import csv
from operator import itemgetter
from os import path
from pathlib import Path


def convert_to_order_list(mdoc: dict, out_dir: Path):
    """Writers order_list.csv required for Relion4.

    Takes mdoc as dict (via mdocfile.read) and path for output.
    Returns path to output file.
    """
    # Sorte by DateTime to get order of acquisition
    mdoc['sections'] = sorted(mdoc['sections'], key=itemgetter('DateTime'))

    tilt_list = [int(section['TiltAngle']) for section in mdoc['sections']]

    # Generate output file path
    output_file = path.join(out_dir, (out_dir.stem + '_order.csv'))

    with open(output_file, 'w+') as f:
        writer = csv.writer(f)
        i = 1

        for tilt in tilt_list:
            writer.writerow([i, tilt])
            i = i + 1

    return output_file

def _convert_value_field(field: str):
    if " " in field:
        # If there's a space in the field,
        # it might either be a string containing spaces or a tuple of ints/floats
        fields_split = [_convert_value_field(f) for f in field.split()]
        # check if all fields were successfully converted to int or float
        if all(isinstance(v, int) or isinstance(v, float) for v in fields_split):
            return fields_split
        else:
            # otherwise it must have been a string
            return field
    else:
        try:
            return int(field)
        except ValueError:
            pass
        try:
            return float(field)
        except ValueError:
            pass
        # No conversion possible
        return field


def find_relative_path(working_dir: Path, abs_path: Path):
    """Try to find paths relative to the current working dir."""
    while not working_dir.joinpath(abs_path).is_file():
        try:
            # Cut off first part
            abs_path = Path(*abs_path.parts[1:])
        except IndexError:
            return None
    # print(f'Found subframe path: "{join(working_dir, abs_path)}')
    return working_dir.joinpath(abs_path)


def read(file: Path):
    """Read mdoc from path as dictionary."""
    mdoc = {}
    mdoc["path"] = file
    mdoc["titles"] = []
    mdoc["sections"] = []
    mdoc["framesets"] = []
    # The currently edited dict, at the beginning this is "global" the mdoc itself
    # For each ZValue current_section will be set to the dict belonging to that section
    current_section = mdoc
    with open(file) as f:
        for line in f:
            line = line.strip()
            # field, value = line.split(' = ')
            if line.startswith("[T ="):  # Title
                mdoc["titles"].append(line[4:-1])
            elif line.startswith("[ZValue ="):  # Section
                current_section = {}
                mdoc["sections"].append(current_section)
            elif line.startswith("[FrameSet ="):  # Section
                current_section = {}
                mdoc["framesets"].append(current_section)
            elif len(line) == 0:
                continue
            else:
                try:
                    key, value = line.split(" = ", maxsplit=1)
                    current_section[key] = _convert_value_field(value)
                except ValueError:
                    print(f'Parsing error, invalid line: "{line}"')
    return mdoc


def _write_key_value(file, key, value):
    if isinstance(value, list):
        file.write(f'{key} = {" ".join([str(v) for v in value])}\n')
    else:
        file.write(f"{key} = {value!s}\n")


def write(mdoc, path):
    """Write mdoc from dict at path."""
    with open(path, "w") as file:
        # First write global vars, then titles, ZValues and FrameSets
        for key, value in mdoc.items():
            if key in ("titles", "sections", "framesets"):
                continue
            _write_key_value(file, key, value)

        for title in mdoc["titles"]:
            file.write(f"\n\n[T = {title}]")

        file.write("\n")
        for i, section in enumerate(mdoc["sections"]):
            file.write(f"\n[ZValue = {i}]\n")
            for key, value in section.items():
                _write_key_value(file, key, value)

        for i, frameset in enumerate(mdoc["framesets"]):
            file.write(f"[FrameSet = {i}]\n")
            for key, value in frameset.items():
                _write_key_value(file, key, value)

def downgrade_DateTime(mdoc: dict):
    """Downgrades DateTime from YYYY to YY (behaviour SerialEM < 4)."""
    for section in mdoc['sections']:
        #Check that date is really in DD-MMM-YYYY (= 11 chars)
        if len(section['DateTime'].split()[0]) == 11:
            section['DateTime'] = section['DateTime'][0:7]+section['DateTime'][9::]
        else:
            continue

    return mdoc


def get_start_tilt(mdoc: dict):
    """Returns the starting tilt, even after reordering."""
    # Sorte by DateTime to get order of acquisition
    mdoc['sections'] = sorted(mdoc['sections'], key=itemgetter('DateTime'))

    return mdoc['sections'][0]['TiltAngle']
