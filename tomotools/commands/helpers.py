import shutil
from os import path
from pathlib import Path
from subprocess import run

import click

from tomotools.utils import mdocfile, tiltseries


@click.command()
@click.option(
    "--branch", default="main", show_default=True, help="The GitHub branch to use"
)
def update(branch):
    """Auto-update tomotools to the latest version."""
    print("Updating...")
    run(
        [
            "pip",
            "install",
            "--upgrade",
            f"git+https://github.com/tomotools/tomotools.git@{branch}",
        ]
    )
    print("Update completed!")

@click.command()
@click.argument("orig_mdoc_dir", nargs=1, type=click.Path(exists=True))
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
def restore_frames(orig_mdoc_dir, input_files):
    """Restore SubFramePath to mdoc.

    orig_mdoc_dir: Folder containing the original tiltseries mdoc files
    input_files: An enumeration of tiltseries(-folders) from tomotools preprocess

    Will save the old mdoc in the tiltseries folder as .mdocbackup file.
    Will write the mdoc with SubFramePath to the original location.
    """
    # Parse all tiltseries
    ts_list = tiltseries.convert_input_to_TiltSeries(input_files)

    orig_mdoc_dir = Path(orig_mdoc_dir)

    # Iterate over Tiltseries
    for ts in ts_list:



        mdoc = mdocfile.read(ts.mdoc)

        # For each, find the corresponding input mdoc
        orig_mdoc_paths = list(orig_mdoc_dir.glob(f"*{ts.path.stem}*.mdoc"))

        if len(orig_mdoc_paths) == 0:
            print(f'{ts.path.name}: no original mdoc file found. Skipping.')
            continue

        elif len(orig_mdoc_paths) > 1:
            print(f'{ts.path.name}: multiple original mdoc files found. Skipping.')
            print(orig_mdoc_paths)
            continue

        print(f"{ts.path.name}: found original mdoc file {orig_mdoc_paths[0]}")

        orig_mdoc = mdocfile.read(orig_mdoc_paths[0])

        orig_mdoc = sorted(
            orig_mdoc['sections'], key=lambda section: section['TiltAngle'])

        # Iterate over sections
        for section in mdoc['sections']:

            for orig_section in orig_mdoc:
                # Match by tilt angle
                if orig_section['TiltAngle'] == section['TiltAngle']:
                    same_section = orig_section
                else:
                    continue

                # Confirm Acquistion time
                if not same_section["DateTime"] == section["DateTime"]:
                    print(f"{ts.path.stem}: {section['TiltAngle']} deg DateTime error:")
                    print(f"{same_section['DateTime']} vs. {section['DateTime']}")
                else:
                    section["SubFramePath"] = same_section["SubFramePath"]

        # Write fixed mdoc
        if all("SubFramePath" in section for section in mdoc["sections"]):
            for section in mdoc["sections"]:

                section["SubFramePath"] = mdocfile.find_relative_path(
                    Path(orig_mdoc_dir),
                    Path(section.get("SubFramePath", "").replace("\\", path.sep)),
                )

            # Backup old mdoc
            shutil.copy(ts.mdoc, ts.mdoc.with_suffix(".mdocbackup"))

            mdocfile.write(mdoc, ts.mdoc)

        else:
            print(f"{ts.path.stem}: no complete set of SubFramePath found.")
            print("Leaving as-is.")

        print("\n")
