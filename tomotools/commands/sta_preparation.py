import os
import click
import starfile
import math

import pandas as pd

from os import path
from pathlib import Path
from datetime import date

from tomotools.utils import sta_util, tiltseries
from tomotools.utils.tiltseries import run_ctfplotter, dose_filter, convert_input_to_TiltSeries
from tomotools.utils.tomogram import Tomogram


@click.command()
@click.argument('input_files', nargs=-1)
def fit_ctf(input_files):
    """ Performs interactive CTF-Fitting.

    Takes tiltseries or folders containing them as input.
    Runs imod ctfplotter interactively.
    Defaults to overwriting previous results. Saves results to folder.

    """

    tiltseries = convert_input_to_TiltSeries(input_files)

    for ts in tiltseries:
        run_ctfplotter(ts, True)


@click.command()
@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.option('-n', '--name', default='warp', show_default=True,
              help="Warp working directory will be created as project_dir/name. Maybe put microscope session here?")
@click.argument('input_files', nargs=-1)
@click.argument('project_dir', nargs=1)
def imod2warp(batch_input, name, input_files, project_dir):
    """ Prepares Warp/M project. 

    Takes as input several tiltseries (folders) or a file listing them (with -b) obtained after processing with tomotools batch-prepare-tiltseries and reconstructed in subdirectories using imod.

    Provide the root folder for the averaging project and a name for this export. This will be the Warp working directory. Both will be created if non-existent.

    Suggested structure is something like this:

    project_dir/
        ./warpdir1/
        ./warpdir2/
        ./warpdir3/
        ./relion/
        ./m/

    """
    out_dir = path.join(project_dir, name)

    if not path.isdir(project_dir):
        os.mkdir(project_dir)

    if path.isdir(out_dir):
        input(
            f'Exporting to existing directory {out_dir}. Are you sure you want to continue?')

    else:
        os.mkdir(out_dir)
        os.mkdir(path.join(out_dir, 'imod'))
        os.mkdir(path.join(out_dir, 'mdoc'))
        print(f"Created Warp folder at {out_dir}.")

    # Parse input files
    if batch_input:
        input_files_parsed = sta_util.batch_parser(input_files[0])

    else:
        input_files_parsed = input_files

    # Convert to list of tiltseries
    ts_list = convert_input_to_TiltSeries(input_files_parsed)

    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")

        sta_util.make_warp_dir(ts, out_dir)

        print(f"Warp files prepared for {ts.path.name}. \n")


@click.command()
@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.option('-n', '--name', default='warp', show_default=True,
              help="Warp working directory will be created as project_dir/name. Maybe put microscope session here?")
@click.argument('input_files', nargs=-1)
@click.argument('project_dir', nargs=1)
def aretomo2warp(batch_input, name, input_files, project_dir):
    # TODO: Simplify by just calling imod2warp?
    """ Prepares Warp/M project. 

    Takes as input several tiltseries (folders) or a file listing them (with -b) obtained after processing with tomotools batch-prepare-tiltseries and reconstructed in subdirectories using AreTomo.

    Provide the root folder for the averaging project and a name for this export. This will be the Warp working directory. Both will be created if non-existent.

    Suggested structure is something like this:

    project_dir/
        ./warpdir1/
        ./warpdir2/
        ./warpdir3/
        ./relion/
        ./m/

    """
    out_dir = path.join(project_dir, name)

    if not path.isdir(project_dir):
        os.mkdir(project_dir)

    if path.isdir(out_dir):
        input(
            f'Exporting to existing directory {out_dir}. Are you sure you want to continue?')

    else:
        os.mkdir(out_dir)
        os.mkdir(path.join(out_dir, 'imod'))
        os.mkdir(path.join(out_dir, 'mdoc'))
        print(f"Created Warp folder at {out_dir}.")

    # Parse input files
    if batch_input:
        input_files_parsed = sta_util.batch_parser(input_files[0])

    else:
        input_files_parsed = input_files

    # Convert to list of tiltseries
    ts_list = convert_input_to_TiltSeries(input_files_parsed)

    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")

        ts_out_imod = sta_util.aretomo_export(ts)

        print(f'Performed AreTomo export of {ts.path.stem}.')

        sta_util.make_warp_dir(ts_out_imod, out_dir)

        print(f"Warp files prepared for {ts.path.name}. \n")


@click.command()
@click.option('--bin', default=4, show_default=True, help="Binning for reconstruction used to pick particles.")
@click.option('--sirt', default=0, show_default=True, help="SIRT-like filter for reconstruction used to pick particles.")
@click.option('-d', '--thickness', default=3000, show_default=True, help="Thickness for reconstruction. Needs to be set so relion is not confused.")
@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.argument('input_files', nargs=-1)
@click.argument('relion_root', nargs=1)
def aretomo2relion(bin, sirt, thickness, batch_input, input_files, relion_root):
    """ Prepares Relion4 project. 

    Takes as input several tiltseries (folders) obtained after processing with tomotools batch-prepare-tiltseries and tomotools reconstruct.
    Gets all required output files from AreTomo, makes a new binned reconstruction for particle picking.

    Provide the relion root folder. This may be a previously existing project. Generates starfile for tomogram import in the relion root with current date.
    Makes one optics group per date. 

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
        input_files_parsed = sta_util.batch_parser(input_files[0])

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
                "This tomogram seems to already exist in the target relion project. Maybe names are non-unique?")

        ts_out_imod = sta_util.aretomo_export(ts)

        print(f'Performed AreTomo export of {ts.path.stem}.')

        # Make reconstruction for picking
        ali_stack_filtered = dose_filter(ts_out_imod, False)
        ali_rec = Tomogram.from_tiltseries(
            ali_stack_filtered, bin=bin, sirt=sirt, thickness=thickness, convert_to_byte=False)

        ali_stack_filtered.delete_files(delete_mdoc=False)

        print(
            f'Created reconstruction for particle picking at {ali_rec.path.name}.')

        df_temp = sta_util.make_relion_dir(
            ts, tomo_folder, override_thickness=thickness)

        df = pd.concat([df_temp.astype(object), df])

        print(f'Successfully created tomograms folder for {ts.path.name}. \n')

    # Write out import_tomos.star file w/ current date for easy ID

    today = date.today()
    id = today.strftime("%y%m%d")

    starfile_path = path.join(relion_root, (id + "_tomotools_import.star"))

    starfile.write(df, starfile_path)

    print(f'Wrote out file for Relion import at {starfile_path}.')


@click.command()
@click.argument('input_files', nargs=-1)
def imod2relion(input_files):
    raise NotImplementedError(
        "imod -> relion export is not implemented yet, sorry!")


@click.command()
@click.option('-b', '--batch', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.option('--bin', default=4, show_default=True, help="Binning of reconstruction.")
@click.option('-d', '--thickness', default=3000, show_default=True,
              help="Thickness for reconstruction in unbinned pixels.")
@click.argument('input_files', nargs=-1)
@click.argument('stopgap_dir', nargs=1)
def imod2stopgap(batch, bin, thickness, input_files, stopgap_dir):
    # Get input files
    ts_list = sta_util.batch_parser(input_files, batch)

    sta_util.list2stopgap(bin, thickness, ts_list, stopgap_dir)


@click.command()
@click.option('-b', '--batch', is_flag=True, default=False, show_default=True,
              help="Input is a file with a tiltseries on each line.")
@click.option('--bin', default=4, show_default=True,
              help="Binning for reconstruction.")
@click.option('-d', '--thickness', default=3000, show_default=True,
              help="Thickness for reconstruction.")
@click.argument('input_files', nargs=-1)
@click.argument('stopgap_dir', nargs=1)
def aretomo2stopgap(batch, bin, thickness, input_files, stopgap_dir):
    # Get input files
    ts_list = sta_util.batch_parser(input_files, batch)

    # Process aretomo -> imod
    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    ts_imodlike = []

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")
        ts_imodlike.append(sta_util.aretomo_export(ts))
        sta_util.ctfplotter_aretomo_export(ts)

    # Process as normal imod-aligned TS
    sta_util.list2stopgap(bin, thickness, ts_imodlike, stopgap_dir)


def imod2tomotwin(batch, thickness, uid, input_files, tomotwin_dir):

    ts_list = sta_util.batch_parser(input_files, batch)

    tomotwin_dir = Path(tomotwin_dir)
    tomo_dir = tomotwin_dir / "tomo"

    if not path.isdir(tomo_dir):
        os.mkdir(tomo_dir)

    for ts in ts_list:

        # bin to about 10 Apix, prefer round binning to avoid artifacts
        binning = math.ceil(10 / ts.angpix / 2) * 2

        ts_ali = tiltseries.align_with_imod(ts, True, False, binning=binning)

        rec = Tomogram.from_tiltseries(ts_ali, bin=1, sirt=0,
                                       thickness=round(thickness/binning), convert_to_byte=False)

        unique_name = f'{uid}_{ts.path.parent.name}.mrc'

        os.symlink(rec.path.absolute(), tomo_dir / unique_name)


def aretomo2tomotwin(batch, thickness, uid, input_files, tomotwin_dir):
    # Get input files
    ts_list = sta_util.batch_parser(input_files, batch)

    # Process aretomo -> imod
    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    ts_imodlike = []

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")
        ts_imodlike.append(sta_util.aretomo_export(ts))

    # Process as normal imod-aligned TS
    imod2tomotwin(False, thickness, uid, ts_imodlike, tomotwin_dir)
