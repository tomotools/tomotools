import os
from datetime import date
from os import path
from pathlib import Path

import click
import pandas as pd
import starfile

from tomotools.utils import sta_util
from tomotools.utils.tiltseries import (
    convert_input_to_TiltSeries,
    dose_filter,
)
from tomotools.utils.tomogram import Tomogram


@click.command()
@click.option('--bin',
              default=4,
              show_default=True,
              help="Binning for reconstruction used to pick particles.")
@click.option('--sirt',
              default=0,
              show_default=True,
              help="SIRT-like filter for reconstruction used to pick particles.")
@click.option('-d','--thickness',
              default=3000,
              show_default=True,
              help="Thickness for reconstruction. Needs to be set so.")
@click.option('-b',
              '--batch-input',
              is_flag=True,
              default=False,
              show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.argument('input_files', nargs=-1)
@click.argument('relion_root', nargs=1)
def aretomo2relion(bin, sirt, thickness, batch_input, input_files, relion_root):
    """Prepares Relion4 project.

    Takes as input several tiltseries (folders) obtained after processing
    with tomotools batch-prepare-tiltseries and tomotools reconstruct.
    Gets all required output files from AreTomo,
    makes a new binned reconstruction for particle picking.

    Provide the relion root folder. This may be a previously existing project.
    Generates starfile for tomogram import in the relion root with current date.
    Makes one optics group per date of acquisition.

    """
    # Prepare folders
    if not path.isdir(relion_root):
        os.mkdir(relion_root)
        print(f'Created Relion root directory at {relion_root}')

    tomo_root = path.join(relion_root, 'Tomograms')

    if not path.isdir(tomo_root):
        os.mkdir(tomo_root)
        print(f'Created ./Tomograms directory at {tomo_root}.')

    # Parse input files
    if batch_input:
        input_files_parsed = []
        with open(input_files[0], "r+") as f:
            for line in f:
                input_files_parsed.append(line.strip("\n"))

    else:
        input_files_parsed = input_files

    # Convert to list of tiltseries
    ts_list = convert_input_to_TiltSeries(input_files_parsed)

    # Initialize dataframe for starfile
    df = pd.DataFrame()

    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")
        tomo_folder = Path(path.join(tomo_root, ts.path.stem))

        if path.isdir(tomo_folder):
            raise FileExistsError(
                "This tomogram seems to already exist in the target relion project. Maybe names are non-unique?" #noqa: E501
                )

        ts_out_imod = sta_util.aretomo_export(ts)

        print(f'Performed AreTomo export of {ts.path.stem}.')

        # Make reconstruction for picking
        ali_stack_filtered = dose_filter(ts_out_imod, False)
        ali_rec = Tomogram.from_tiltseries(ali_stack_filtered,
                                           bin = bin,
                                           sirt = sirt,
                                           thickness = thickness,
                                           convert_to_byte=False)

        ali_stack_filtered.delete_files(delete_mdoc=False)

        print(f'Created reconstruction for particle picking at {ali_rec.path.name}.')

        df_temp = sta_util.make_relion_dir(ts,
                                           tomo_folder,
                                           override_thickness=thickness)

        df = pd.concat([df_temp.astype(object), df])

        print(f'Successfully created tomograms folder for {ts.path.name}. \n')

    # Write out import_tomos.star file w/ current date for easy ID

    today = date.today()
    date_formatted = today.strftime("%y%m%d")

    starfile_path = path.join(relion_root, (date_formatted + "_tomotools_import.star"))

    starfile.write(df, starfile_path)

    print(f'Wrote out file for Relion import at {starfile_path}.')
