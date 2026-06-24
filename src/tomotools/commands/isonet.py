import gc
import os
import warnings
import xml.etree.ElementTree as ET
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

import click
import mrcfile
import pandas as pd
import starfile

WARPYLIB_AVAILABLE = (
    find_spec("torch_projectors") is not None
    and find_spec("warpylib") is not None
    and find_spec("torch") is not None
)

if TYPE_CHECKING:
    from warpylib import TiltSeries

warnings.filterwarnings(
    "ignore",
    message="To copy construct from a tensor",
    category=UserWarning,
)


@click.command()
@click.option(
    "--settings",
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
    type=int,
    required=True,
    help="Binning level for reconstructions.",
)
def warp2isonet(
    settings: Path,
    isonet_dir: Path,
    binning: int,
):
    """Export even/odd tomograms for IsoNet2."""
    processing_folder, dim_px = read_warp_settings(settings)

    isonet_dir.mkdir(parents=True, exist_ok=True)

    tomo_list = parse_tomos(processing_folder)
    if len(tomo_list) == 0:
        click.echo("No tomograms found in processing folder.", err=True)
        return

    output_star_list = []

    with click.progressbar(
        tomo_list,
        label="Reconstructing...",
        show_pos=True,
        item_show_func=lambda t: t.name if t is not None else "",
    ) as bar:
        for tomo in bar:
            particle_star = make_noCTF_EVNODD(tomo, binning, isonet_dir, dim_px=dim_px)
            output_star_list.append(particle_star)

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


def read_warp_settings(
    settings_path: Path,
) -> tuple[Path, tuple[int, int, int]]:
    """Read ProcessingFolder and Tomo Dimensions(X,Y,Z) from a warp_tiltseries.settings file.

    The ProcessingFolder is resolved relative to the settings file's parent directory.
    """
    root = ET.parse(settings_path).getroot()
    processing_folder = root.find("./Import/Param[@Name='ProcessingFolder']").get(
        "Value"
    )
    dims = tuple(
        int(root.find(f"./Tomo/Param[@Name='Dimensions{axis}']").get("Value"))
        for axis in ("X", "Y", "Z")
    )
    return (Path(settings_path).parent / processing_folder).resolve(), dims


def parse_tomos(processing_folder: Path):
    """Return a list of TiltSeries objects from a processing_path.

    Inputs:
        processing_folder (Path): folder with WarpTools processing results.

    Returns:
        tomo_list ([]): list containing TiltSeries objects for all tomograms in folder.
    """
    from warpylib import TiltSeries

    tomo_list = []

    for tomo in processing_folder.glob("*.xml"):
        ts = TiltSeries(str(tomo))

        tomo_list.append(ts)

    return tomo_list


def make_noCTF_EVNODD(
    ts: "TiltSeries",
    binning: int,
    isonet_root_dir: Path,
    dim_px: tuple[int, int, int] = (4092, 5760, 3000),
):
    """Make EVN/ODD tomogram without any CTF modulation.

    Inputs:
        ts (TiltSeries): warpylib TiltSeries to work on.
        binning (int): binning level to reconstruct at.
        isonet_root_dir (Path): output path for all IsoNet2 processing.
        dim_px (Tuple[int,int,int]): xyz extent of tomogram in unbinned pixels.

    Returns:
        tomo_values ({}): dict with all relevant values for IsoNet2 star file.
    """
    import torch

    # prepare output folders
    tomo_dir = isonet_root_dir / "tomo"

    if not os.path.isdir(tomo_dir):
        os.mkdir(tomo_dir)

    # reset CTF information in the memory to get tomogram without any correction
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

    # generate output pixel sizes and tomogram dimensions
    orig_angpix = ts.ctf.pixel_size
    out_angpix = orig_angpix * binning

    dim_a = torch.tensor(  # pyright: ignore[reportPossiblyUnboundVariable]
        [dim_px[0] * orig_angpix, dim_px[1] * orig_angpix, dim_px[2] * orig_angpix],
        dtype=torch.float32,  # pyright: ignore[reportPossiblyUnboundVariable]
    )

    ts.volume_dimensions_physical = dim_a

    # reconstruct with EVN/ODD
    evn_path = tomo_dir / f"{ts.name[:-4]}_even.mrc"
    odd_path = tomo_dir / f"{ts.name[:-4]}_odd.mrc"

    _, ts_evn, ts_odd = ts.load_images(
        original_pixel_size=orig_angpix,
        desired_pixel_size=out_angpix,
        load_half_averages=True,
    )
    tomo_evn = ts.reconstruct_full(
        tilt_data=ts_evn, pixel_size=out_angpix, volume_dimensions_physical=dim_a
    )

    mrcfile.write(
        evn_path, data=tomo_evn.numpy(), overwrite=True, voxel_size=out_angpix
    )

    tomo_odd = ts.reconstruct_full(
        tilt_data=ts_odd, pixel_size=out_angpix, volume_dimensions_physical=dim_a
    )

    mrcfile.write(
        odd_path, data=tomo_odd.numpy(), overwrite=True, voxel_size=out_angpix
    )

    # save values to starfile
    tomo_values = {
        "rlnTomoName": f"{ts.name[:-4]}",
        "rlnTomoReconstructedTomogramHalf1": evn_path,
        "rlnTomoReconstructedTomogramHalf2": odd_path,
        "rlnPixelSize": out_angpix,
        "rlnDefocus": int(defocus_um * 10000),
        "rlnTiltMin": round(t_min),
        "rlnTiltMax": round(t_max),
    }

    ts.save_meta(tomo_dir / f"{ts.name[:-4]}.xml")

    del ts_evn, ts_odd, tomo_evn, tomo_odd
    gc.collect()

    return tomo_values
