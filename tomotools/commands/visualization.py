from os import path

import click
import mrcfile
import numpy as np

from tomotools.utils import mathutil


@click.command()
@click.option(
    "--defocus",
    help="(Central) defocus in um. Positive values denote underfocus.",
)
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
@click.argument("input_files", nargs=-1, required=True)
def deconv(
    defocus,
    snrfalloff,
    deconvstrength,
    hpnyquist,
    phaseshift,
    phaseflipped,
    input_files,
):
    """Deconvolve your tomogram or list of tomograms.

    Python implementation Dimitri Tegunovs tom_deconv.m.

    The input file should be a reconstructed tomogram.
    AngPix is automatically read from the header.

    Output file will be an mrc in the same folder, with added _deconv suffix.

    Original Script at https://github.com/dtegunov/tom_deconv/.
    """
    # TODO: automatically read defocus out of ctfplotter file?
    if defocus is None:
        raise NotImplementedError(
            "Automated defocus determination not yet implemented."
        )

    for input_file in input_files:
        with mrcfile.open(input_file) as mrc:
            angpix = float(mrc.voxel_size.x)
            volume_in = mrc.data

        wiener = mathutil.wiener(
            angpix,
            float(defocus),
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

        output_file = f"{path.splitext(input_file)[0]}_deconv.mrc"

        with mrcfile.open(output_file, mode="w+") as mrc:
            mrc.set_data(vol_deconv)
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()
