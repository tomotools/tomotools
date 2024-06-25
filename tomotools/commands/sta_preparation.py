import os
from os import path

import click

from tomotools.utils import comfile, sta_util, tiltseries, tomogram
from tomotools.utils.tiltseries import (
    convert_input_to_TiltSeries,
    run_ctfplotter,
)


@click.command()
@click.argument('input_files', nargs=-1)
def fit_ctf(input_files):
    """Performs interactive CTF-Fitting.

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
              help="Warp working directory will be created as project_dir/name.")
@click.argument('input_files', nargs=-1)
@click.argument('project_dir', nargs=1)
def imod2warp(batch_input, name, input_files, project_dir):
    """Prepares Warp/M project.

    Takes as input several tiltseries (folders) or a file listing them (with -b),
    obtained after processing with tomotools batch-prepare-tiltseries
    and reconstructed in subdirectories using imod.

    Provide the root folder for the averaging project and a name for this export.
    This will be the Warp working directory. Both will be created if non-existent.

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
        input(f'Exporting to existing directory {out_dir}. Continue?')

    else:
        os.mkdir(out_dir)
        os.mkdir(path.join(out_dir, 'imod'))
        os.mkdir(path.join(out_dir, 'mdoc'))
        print(f"Created Warp folder at {out_dir}.")

    # Parse input files
    ts_list = sta_util.batch_parser(input_files, batch_input)

    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")

        sta_util.make_warp_dir(ts, out_dir, imod = True)

        print(f"Warp files prepared for {ts.path.name}. \n")


@click.command()
@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.option('-n', '--name', default='warp', show_default=True,
              help="Warp working directory will be created as project_dir/name.")
@click.argument('input_files', nargs=-1)
@click.argument('project_dir', nargs=1)
def aretomo2warp(batch_input, name, input_files, project_dir):
    """Prepares Warp/M project.

    Takes as input several tiltseries (folders) or a file listing them (with -b),
    obtained after processing with tomotools batch-prepare-tiltseries
    and reconstructed in subdirectories using AreTomo.

    Provide the root folder for the averaging project and a name for this export.
    This will be the Warp working directory. Both will be created if non-existent.

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
        input(f'Exporting to existing directory {out_dir}. Continue?')

    else:
        os.mkdir(out_dir)
        os.mkdir(path.join(out_dir, 'imod'))
        os.mkdir(path.join(out_dir, 'mdoc'))
        print(f"Created Warp folder at {out_dir}.")

    ts_list = sta_util.batch_parser(input_files, batch_input)

    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")

        ts_out_imod = sta_util.aretomo_export(ts)

        print(f'Performed AreTomo export of {ts.path.stem}.')

        sta_util.make_warp_dir(ts_out_imod, out_dir)

        print(f"Warp files prepared for {ts.path.name}. \n")


@click.command()
@click.option('--thickness', default = 3000, show_default = True,
              help="Total thickness in unbinned pixels.")
@click.option('--bin', default = 1, show_default = True,
              help="Desired binning level.")
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
def reconstruct_3dctf(thickness, bin, input_files):
    """Reconstruct tomograms using imod's ctf3d command.

    Assumes that tiltseries have previously been aligned using tomotools reconstruct.

    Prefers imod to aretomo alignment, if both are found.
    """
    input_ts = convert_input_to_TiltSeries(input_files)

    print(f'Found {len(input_ts)} TiltSeries to work on. \n')

    for ts_in in input_ts:

        print(f'Now working on {ts_in.path}.')

        # Test whether imod alignment found
        if path.isfile(ts_in.path.with_suffix(".xf")):
            ts = ts_in
            aretomo = False

        # Test whether AreTomo alignment found
        elif path.isfile(ts_in.path.with_suffix(".aln")):
            ts = sta_util.aretomo_export(ts_in)
            sta_util.ctfplotter_aretomo_export(ts_in)
            aretomo = True

        else:
            print(f"No previous alignments found for {ts_in.path}.")
            continue

        # Align
        ts_ali = tiltseries.align_with_imod(ts, True, False, binning = bin)

        # Perform dose filtration
        ts_ali_filt = tiltseries.dose_filter(ts_ali, False)
        ts_ali.delete_files(False)

        # Check that defocus file is there + create ctf com-file
        # Otherwise, open ctfplotter
        if ts.defocus_file() is None:
            print(f'Defocus file not found for {ts.path.name}. Running ctfplotter now.')
            run_ctfplotter(ts, True)

        comfile.fake_ctfcom(ts_ali_filt, 1)

        dim_x, dim_y = tiltseries.binned_size(ts, 1)

        rec = tomogram.Tomogram.from_tiltseries_3dctf(
            ts_ali_filt, binning=bin, thickness=thickness,
            z_slices_nm=25, fullimage=[dim_x,dim_y])

        # Link reconstruction back to main dir, in case AreTomo alignments are used
        if aretomo:
            os.symlink(rec.path.absolute(),
                       ts_in.path.parent / f'{ts_in.path.stem}_3dctf_bin{bin}.mrc')
        else:
            os.rename(rec.path.absolute(), 
                      ts_in.path.parent / f'{ts_in.path.stem}_3dctf_bin{bin}.mrc')

        print('\n')


    return

@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.option('-d', '--thickness', default=3000, show_default=True,
              help="Tomogram thickness in unbinned pixels.")
@click.option('--bin-up/--bin-down', is_flag=True, default=True, show_default=True,
              help="Default calculates binning closest to 10A and rounds up.")
@click.option('--uid', default='imod', show_default=True,
              help="Unique identifier to tell apart tomograms from several sessions.")
@click.argument('input_files', nargs=-1)
@click.argument('tomotwin_dir', nargs=1)
def imod2tomotwin(batch_input, thickness, bin_up, uid, input_files, tomotwin_dir):
    """Prepare for TomoTwin picking.

    Takes as input several tiltseries (folders) or a file listing them (with -b),
    obtained after processing with tomotools batch-prepare-tiltseries
    and reconstructed in subdirectories using imod.

    Will output tomograms as desired by TomoTwin in the specified project folder,
    subfolder "tomo".

    Provide the unbinned thickness, and a unique identifier for this session.
    UID will be put in from of name, e.g. 230105_TS_01.mrc.
    """
    ts_list = sta_util.batch_parser(input_files, batch_input)

    sta_util.tomotwin_prep(tomotwin_dir, ts_list, thickness, uid, bin_up=bin_up)


@click.command()
@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.option('-d', '--thickness', default=3000, show_default=True,
              help="Tomogram thickness in unbinned pixels.")
@click.option('--bin-up/--bin-down', is_flag=True, default=True, show_default=True,
              help="Default calculates binning closest to 10A and rounds up.")
@click.option('--uid', default='aretomo', show_default=True,
              help="Unique identifier to tell apart tomograms from several sessions.")
@click.argument('input_files', nargs=-1)
@click.argument('tomotwin_dir', nargs=1)
def aretomo2tomotwin(batch_input, thickness, bin_up, uid, input_files, tomotwin_dir):
    """Prepare for TomoTwin picking.

    Takes as input several tiltseries (folders) or a file listing them (with -b),
    obtained after processing with tomotools batch-prepare-tiltseries
    and reconstructed in subdirectories using AreTomo.

    Will output tomograms as desired by TomoTwin in the specified project folder,
    subfolder "tomo".

    Provide the unbinned thickness, and a unique identifier for this session.
    UID will be put in from of name, e.g. 230105_TS_01.mrc.
    """
    # Get input files
    ts_list = sta_util.batch_parser(input_files, batch_input)

    # Process aretomo -> imod
    print(f'Found {len(ts_list)} TiltSeries to work on. \n')

    ts_imodlike = []

    for ts in ts_list:
        print(f"Now working on {ts.path.name}")
        ts_imodlike.append(sta_util.aretomo_export(ts))

    # Process as normal imod-aligned TS
    sta_util.tomotwin_prep(tomotwin_dir, ts_imodlike, thickness, uid, bin_up=bin_up)

   