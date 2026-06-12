from os import path
from pathlib import Path

import click
import mrcfile
import numpy as np

from tomotools.utils import mathutil, tiltseries, tomogram


@click.command()
@click.option(
    "--snrfalloff",
    default=1.0,
    show_default=True,
    help="How fast the SNR falls off - 1.0 or 1.2 usually",
)
@click.option(
    "--deconvstrength",
    default=1.0,
    show_default=True,
    help="Deconvolution strength, linked to SNR. 1 for SNR 1000, 0.67 for SNR 100, ...",
)
@click.option(
    "--hpnyquist",
    default=0.02,
    show_default=True,
    help="Fraction of Nyquist frequency to be cut off on the lower end.",
)
@click.option(
    "--phaseshift", default=0, show_default=True, help="Phase shift in degrees"
)
@click.option("--phaseflipped", is_flag=True, help="Data has been phase-flipped")
@click.argument(
    "input_files",
    nargs=-1,
    type=click.Path(file_okay=True, dir_okay=True, path_type=Path),
    required=True,
)
def deconv(
    snrfalloff: float,
    deconvstrength: float,
    hpnyquist: float,
    phaseshift: int,
    phaseflipped: bool,
    input_files: tuple[Path],
):
    """Deconvolve your tomogram or list of tomograms.

    Python implementation Dimitri Tegunovs tom_deconv.m.

    The input file should be a reconstructed tomogram.
    AngPix is automatically read from the header.
    CTF will be determined using imod ctfplotter.

    Output file will be an mrc in the same folder, with added _deconv suffix.

    Original Script at https://github.com/dtegunov/tom_deconv/.
    """

    input_tomo = tomogram.convert_input_to_Tomogram(list(input_files))

    ts_list = tiltseries.convert_input_to_TiltSeries(
        tomo.path.parent for tomo in input_tomo
    )

    for ts_in in ts_list:
        # Test, whether .defocus file is found
        if not path.isfile(ts_in.path.with_suffix(".defocus")):
            tiltseries.run_ctfplotter(ts_in, True)

    for tomo, ts_in in zip(input_tomo, ts_list):
        angpix = tomo.angpix

        with mrcfile.open(tomo.path) as mrc:
            volume_in = mrc.data

        defocus = tiltseries.parse_ctfplotter(ts_in.path.with_suffix(".defocus"))

        middle_defocus = (
            float(defocus.iloc[round(len(defocus.index) / 2)].df_1_nm.strip()) / 1000
        )

        wiener = mathutil.wiener(
            angpix,
            float(middle_defocus),
            float(snrfalloff),
            float(deconvstrength),
            float(hpnyquist),
            phaseflipped,
            int(phaseshift),
        )

        # In mcrfile convention, the array is ordered zyx!
        sx = int(-1 * np.floor(volume_in.shape[2] / 2))
        fx = sx + volume_in.shape[2] - 1

        sy = int(-1 * np.floor(volume_in.shape[1] / 2))
        fy = sy + volume_in.shape[1] - 1

        sz = int(-1 * np.floor(volume_in.shape[0] / 2))
        fz = sz + volume_in.shape[0] - 1

        gridz, gridy, gridx = np.mgrid[sz : fz + 1, sy : fy + 1, sx : fx + 1]

        gridx = np.divide(gridx, np.abs(sx))
        gridy = np.divide(gridy, np.abs(sy))
        gridz = np.divide(gridz, np.maximum(1, np.abs(sz)))

        # Create input array with Euclidean distance from the center as cell value
        r = np.sqrt(np.square(gridx) + np.square(gridy) + np.square(gridz))

        del (gridx, gridy, gridz, sx, sy, sz, fx, fy, fz)

        r = np.minimum(1, r)
        r = np.fft.ifftshift(r)

        x = np.linspace(0, 1, 2048)

        ramp = np.interp(r, x, wiener)

        del r

        vol_deconv = np.real(np.fft.ifftn(np.fft.fftn(volume_in) * ramp))

        # Cast to single precision / float32 (maximum allowed by mrc standard)
        vol_deconv = vol_deconv.astype("float32")

        with mrcfile.open(
            tomo.path.parent / f"{tomo.path.stem}_deconv.mrc", mode="w+"
        ) as mrc:
            mrc.set_data(vol_deconv)
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()
