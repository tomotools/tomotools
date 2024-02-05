import json
import os
import pickle
import tarfile
from glob import glob
from os import path
from os.path import isdir, join

import click
import mrcfile
import numpy as np

from tomotools.utils import mathutil
from tomotools.utils.tomogram import convert_input_to_Tomogram
from tomotools.utils.util import num_gpus


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

def deconv(defocus,
           snrfalloff,
           deconvstrength,
           hpnyquist,
           phaseshift,
           phaseflipped,
           input_files):
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

        wiener = mathutil.wiener(angpix,
                                 float(defocus),
                                 float(snrfalloff),
                                 float(deconvstrength),
                                 float(hpnyquist),
                                 phaseflipped,
                                 int(phaseshift))

        # In mcrfile convention, the array is ordered zyx!
        sx = int(-1*np.floor(volume_in.shape[2]/2))
        fx = sx + volume_in.shape[2] -1

        sy = int(-1*np.floor(volume_in.shape[1]/2))
        fy = sy + volume_in.shape[1] -1

        sz = int(-1*np.floor(volume_in.shape[0]/2))
        fz = sz + volume_in.shape[0] -1

        gridz,gridy,gridx = np.mgrid[sz:fz+1,sy:fy+1,sx:fx+1]

        gridx = np.divide(gridx,np.abs(sx))
        gridy = np.divide(gridy,np.abs(sy))
        gridz = np.divide(gridz,np.maximum(1, np.abs(sz)))

        # Create input array with Euclidean distance from the center as cell value
        r = np.sqrt(np.square(gridx)+np.square(gridy)+np.square(gridz))

        del(gridx,gridy,gridz,sx,sy,sz,fx,fy,fz)

        r = np.minimum(1, r)
        r = np.fft.ifftshift(r)

        x = np.linspace(0,1,2048)

        ramp = np.interp(r,x,wiener)

        del(r)

        vol_deconv = np.real(np.fft.ifftn(np.fft.fftn(volume_in)*ramp))

        # Cast to single precision / float32 (maximum allowed by mrc standard)
        vol_deconv = vol_deconv.astype('float32')

        output_file = f'{path.splitext(input_file)[0]}_deconv.mrc'

        with mrcfile.open(output_file, mode = 'w+') as mrc:
            mrc.set_data(vol_deconv)
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()



@click.command()
@click.option(
    "--num_slices",
    type=int,
    default=1200,
    show_default=True,
    help="Number of sub-volume extracted per tomogram.",
)
@click.option(
    "--split",
    type=float,
    default=0.9,
    show_default=True,
    help="Training vs. validation split.",
)
@click.option(
    "--patch_shape",
    type=int,
    default=72,
    show_default=True,
    help="Size of sub-volumes for training. Should not be below 64.",
)
@click.option(
    "--tilt_axis",
    type=str,
    default="Y",
    show_default=True,
    help="Tilt-axis of the tomogram. Y is imod and AreTomo default.",
)
@click.option(
    "--n_normalization_samples",
    type=int,
    default=500,
    show_default=True,
    help="Number of sub-volumes extracted per tomogram for normalization.",
)
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
@click.argument(
    "output_path", type=click.Path(dir_okay=True, writable=True), default="./"
)
def cryocare_extract(
    num_slices,
    split,
    patch_shape,
    tilt_axis,
    n_normalization_samples,
    input_files,
    output_path,
):
    """Prepares for cryoCARE-denoising.

    Takes reconstructed tomograms or folders containing them as input.
    Must have EVN/ODD volumes associated!
    The training data will be saved in output_path.

    """
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule

    input_tomo = []
    input_evn = []
    input_odd = []

    if not isdir(output_path):
        os.mkdir(output_path)

    print("\n")

    # Convert all input_files into a list of Tomogram objects
    input_tomo = convert_input_to_Tomogram(input_files)

    for tomo in input_tomo:
        if tomo.is_split:
            input_evn.append(tomo.evn_path)
            input_odd.append(tomo.odd_path)

    print(f"Will extract from {len(input_evn)} tomograms. \n")

    dm = CryoCARE_DataModule()
    dm.setup(
        input_odd,
        input_evn,
        n_samples_per_tomo=num_slices,
        validation_fraction=(1.0 - split),
        sample_shape=[patch_shape] * 3,
        tilt_axis=tilt_axis,
        n_normalization_samples=n_normalization_samples,
    )
    dm.save(output_path)


@click.command()
@click.option("--epochs", type=int, default=100, show_default=True)
@click.option("--steps_per_epoch", type=int, default=200, show_default=True)
@click.option(
    "--batch_size",
    type=int,
    default=16,
    show_default=True,
    help="Increase if multiple GPUs are used. Try 32 or 64.",
)
@click.option(
    "--unet_kern_size",
    type=int,
    default=3,
    show_default=True,
    help="Convolution kernel size of the U-Net. Has to be odd.",
)
@click.option("--unet_n_depth", type=int, default=3, show_default=True)
@click.option(
    "--unet_n_first",
    type=int,
    default=16,
    show_default=True,
    help="Number of initial feature channels.",
)
@click.option("--learning_rate", type=float, default=0.0004, show_default=True)
@click.option(
    "--gpu",
    type=str,
    default=None,
    help="Specify which GPUs to use. Default: All GPUs.",
)
@click.argument("extraction_dir", type=click.Path(dir_okay=True, file_okay=False))
@click.argument(
    "training_dir", type=click.Path(dir_okay=True, file_okay=False), default="./"
)
@click.argument("model_name", type=str, default="model")
def cryocare_train(
    epochs,
    steps_per_epoch,
    batch_size,
    unet_kern_size,
    unet_n_depth,
    unet_n_first,
    learning_rate,
    gpu,
    extraction_dir,
    training_dir,
    model_name,
):
    """Trains a Noise2Noise model with cryoCARE.

    Can only be used after cryocare-extract was run.
    Takes the training data generated as an input.

    Optionally, the output path and the model name can be specified.
    """
    from cryocare.internals.CryoCARE import CryoCARE
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule
    from cryocare.scripts.cryoCARE_predict import set_gpu_id
    from csbdeep.models import Config

    if gpu is None:
        gpu_id = [int(i) for i in range(0, num_gpus())]

    else:
        # Turn GPU list into list of integers
        gpu_id = gpu.split(",")
        gpu_id = [int(gpu) for gpu in gpu_id]

    set_gpu_id({"gpu_id": gpu_id})

    dm = CryoCARE_DataModule()
    dm.load(extraction_dir)

    net_conf = Config(
        axes="ZYXC",
        train_loss="mse",
        train_epochs=epochs,
        train_steps_per_epoch=steps_per_epoch,
        train_batch_size=batch_size,
        unet_kern_size=unet_kern_size,
        unet_n_depth=unet_n_depth,
        unet_n_first=unet_n_first,
        train_tensorboard=False,
        train_learning_rate=learning_rate,
    )

    model = CryoCARE(net_conf, model_name, basedir=training_dir)

    history = model.train(dm.get_train_dataset(), dm.get_val_dataset())
    mean, std = dm.train_dataset.mean, dm.train_dataset.std

    with open(join(training_dir, model_name, "history.dat"), "wb+") as f:
        pickle.dump(history.history, f)

    norm = {"mean": float(mean), "std": float(std)}

    with open(join(training_dir, model_name, "norm.json"), "w") as fp:
        json.dump(norm, fp)

    with tarfile.open(join(training_dir, f"{model_name}.tar.gz"), "w:gz") as tar:
        tar.add(
            join(training_dir, model_name),
            arcname=path.basename(join(training_dir, model_name)),
        )


@click.command()
@click.option(
    "--tiles",
    type=(int, int, int),
    default=(1, 1, 1),
    show_default=True,
    help="Specify number of tiles.",
)
@click.option(
    "--gpu",
    default="0",
    type=str,
    help="Specify which GPUs to use (eg. 2,3).",
)
@click.option(
    "--model-path",
    type=click.Path(dir_okay=False, exists=True),
    default="./model.tar.gz",
    show_default=True,
    help="Specify the folder containing the model.",
)
@click.argument(
    "input_files",
    nargs=-1,
    type=click.Path(exists=True),
)
@click.argument("output", type=click.Path(dir_okay=True), default="./denoised")
def cryocare_predict(tiles, gpu, model_path, input_files, output):
    """Predicts denoised tomogram using cryoCARE.

    Takes tomograms or folder containing them with associated EVN/ODD halves \
    and the trained model as inputs.
    """
    import tempfile

    from cryocare.scripts.cryoCARE_predict import denoise, set_gpu_id

    # Parse input tomogram
    input_evn = []
    input_odd = []

    # Convert all input_files into a list of Tomogram objects
    input_tomo = convert_input_to_Tomogram(input_files)

    for tomo in input_tomo:
        if tomo.is_split:
            input_evn.append(tomo.evn_path)
            input_odd.append(tomo.odd_path)

    # Create output directory
    if not path.isdir(output):
        os.mkdir(output)

    # Take care of GPU stuff
    gpu_id = gpu.split(",")
    gpu_id = [int(gpu) for gpu in gpu_id]

    set_gpu_id({"gpu_id": gpu_id})

    # Extract model and denoise
    with tempfile.TemporaryDirectory() as tmpdirname:
        tar = tarfile.open(model_path, "r:gz")
        tar.extractall(tmpdirname)
        tar.close()

        config = {}
        config["even"] = input_evn
        config["odd"] = input_odd
        config["output"] = output
        config["n_tiles"] = list(tiles)

        config["model_name"] = os.listdir(tmpdirname)[0]
        config["path"] = join(tmpdirname)

        with open(join(tmpdirname, config["model_name"], "norm.json")) as f:
            norm_data = json.load(f)
            mean = norm_data["mean"]
            std = norm_data["std"]

        if isinstance(config["even"], list):
            all_even = tuple(config["even"])
            all_odd = tuple(config["odd"])
        elif os.path.isdir(config["even"]) and os.path.isdir(config["odd"]):
            all_even = glob(join(config["even"], "*.mrc"))
            all_odd = glob(join(config["odd"], "*.mrc"))
        else:
            all_even = [config["even"]]
            all_odd = [config["odd"]]

        for even, odd in zip(all_even, all_odd):
            out_filename = join(config["output"], os.path.basename(even))
            denoise(config, mean, std, even=even, odd=odd, output_file=out_filename)
