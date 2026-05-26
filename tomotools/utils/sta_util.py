import math
import os
import shutil
import subprocess
from glob import glob
from os import path
from pathlib import Path
from typing import List, Tuple, Union
import click
from typing_extensions import Literal

import mrcfile

from tomotools.utils import mdocfile, tomogram
from tomotools.utils.tiltseries import (
    TiltSeries,
    align_with_imod,
    aretomo_executable,
    convert_input_to_TiltSeries,
    parse_ctfplotter,
    parse_darkimgs,
    run_ctfplotter,
    write_ctfplotter,
)


def aretomo_export(ts: TiltSeries):
    """Export AreTomo alignments to xf using -OutImod 2."""
    mdoc = mdocfile.read(ts.mdoc)

    angpix = ts.angpix

    with mrcfile.mmap(ts.path) as mrc:
        labels = mrc.get_labels()

    aln_file = ts.path.with_suffix(".aln")

    ali_stack = ts.path.with_name(f"{ts.path.stem}_ali.mrc")

    imod_dir = path.join(ts.path.parent, (ali_stack.stem + "_Imod"))

    if path.isdir(imod_dir) and path.isfile(
        path.join(imod_dir, (ali_stack.stem + ".st"))
    ):
        print(f"Previous AreTomo export found for {ts.path.name}. Re-using.")

        ali_stack_imod = TiltSeries(Path(path.join(imod_dir, (ali_stack.stem + ".st"))))

        with mrcfile.mmap(ali_stack_imod.path, mode="r+") as mrc:
            mrc.voxel_size = str(angpix)

            # Check whether labels were already added
            if len(mrc.get_labels()) == 0:
                for label in labels:
                    mrc.add_label(label)
            mrc.update_header_stats()

    elif not path.isfile(aln_file):
        raise FileNotFoundError(
            f"{ts.path}: No previous alignment was found at {aln_file}."
        )

    else:
        subprocess.run(
            [
                aretomo_executable(),
                "-InMrc",
                ts.path,
                "-OutMrc",
                ali_stack,
                "-AlnFile",
                aln_file,
                "-TiltCor",
                "0",
                "-VolZ",
                "0",
                "-OutImod",
                "2",
            ],
            stdout=subprocess.DEVNULL,
        )

        ali_stack_imod = TiltSeries(Path(path.join(imod_dir, (ali_stack.stem + ".st"))))

        with mrcfile.mmap(ali_stack, mode="r+") as mrc:
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()

        with mrcfile.mmap(ali_stack_imod.path, mode="r+") as mrc:
            mrc.voxel_size = str(angpix)
            for label in labels:
                mrc.add_label(label)
            mrc.update_header_stats()

    # Get view exclusion list and create appropriate mdoc
    exclude = parse_darkimgs(ts)

    mdoc_cleaned = mdoc

    mdoc_cleaned["sections"] = [
        ele for idx, ele in enumerate(mdoc["sections"]) if idx not in exclude
    ]

    mdocfile.write(mdoc_cleaned, ali_stack_imod.mdoc)

    return ali_stack_imod


def make_warp_dir(
    ts: TiltSeries,
    project_dir: Path,
    frames_strategy: Union[
        Tuple[Literal["skip"], None],
        Tuple[Literal["extract"], None],
        Tuple[Literal["copy"], Path],
        Tuple[Literal["link"], Path],
    ],
    imod: bool = False,
    v2: bool = False,
):
    """Export tiltseries to Warp."""
    ts_path = ts.path
    mdoc_path = ts.mdoc
    xf_path = ts_path.with_suffix(".xf")
    ta_solution_path = ts.path.parent / "taSolution.log"
    tlt_file = ts_path.with_suffix(".tlt")
    rawtlt_file = ts_path.with_suffix(".rawtlt")
    required_files = [ts_path, mdoc_path, xf_path]
    if imod:
        required_files.append(ta_solution_path)

    # Check that all files are present
    for file in required_files:
        if not file.is_file():
            click.echo(f"Required file {file} not found for {ts.path.name}.", err=True)
            return
    if not (tlt_file.is_file() or rawtlt_file.is_file()):
        click.echo(
            f"Required tlt or rawtlt file not found for {ts.path.name}.", err=True
        )
        return
    # Create imod subdirectory
    # copy alignment files (to protect against later modification)
    ts_dir = project_dir / "imod" / ts.path.stem
    ts_dir.mkdir()

    shutil.copy(xf_path, ts_dir)
    if imod:
        shutil.copy(ta_solution_path, ts_dir)
    if tlt_file.is_file():
        shutil.copy(tlt_file, ts_dir)
    elif rawtlt_file.is_file():
        shutil.copy(rawtlt_file, ts_dir / ts.name.with_suffix(".tlt"))

    if v2:
        # invert tilt-angles in tlt file (done during import in Warp 1.X)
        invert_tlt_files(ts_dir)
        # copy frames to frames subfolder instead of main folder
        frame_target_dir = project_dir / "frames"
    else:
        # tilt images go to warp root directory
        frame_target_dir = project_dir

    # Read mdoc, fix date bug
    mdoc = mdocfile.read(ts.mdoc)
    mdoc = mdocfile.downgrade_DateTime(mdoc)

    if frames_strategy[0] in ("copy", "link"):
        frames_mode, frames_dir = frames_strategy
        try:
            written_files = _link_or_copy_frames(
                mdoc, frames_dir, frame_target_dir, frames_mode
            )
        except ValueError as e:
            click.echo(f"Error processing frames for {ts.name}: {e}", err=True)
            return
    elif frames_strategy[0] == "extract":
        written_files = _extract_frames(ts, mdoc, frame_target_dir)
    else:
        written_files = []
    if len(written_files) > 0 and not len(mdoc["sections"]) == len(written_files):
        click.echo(
            f"Error: mismatch between mdoc entries and frames in {ts.name}", err=True
        )
        return
    for subframe_path, section in zip(written_files, mdoc["sections"]):
        section["SubFramePath"] = "X:\\WarpDir\\" + subframe_path.name
    mdocfile.write(mdoc, project_dir / "mdoc" / f"{ts.path.stem}.mdoc")


def _get_subframes(mdoc: dict, src_dir: Path) -> List[Path]:
    if not all("SubFramePath" in section for section in mdoc["sections"]):
        raise ValueError("No SubFramePath in mdoc")
    subframes: List[Path] = []
    for section in mdoc["sections"]:
        subframes.append(
            mdocfile.find_relative_path(
                Path(src_dir),
                Path(section.get("SubFramePath", "").replace("\\", path.sep)),
            )
        )
    return subframes


def _link_or_copy_frames(
    mdoc: dict, src_dir: Path, target_dir: Path, mode: Literal["link", "copy"]
) -> List[Path]:
    # Check, whether all tlts have SubFrameImages
    subframes = _get_subframes(mdoc, src_dir)
    written_files: List[Path] = []
    for file in subframes:
        target = target_dir / file.name
        source = file if file.is_absolute() else Path.cwd() / file
        if mode == "link":
            os.symlink(os.path.relpath(source, start=target.parent), target)
        else:
            shutil.copy(source, target)
        written_files.append(target)
    return written_files


def _extract_frames(ts: TiltSeries, mdoc: dict, target_dir: Path):
    try:
        subprocess.run(
            [
                "newstack",
                "-split",
                "0",
                "-append",
                "mrc",
                "-in",
                ts.path,
                target_dir / (ts.path.stem + "_sec_"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo("Command failed:", e.returncode, err=True)
        click.echo("stdout:", e.stdout, err=True)
        click.echo("stderr:", e.stderr, err=True)
        return
    # Create mdoc with SubFramePath and save it to the mdoc subdirectory
    written_files = sorted(target_dir.glob(ts.path.stem + "_sec_[0-9][0-9].mrc"))
    # Check that mdoc has as many sections as there are tilt images
    return written_files


def batch_parser(input_files: List, batch: bool):
    """Batch-parse tiltseries to work on from textfile."""
    input_files_parsed = []

    # Check whether you already received a correctly formatted list of TiltSeries
    if isinstance(input_files[0], TiltSeries):
        return input_files

    if isinstance(input_files[0], list):
        return input_files[0]

    # Parse input files
    if batch:
        with open(input_files[0], "r+") as f:
            for line in f:
                input_files_parsed.append(line.strip("\n"))

    else:
        input_files_parsed = input_files

    # Convert to list of tiltseries
    ts_list = convert_input_to_TiltSeries(input_files_parsed)

    return ts_list


def ctfplotter_aretomo_export(ts: TiltSeries):
    """Exclude AreTomo Excludeview from ctfplotter file."""
    exclude = parse_darkimgs(ts)

    # If required run ctfplotter or just return results of previous run.
    # Perform on original TiltSeries to avoid interpolation artefacts.
    ctffile = parse_ctfplotter(run_ctfplotter(ts, False))

    # ctfplotter is 1-indexed, excludeviews are 0-indexed
    ctffile_cleaned = ctffile[
        ~ctffile.view_start.isin([str(ele + 1) for ele in exclude])
    ]

    # Write to AreTomo export folder
    ctf_out = write_ctfplotter(
        ctffile_cleaned,
        ts.path.parent / f"{ts.path.stem}_ali_Imod" / f"{ts.path.stem}_ali.defocus",
    )

    return ctf_out


def tomotwin_prep(tomotwin_dir, ts_list, thickness, uid, bin_up=True):
    """Prepare list of TS for TomoTwin."""
    tomotwin_dir = Path(tomotwin_dir)
    tomo_dir = tomotwin_dir / "tomo"

    if not path.isdir(tomotwin_dir):
        os.mkdir(tomotwin_dir)

    if not path.isdir(tomo_dir):
        os.mkdir(tomo_dir)

    for ts in ts_list:
        # bin to about 10 Apix, prefer round binning to avoid artifacts
        if bin_up is True:
            binning = math.ceil(10 / ts.angpix / 2) * 2
        else:
            binning = math.floor(10 / ts.angpix / 2) * 2

        ts_ali = align_with_imod(ts, True, False, binning=binning)

        rec = tomogram.Tomogram.from_tiltseries(
            ts_ali,
            bin=1,
            sirt=0,
            thickness=round(thickness / binning),
            convert_to_byte=False,
        )

        unique_name = f"{uid}_{ts.path.parent.absolute().name}.mrc"

        os.symlink(rec.path.absolute(), tomo_dir / unique_name)


def invert_tlt_files(ts_dir: Path):
    """Invert tilt angles in tlt file for WarpTools."""
    for tlt in ts_dir.glob("*.tlt"):
        tlt_inverted = []

        with open(tlt) as file:
            data = file.readlines()

        for line in data:
            # Remove whitespace, produced by imod
            line = line.strip()

            if len(line) == 0:
                continue

            elif line.startswith("-"):
                tlt_inverted.append(line[1:])

            else:
                tlt_inverted.append("-" + line)

        with open(tlt, "w+") as file:
            for line in tlt_inverted:
                file.write(f"{line}\n")

    return
