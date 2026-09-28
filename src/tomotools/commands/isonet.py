import multiprocessing
import multiprocessing.synchronize
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from functools import partial
from importlib.util import find_spec
from pathlib import Path
from typing import Self
from os import path

import click
import mrcfile
import pandas as pd
import starfile

from tomotools.utils import sta_util
from tomotools.utils.tiltseries import TiltSeries, run_ctfplotter

WARPYLIB_AVAILABLE = (
    find_spec("torch_projectors") is not None
    and find_spec("warpylib") is not None
    and find_spec("torch") is not None
)

warnings.filterwarnings(
    "ignore",
    message="To copy construct from a tensor",
    category=UserWarning,
)


@dataclass
class WarpSettings:
    path: Path
    processing_path: Path
    binning: float
    unbin_angpix: float
    dimensions_px: tuple[int, int, int]

    @classmethod
    def read(cls, path: Path) -> "Self":
        root = ET.parse(path).getroot()
        processing_folder = root.find("./Import/Param[@Name='ProcessingFolder']").get(
            "Value"
        )
        binning = float(root.find("./Import/Param[@Name='BinTimes']").get("Value"))
        unbin_angpix = float(
            root.find("./Import/Param[@Name='PixelSize']").get("Value")
        )
        dims = tuple(
            int(root.find(f"./Tomo/Param[@Name='Dimensions{axis}']").get("Value"))
            for axis in ("X", "Y", "Z")
        )
        return cls(
            path=path,
            processing_path=(Path(path).parent / processing_folder).resolve(),
            binning=binning,
            unbin_angpix=unbin_angpix,
            dimensions_px=dims,  # pyright: ignore[reportArgumentType]
        )

    def bin_angpix(self) -> float:
        return self.unbin_angpix * (2**self.binning)

    def dimension_angstrom(self) -> tuple[float, float, float]:
        return tuple(dim * self.unbin_angpix for dim in self.dimensions_px)  # pyright: ignore[reportReturnType]


_read_semaphore: multiprocessing.synchronize.Semaphore
_reconstruct_semaphore: multiprocessing.synchronize.Semaphore
_write_semaphore: multiprocessing.synchronize.Semaphore


def _init_worker(
    read_semaphore: "multiprocessing.synchronize.Semaphore",
    reconstruct_semaphore: "multiprocessing.synchronize.Semaphore",
    write_semaphore: "multiprocessing.synchronize.Semaphore",
):
    """Share semaphores limiting concurrent read/reconstruct/write calls with pool workers."""
    global _read_semaphore, _reconstruct_semaphore, _write_semaphore
    _read_semaphore = read_semaphore
    _reconstruct_semaphore = reconstruct_semaphore
    _write_semaphore = write_semaphore


@click.command()
@click.option(
    "--settings",
    "settings_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to a warp_tiltseries.settings file (supplies the processing folder and tomogram dimensions).",
)
@click.option(
    "--isonet-dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Output folder for IsoNet2 processing.",
)
@click.option(
    "-b",
    "--bin",
    "binning",
    type=int,
    required=True,
    help="Binning level for reconstructions.",
)
@click.option(
    "--read-jobs",
    type=int,
    default=1,
    show_default=True,
    help="Number of concurrent image-loading (ts.load_images) operations.",
)
@click.option(
    "--reconstruct-jobs",
    type=int,
    default=1,
    show_default=True,
    help="Number of concurrent reconstruction (ts.reconstruct_full) operations.",
)
@click.option(
    "--write-jobs",
    type=int,
    default=1,
    show_default=True,
    help="Number of concurrent MRC-writing (mrcfile.write) operations.",
)
@click.argument(
    "tomo_xmls",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    nargs=-1,
)
def warp2isonet(
    settings_path: Path,
    isonet_dir: Path,
    binning: int,
    read_jobs: int,
    reconstruct_jobs: int,
    write_jobs: int,
    tomo_xmls: tuple[Path, ...] | list[Path],
):
    """Export even/odd tomograms for IsoNet2."""
    settings = WarpSettings.read(settings_path)
    tomo_dir = isonet_dir / "tomo"
    tomo_dir.mkdir(parents=True, exist_ok=True)

    if not tomo_xmls:
        tomo_xmls = sorted(settings.processing_path.glob("*.xml"))
    tomo_xmls = filter_tomo_xmls(tomo_xmls)
    if len(tomo_xmls) == 0:
        click.echo("No tomograms found in processing folder.", err=True)
        return

    worker = partial(
        make_noCTF_EVNODD,
        binning=binning,
        tomo_dir=tomo_dir,
        warp_settings=settings,
    )

    mp_context = multiprocessing.get_context("spawn")
    read_semaphore = mp_context.Semaphore(read_jobs)
    reconstruct_semaphore = mp_context.Semaphore(reconstruct_jobs)
    write_semaphore = mp_context.Semaphore(write_jobs)

    with (
        mp_context.Pool(
            processes=read_jobs + reconstruct_jobs + write_jobs,
            initializer=_init_worker,
            initargs=(read_semaphore, reconstruct_semaphore, write_semaphore),
        ) as pool,
        click.progressbar(
            pool.imap_unordered(worker, tomo_xmls),
            length=len(tomo_xmls),
            label="Reconstructing...",
            show_pos=True,
        ) as bar,
    ):
        output_star_list = list(bar)

    output_star = pd.DataFrame().from_records(output_star_list)

    output_star["rlnIndex"] = output_star.index + 1
    output_star["rlnVoltage"] = 300
    output_star["rlnSphericalAberration"] = 2.7
    output_star["rlnAmplitudeContrast"] = 0.07
    output_star["rlnDeconvTomoName"] = "None"
    output_star["rlnMaskBoundary"] = "None"
    output_star["rlnMaskName"] = "None"
    output_star["rlnBoxFile"] = "None"
    output_star["rlnCorrectedTomoName"] = "None"
    output_star["rlnDenoisedTomoName"] = "None"
    output_star["rlnNumberSubtomo"] = round(6000 / len(output_star.index))

    starfile.write(output_star, isonet_dir / f"isonet2_tomos_bin_{binning}.star")


def filter_tomo_xmls(xmls: Iterable[Path]):
    """Filter a list of xml files to only include tomogram xmls."""
    tomo_list: list[Path] = []
    for xml in xmls:
        if ET.parse(xml).getroot().tag == "TiltSeries":
            tomo_list.append(xml)
    return tomo_list


def make_noCTF_EVNODD(
    ts_path: Path,
    binning: int,
    tomo_dir: Path,
    warp_settings: WarpSettings,
):
    """Make EVN/ODD tomogram without any CTF modulation.

    Inputs:
        ts_path (Path): path to the TiltSeries file.
        binning (int): binning level to reconstruct at.
        isonet_root_dir (Path): output path for all IsoNet2 processing.
        dim_px (Tuple[int,int,int]): xyz extent of tomogram in unbinned pixels.
        warp_settings (WarpSettings): warp settings object with processing folder and tomogram dimensions.

    Returns:
        tomo_values ({}): dict with all relevant values for IsoNet2 star file.
    """
    import torch
    from warpylib import TiltSeries

    # reset CTF information in the memory to get tomogram without any correction
    ts = TiltSeries(str(ts_path))
    y_offset = ts.level_angle_y

    defocus_um = ts.ctf.get_copy().defocus
    t_max = ts.max_tilt + y_offset
    t_min = ts.min_tilt + y_offset

    # set global CTF variables to disable CTF
    ts.ctf.amplitude = 1
    ts.ctf.cc = 0
    ts.ctf.cs = 0
    ts.ctf.defocus = 0
    ts.ctf.defocus_delta = 0

    ts.grid_ctf_defocus.values = torch.zeros(  # pyright: ignore[reportPossiblyUnboundVariable]
        ts.grid_ctf_defocus.flat_values.shape
    )
    ts.grid_ctf_defocus_delta.values = torch.zeros(  # pyright: ignore[reportPossiblyUnboundVariable]
        ts.grid_ctf_defocus_delta.flat_values.shape
    )

    out_angpix = binning * warp_settings.bin_angpix()
    # Tomogram dimensions in the xml file are missing the Z dimension
    # so it's calculated from the warp settings
    ts.volume_dimensions_physical = torch.tensor(warp_settings.dimension_angstrom())
    # reconstruct with EVN/ODD
    evn_path = tomo_dir / f"{ts_path.name[:-4]}_even.mrc"
    odd_path = tomo_dir / f"{ts_path.name[:-4]}_odd.mrc"

    with _read_semaphore:
        _, ts_evn, ts_odd = ts.load_images(
            original_pixel_size=warp_settings.bin_angpix(),
            desired_pixel_size=out_angpix,
            load_half_averages=True,
        )

    with _reconstruct_semaphore:
        tomo_evn = ts.reconstruct_full(
            tilt_data=ts_evn,
            pixel_size=out_angpix,
            volume_dimensions_physical=ts.volume_dimensions_physical,
        )
        tomo_odd = ts.reconstruct_full(
            tilt_data=ts_odd,
            pixel_size=out_angpix,
            volume_dimensions_physical=ts.volume_dimensions_physical,
        )

    with _write_semaphore:
        mrcfile.write(
            evn_path, data=tomo_evn.numpy(), overwrite=True, voxel_size=out_angpix
        )
        mrcfile.write(
            odd_path, data=tomo_odd.numpy(), overwrite=True, voxel_size=out_angpix
        )

    # save values to starfile
    tomo_values = {
        "rlnTomoName": f"{ts_path.name[:-4]}",
        "rlnTomoReconstructedTomogramHalf1": tomo_dir.stem / evn_path.name,
        "rlnTomoReconstructedTomogramHalf2": tomo_dir.stem / odd_path.name,
        "rlnPixelSize": out_angpix,
        "rlnDefocus": int(defocus_um * 10000),
        "rlnTiltMin": round(t_min),
        "rlnTiltMax": round(t_max),
    }

    ts.save_meta(tomo_dir / f"{ts_path.name[:-4]}.xml")
    return tomo_values


@click.command()
@click.option(
    "-d",
    "--thickness",
    default=3000,
    show_default=True,
    help="Tomogram thickness in unbinned pixels.",
)
@click.option(
    "-b",
    "--bin",
    "binning",
    required=True,
    type=int,
    help="Binning level for reconstruction.",
)
@click.option(
    "--prefix",
    default="",
    show_default=True,
    help="Prefix prepended to output filenames (e.g. session ID).",
)
@click.option(
    "--aretomo",
    is_flag=True,
    default=False,
    show_default=True,
    help="Align with AreTomo (fresh alignment) instead of imod (requires previous .xf/.tlt).",
)
@click.argument("input_files", nargs=-1)
@click.argument("isonet_dir", nargs=1)
def imod2isonet(
    thickness: int,
    binning: int,
    prefix: str,
    aretomo: bool,
    input_files: tuple[str, ...],
    isonet_dir: str,
):
    """Export even/odd tomograms for IsoNet2.

    Takes as input several tilt series folders obtained after processing with
    tomotools (imod-aligned by default, or AreTomo-aligned with --aretomo).
    EVN/ODD half-stacks must be present alongside the main aligned stack.

    Pipeline per tilt series (two passes):

    \b
    Pass 1 — CTF pre-flight (interactive):
      Check/run ctfplotter on every tilt series before any reconstruction starts.
    Pass 2 — Align, dose-filter, reconstruct:
      Align → dose-filter → WBP reconstruction (no CTF correction) → symlink halves.

    Writes an IsoNet2-compatible RELION STAR file to ISONET_DIR.
    """
    # Collect all tilt series
    ts_list: list[TiltSeries] = []
    for input_file in input_files:
        ts_list.extend(TiltSeries.from_path(Path(input_file)))

    if not ts_list:
        click.echo("No tilt series found in the provided input paths.", err=True)
        return

    # Drop any TS that lack EVN/ODD halves
    valid_ts: list[TiltSeries] = []
    for ts in ts_list:
        if not ts.is_split:
            click.echo(
                f"Warning: {ts.path.parent.name} has no EVN/ODD halves — skipping.",
                err=True,
            )
        else:
            valid_ts.append(ts)

    if not valid_ts:
        click.echo("No tilt series with EVN/ODD halves found. Aborting.", err=True)
        return

    # --- Pass 1: CTF pre-flight (all interactive work before reconstruction) ---
    click.echo(f"Running ctfplotter on {len(valid_ts)} tilt series...")
    ctf_ok: list[TiltSeries] = []
    for ts in valid_ts:
        # First, check whether all defocus files are there
        if not path.isfile(ts.path.with_suffix(".defocus")):
            ctf_ok.append(ts)
        else:
            run_ctfplotter(ts, overwrite=False)
            ctf_ok.append(ts)

    if not ctf_ok:
        click.echo("No tilt series passed CTF check. Aborting.", err=True)
        return

    # --- Pass 2: align, dose-filter, reconstruct ---
    sta_util.isonet_prep(
        isonet_dir=Path(isonet_dir),
        ts_list=ctf_ok,
        thickness=thickness,
        binning=binning,
        prefix=prefix,
        aretomo=aretomo,
    )
