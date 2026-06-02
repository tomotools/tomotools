import os
from os import path
from pathlib import Path
from typing import List, Optional, Tuple

import click

from tomotools.utils import comfile, sta_util, tiltseries, tomogram
from tomotools.utils.tiltseries import (
    TiltSeries,
    convert_input_to_TiltSeries,
    run_ctfplotter,
)


@click.command()
@click.argument("input_files", nargs=-1)
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
@click.option(
    "-b",
    "--batch-input",
    is_flag=True,
    hidden=True,
    help="[Deprecated] Read input files as text, each line is a tiltseries (folder)",
)
@click.option(
    "--v2/--v1",
    is_flag=True,
    default=True,
    hidden=True,
    help="[Deprecated] WarpTools (2.x) or Warp (1.x) project. Default is WarpTools.",
)
@click.option(
    "--aretomo",
    is_flag=True,
    default=False,
    show_default=True,
    help="Input files are outputs of AreTomo, not imod.",
)
@click.option(
    "--link-frames",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Link frames from this directory.",
)
@click.option(
    "--copy-frames",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Copy frames from this directory.",
)
@click.option(
    "--extract-frames",
    is_flag=True,
    default=False,
    show_default=True,
    help="Extract images from tilt stack. Only use if no raw frames are available.",
)
@click.argument(
    "input_files",
    type=click.Path(file_okay=True, dir_okay=True, path_type=Path),
    nargs=-1,
)
@click.argument(
    "project_dir",
    type=click.Path(file_okay=False, writable=True, path_type=Path),
    nargs=1,
)
def imod2warp(
    batch_input: bool,
    v2: bool,
    aretomo: bool,
    link_frames: Optional[Path],
    copy_frames: Optional[Path],
    extract_frames: bool,
    input_files: Tuple[Path],
    project_dir: Path,
):
    """Export aligned tilt-series into a Warp/M project.

    Takes as input ETomo- or AreTomo-aligned tilt-series (in the form of folders,
    mdoc files, etomo batch (.ebt), etomo project (.edf) or text files listing them)
    and exports them for Warp/M into a specified project directory.
    """
    if sum([bool(link_frames), bool(copy_frames), extract_frames]) > 1:
        click.echo(
            "Cannot both link frames, copy frames and extract frames."
            "Please choose one option."
        )
        return
    project_dir.mkdir(exist_ok=True)
    (project_dir / "imod").mkdir(exist_ok=True)
    (project_dir / "mdoc").mkdir(exist_ok=True)
    (project_dir / "frames").mkdir(exist_ok=True)

    # Parse input files
    ts_list: List[TiltSeries] = []
    for input_file in input_files:
        ts_list.extend(TiltSeries.from_path(input_file))

    if copy_frames:
        frames_strategy = ("copy", copy_frames)
    elif link_frames:
        frames_strategy = ("link", link_frames)
    elif extract_frames:
        frames_strategy = ("extract", None)
    else:
        frames_strategy = ("skip", None)
    with click.progressbar(
        ts_list,
        label=f"Working on {len(ts_list)} TiltSeries",
        item_show_func=lambda x: f"Processing {x.path.name}" if x else None,
    ) as progress:
        for ts in progress:
            if aretomo:
                ts_out_imod = sta_util.aretomo_export(ts)
            else:
                ts_out_imod = ts

            sta_util.make_warp_dir(
                ts_out_imod,
                project_dir,
                frames_strategy=frames_strategy,
                imod=not aretomo,
            )


@click.command()
@click.option(
    "--thickness",
    default=3000,
    show_default=True,
    help="Total thickness in unbinned pixels.",
)
@click.option("--bin", default=1, show_default=True, help="Desired binning level.")
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
def reconstruct_3dctf(thickness, bin, input_files):
    """Reconstruct tomograms using imod's ctf3d command.

    Assumes that tiltseries have previously been aligned using tomotools reconstruct.

    Prefers imod to aretomo alignment, if both are found.
    """
    input_ts = convert_input_to_TiltSeries(input_files)

    print(f"Found {len(input_ts)} TiltSeries to work on. \n")

    # First, check whether all defocus files are there
    for ts_in in input_ts:
        # Test, whether .defocus file is found
        if not path.isfile(ts_in.path.with_suffix(".defocus")):
            run_ctfplotter(ts_in, True)

    print("All defocus files found or created.")

    for ts_in in input_ts:
        print(f"Now working on {ts_in.path}.")

        # Test whether imod alignment found
        if path.isfile(ts_in.path.with_suffix(".xf")):
            ts = ts_in

        # Test whether AreTomo alignment found
        elif path.isfile(ts_in.path.with_suffix(".aln")):
            ts = sta_util.aretomo_export(ts_in)
            sta_util.ctfplotter_aretomo_export(ts_in)

        else:
            print(f"No previous alignments found for {ts_in.path}.")
            continue

        # Align
        ts_ali = tiltseries.align_with_imod(ts, True, False, binning=bin)

        # Perform dose filtration
        ts_ali_filt = tiltseries.dose_filter(ts_ali, False)
        ts_ali.delete_files(False)

        # Check that defocus file is there + create ctf com-file
        # Otherwise, open ctfplotter
        if ts.defocus_file() is None:
            print(f"Defocus file not found for {ts.path.name}. Running ctfplotter now.")
            run_ctfplotter(ts, True)

        comfile.fake_ctfcom(ts_ali_filt, 1)

        dim_x, dim_y = tiltseries.binned_size(ts, 1)

        rec = tomogram.Tomogram.from_tiltseries_3dctf(
            ts_ali_filt,
            binning=bin,
            thickness=thickness,
            z_slices_nm=25,
            fullimage=[dim_x, dim_y],
        )

        # Move / rename reconstruction
        os.rename(
            rec.path.absolute(),
            ts_in.path.parent.absolute() / f"{ts_in.path.stem}_3dctf_bin{bin}.mrc",
        )

        print("\n")

        print("\n")

    return


@click.command()
@click.option(
    "-b",
    "--batch-input",
    is_flag=True,
    hidden=True,
    help="[Deprecated] Read input files as text, each line is a tiltseries (folder)",
)
@click.option(
    "-d",
    "--thickness",
    default=3000,
    show_default=True,
    help="Tomogram thickness in unbinned pixels.",
)
@click.option(
    "--aretomo",
    is_flag=True,
    default=False,
    show_default=True,
    help="Input files are outputs of AreTomo, not imod.",
)
@click.option(
    "--bin-up/--bin-down",
    is_flag=True,
    default=True,
    show_default=True,
    help="Default calculates binning closest to 10A and rounds up.",
)
@click.option(
    "--uid",
    default="",
    show_default=True,
    help="Unique identifier to tell apart tomograms from several sessions.",
)
@click.argument("input_files", nargs=-1)
@click.argument("tomotwin_dir", nargs=1)
def imod2tomotwin(
    batch_input, thickness, aretomo, bin_up, uid, input_files, tomotwin_dir
):
    """Prepare for TomoTwin picking.

    Takes as input several tiltseries (folders) or a file listing them (with -b),
    obtained after processing with tomotools.

    Will output tomograms as desired by TomoTwin in the specified project folder,
    subfolder "tomo".

    Provide the unbinned thickness, and a unique identifier for this session.
    UID will be put in from of name, e.g. 230105_TS_01.mrc.
    """
    ts_list: List[TiltSeries] = []

    for input_file in input_files:
        ts_list.extend(TiltSeries.from_path(input_file))

    if aretomo:
        ts_list_temp = []

        for ts in ts_list:
            ts_list_temp.append(sta_util.aretomo_export(ts))

        ts_list = ts_list_temp

    sta_util.tomotwin_prep(tomotwin_dir, ts_list, thickness, uid, bin_up=bin_up)
