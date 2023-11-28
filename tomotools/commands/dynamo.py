from os import listdir, mkdir, symlink
from os.path import abspath, basename, isdir, isfile, join

import click
import dynamotable
import emfile
import numpy as np
import pandas as pd
from dynamotable.utils import COLUMN_NAMES as TABLE_COLUMN_NAMES


class SettingsCard:
    def __init__(self, path: str, settings: dict):
        self.path: str = path
        self.settings: dict = settings

    def __getattr__(self, attr):
        if attr in self.settings:
            return self.settings[attr]
        elif attr == "s":
            return self.settings
        else:
            raise AttributeError(f'No such setting "{attr}"')

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def update(self, other: "SettingsCard"):
        self.settings.update(other.settings)

    @staticmethod
    def read(path: str) -> "SettingsCard":
        settings = {}
        with open(path) as file:
            for line in file:
                key, value = line.strip().rstrip(";").split("=")
                if " " in value:
                    value = value.split()
                settings[key] = value
        return SettingsCard(path, settings)

    def write(self, path: str):
        with open(path, "w") as file:
            for key, value in self.settings.items():
                if type(value) == list:
                    value = "  ".join(value)
                file.write(f"{key}={value};\n")


class DataDir:
    @staticmethod
    def empty_table():
        return pd.DataFrame(columns=TABLE_COLUMN_NAMES)

    def path_for_tag(self, tag: int):
        batch_size: int = self.settings.get("batch", 0)
        padding: int = self.settings.get("padding", 6)
        ext: str = self.settings.get("extension", "em")
        batch_dir: str = (
            f"batch_{tag // batch_size * batch_size}" if batch_size > 0 else ""
        )
        particle_file: str = f"particle_{tag:0{padding}}.{ext}"
        return abspath(join(self.path, batch_dir, particle_file))

    def __init__(self, path: str, table_path: str):
        # Directory path
        self.path = path
        if not isdir(self.path):
            mkdir(self.path)

        # Table
        self.table_path = table_path
        if isfile(self.table_path):
            self.table = dynamotable.read(self.table_path)
        else:
            self.table = DataDir.empty_table()

        # Read settings.card file if it exists
        self.settings_file = join(self.path, "settings.card")
        if isfile(self.settings_file):
            self.settings = SettingsCard.read(self.settings_file)
        else:
            self.settings = SettingsCard(self.settings_file, {})

        # Particle paths
        self.table["particle_path"] = self.table["tag"].transform(self.path_for_tag)

    def append(self, other: "DataDir"):
        other_table = other.table.copy()
        max_tag = self.table["tag"].max()
        if pd.notna(max_tag):
            other_table["tag"] += max_tag
        self.table = self.table.append(other_table, ignore_index=True)

    def write_table(self, path):
        dynamotable.write(
            self.table[
                [col for col in TABLE_COLUMN_NAMES if col in self.table.columns]
            ],
            path,
        )

    def link_particles_to(self, path):
        def link_tag(row):
            tag = row["tag"]
            symlink(
                row["particle_path"], join(path, f"particle_{tag:0{padding}}.{ext}")
            )

        padding: int = self.settings.get("padding", 6)
        ext: str = self.settings.get("extension", "em")
        self.table.apply(link_tag, axis=1)


class DBox:
    def __init__(self, path):
        # Path
        self.path = abspath(path)
        if not isdir(self.path):
            mkdir(self.path)
        # Tags
        self.tags_file = join(self.path, "tags.em")
        if isfile(self.tags_file):
            self.tags = emfile.read(self.tags_file)
        else:
            self.tags = ({}, np.array([[[]]], np.float32))
        # Table
        self.table_file = join(self.path, "crop.tbl")
        if isfile(self.table_file):
            self.table = dynamotable.read(self.table_file)
        else:
            self.table = pd.DataFrame(columns=TABLE_COLUMN_NAMES)
        # settings.card
        self.settings_file = join(self.path, "settings.card")
        if isfile(self.settings_file):
            self.settings = SettingsCard.read(self.settings_file)
        else:
            self.settings = SettingsCard(self.settings_file, {})


def _link_particles(source_dbox: DBox, dest_dbox: DBox):
    # Loop through the batch_xxxx directories
    for batch_dir in [
        dir for dir in listdir(source_dbox.path) if dir.startswith("batch_")
    ]:
        # Create the batch_xxxx directories in dbox_out
        mkdir(join(dest_dbox.path, batch_dir))
        # link the individual particles
        for particle in listdir(join(source_dbox.path, batch_dir)):
            symlink(
                join(source_dbox.path, batch_dir, particle),
                join(dest_dbox.path, batch_dir, particle),
            )


def _merge_tags(original, appended):
    from copy import deepcopy

    import numpy as np

    # Merge the two headers
    header = deepcopy(original[0])
    header.update(appended[0])
    # The data is essentially a list of tags, ascending order, but in the form of a numpy array with shape (1, 1, x)
    data = np.array(
        [[np.append(original[1], appended[1] + np.max(original[1], initial=0))]]
    )
    header["xdim"] = data[0][0].shape[0]
    return (header, data)


def _merge_tables(original, appended):
    appended = appended.copy()
    max = original["tag"].max()
    if pd.notna(max):
        appended["tag"] += original["tag"].max()
    return original.append(appended, ignore_index=True)


def _decimal_digits(number: int) -> int:
    if number < 1:
        raise ValueError(
            "Number of decimal places will only be determined for numbers > 0"
        )
    digits: int = 0
    while number >= 10**digits:
        digits += 1
    return digits


@click.command()
def merge_dboxes(*args, **kwargs):
    """!!!Very much work in progress!!! Merge Dynamo dBoxes folders"""
    if len(args) < 3:
        return
    # TODO: do some compatibility checking, e.g. compare settings.card files and so on
    dboxes = [DBox(arg) for arg in args[:-1]]
    dbox_out = abspath(args[-1])
    if isdir(dbox_out):
        raise FileExistsError("Output directory already exists, not overwriting")
    dbox_out = DBox(dbox_out)

    # Determine the required padding and set some default parameters (batch_size etc.)
    particle_count: int = sum([dbox.table["tag"].size for dbox in dboxes])
    padding: int = _decimal_digits(particle_count)
    batch_size: int = 1000
    print(
        f"Particle count: {particle_count}\nPadding: {padding}\nBatch_size: {batch_size}"
    )

    # Create the batch_xxx folders in the target DBox directory
    for batch in range(0, particle_count, batch_size):
        mkdir(join(dbox_out.path, f"batch_{batch}"))

    linked_particle_count: int = 0
    for dbox in dboxes:
        # Loop through the source DBoxes, read some settings
        print(f"Linking DBox {basename(dbox.path)}")
        local_batch_size: int = int(dbox.settings.batch)
        local_padding: int = int(dbox.settings.padding)
        ext: str = dbox.settings.extension
        # Loop through the tags (particles), create symlinks in the destination folder in ascending order
        for tag in dbox.table["tag"]:
            tag = int(tag)
            linked_particle_count += 1
            src_particle = join(  # The source particle, where the link will point
                dbox.path,  # ./list.../
                f"batch_{tag // local_batch_size * local_batch_size}",  # ./list.../batch_xxx/
                f"particle_{tag:0{local_padding}}.{ext}",  # ./list.../batch_xxx/particle_xxxx.em
            )
            dst_particle = join(  # The destination, where the link will be created
                dbox_out.path,  # ./list.../
                f"batch_{linked_particle_count // batch_size * batch_size}",  # ./list.../batch_xxx/
                f"particle_{linked_particle_count:0{padding}}.{ext}",  # ./list.../batch_xxx/particle_xxxx.em
            )
            if not isfile(src_particle):
                raise FileNotFoundError(f"Source particle not found: {src_particle}")
            if isfile(dst_particle):
                raise FileExistsError(
                    f"Destination particle file already exists: {dst_particle}"
                )
            symlink(src_particle, dst_particle)
        # All links for this dbox were created, now merge the tables, tags and settings:
        # Merge the tags
        dbox_out.tags = _merge_tags(dbox_out.tags, dbox.tags)
        # Merge the tables
        dbox_out.table = _merge_tables(dbox_out.table, dbox.table)
        # Merge settings
        dbox_out.settings.update(dbox.settings)

    # The padding and batch size might have to be updated
    dbox_out.settings.s["padding"] = padding
    dbox_out.settings.s["batch"] = batch_size

    # Write the metadata files
    dynamotable.write(dbox_out.table, dbox_out.table_file)
    emfile.write(dbox_out.tags_file, dbox_out.tags[1], header_params=dbox_out.tags[0])
    dbox_out.settings.write(dbox_out.settings_file)
    return dbox_out


def flip_table(path: str):
    def flip_angle(angle: float):
        return angle - 180.0 if angle > 0 else angle + 180

    table = dynamotable.read(path)
    basename, ext = path.rsplit(".", maxsplit=1)
    out_filename = f"{basename}_flipped.{ext}"

    table["tilt"] = table["tilt"].transform(flip_angle)

    dynamotable.write(table, out_filename)
