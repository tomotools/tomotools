import math
import os
import shutil
import subprocess
from os import path
from pathlib import Path
from typing import Literal

import click
import mrcfile

from tomotools.utils import mdocfile, tomogram
from tomotools.utils.tiltseries import (
    TiltSeries,
    align_with_imod,
    aretomo_executable,
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
        aretomo_exe = aretomo_executable()
        if aretomo_exe is None:
            raise FileNotFoundError("AreTomo executable not found.")
        subprocess.run(
            [
                aretomo_exe,
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
    frames_strategy: (
        tuple[Literal["skip"], None]
        | tuple[Literal["extract"], None]
        | tuple[Literal["copy"], Path]
        | tuple[Literal["link"], Path]
    ),
    imod: bool = False,
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
        shutil.copy(rawtlt_file, ts_dir / ts.path.with_suffix(".tlt").name)

    # invert tilt-angles in tlt file (done during import in Warp 1.X)
    invert_tlt_files(ts_dir)
    # copy frames to frames subfolder instead of main folder
    frame_target_dir = project_dir / "frames"

    # Read mdoc, fix date bug
    mdoc = mdocfile.read(ts.mdoc)
    mdoc = mdocfile.downgrade_DateTime(mdoc)

    frames_mode, frames_dir = frames_strategy
    match frames_mode:
        case "copy" | "link":
            assert frames_dir is not None
            try:
                written_files = _link_or_copy_frames(
                    mdoc, frames_dir, frame_target_dir, frames_mode
                )
            except ValueError as e:
                click.echo(f"Error processing frames for {ts.path.name}: {e}", err=True)
                return
        case "extract":
            written_files = _extract_frames(ts, mdoc, frame_target_dir)
        case "skip":
            written_files = []
    if len(written_files) > 0 and not len(mdoc["sections"]) == len(written_files):
        click.echo(
            f"Error: mismatch between mdoc entries and frames in {ts.path.name}",
            err=True,
        )
        return
    for subframe_path, section in zip(written_files, mdoc["sections"]):
        section["SubFramePath"] = "X:\\WarpDir\\" + subframe_path.name
    mdocfile.write(mdoc, project_dir / "mdoc" / f"{ts.path.stem}.mdoc")


def _get_subframes(mdoc: dict, src_dir: Path) -> list[Path]:
    if not all("SubFramePath" in section for section in mdoc["sections"]):
        raise ValueError("No SubFramePath in mdoc")
    subframes: list[Path] = []
    for section in mdoc["sections"]:
        subframe_path = mdocfile.find_relative_path(
            Path(src_dir),
            Path(section.get("SubFramePath", "").replace("\\", path.sep)),
        )
        if subframe_path is None:
            raise ValueError(
                f"Could not find relative path for SubFramePath:"
                f"{section.get('SubFramePath')}"
            )
        subframes.append(subframe_path)
    return subframes


def _link_or_copy_frames(
    mdoc: dict, src_dir: Path, target_dir: Path, mode: Literal["link", "copy"]
) -> list[Path]:
    # Check, whether all tlts have SubFrameImages
    subframes = _get_subframes(mdoc, src_dir)
    written_files: list[Path] = []
    for file in subframes:
        target = target_dir / file.name
        source = file if file.is_absolute() else Path.cwd() / file
        if mode == "link":
            os.symlink(os.path.relpath(source, start=target.parent), target)
        else:
            shutil.copy(source, target)
        written_files.append(target)
    return written_files


def _extract_frames(ts: TiltSeries, mdoc: dict, target_dir: Path) -> list[Path]:
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
    return sorted(target_dir.glob(ts.path.stem + "_sec_[0-9][0-9].mrc"))


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
        ctffile_cleaned,  # pyright: ignore[reportArgumentType]
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
                tlt_inverted.append(line.removeprefix("-"))

            else:
                tlt_inverted.append("-" + line)

        with open(tlt, "w+") as file:
            for line in tlt_inverted:
                file.write(f"{line}\n")

    return
