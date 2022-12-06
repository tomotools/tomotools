import os
import click
import pickle
import json
import tarfile

from os import path
from os.path import isdir, join
from pathlib import Path
from glob import glob

from tomotools.utils.tomogram import Tomogram, convert_input_to_Tomogram
from tomotools.utils.util import num_gpus

@click.command()
@click.option('--num_slices', type=int, default=1200, show_default=True, help='Number of sub-volume extracted per tomogram.')
@click.option('--split', type=float, default=0.9, show_default=True, help='Training vs. validation split.')
@click.option('--patch_shape', type=int, default=72, show_default=True, help='Size of sub-volumes for training. Should not be below 64.')
@click.option('--tilt_axis', type=str, default='Y', show_default=True, help='Tilt-axis of the tomogram. Used for splitting into training/validation. Y is imod and AreTomo default.')
@click.option('--n_normalization_samples', type=int, default=500, show_default=True, help='Number of sub-volumes extracted per tomogram to calculate mean and SD for normalization.')
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.argument('output_path', type=click.Path(dir_okay=True, writable=True), default='./')

def cryocare_extract(num_slices, split, patch_shape, tilt_axis, n_normalization_samples, input_files, output_path):
    """ Prepares for cryoCARE-denoising. 
    
    Takes reconstructed tomograms or folders containing them as input. Must have EVN/ODD volumes associated!
    The training data will be saved in output_path.   
    
    """
    
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule
    
    input_tomo = list()
    input_evn = list()
    input_odd = list()
    
    if not isdir(output_path):
        os.mkdir(output_path)
    
    # Convert all input_files into a list of Tomogram objects
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_tomo.append(Tomogram(Path(input_file)))
        elif input_file.is_dir():
            input_tomo += ([Tomogram(Path(file))for file in glob(join(input_file, '*_rec_bin_[0-9].mrc'))])
            
    for tomo in input_tomo:
        if path.isfile(tomo.path.with_name(f'{tomo.path.stem}_EVN.mrc')) and path.isfile(tomo.path.with_name(f'{tomo.path.stem}_ODD.mrc')):
            tomo = tomo.with_split_files(tomo.path.with_name(f'{tomo.path.stem}_EVN.mrc'), tomo.path.with_name(f'{tomo.path.stem}_ODD.mrc'))
            input_evn.append(tomo.evn_path)
            input_odd.append(tomo.odd_path)
            print(f'Found reconstruction {tomo.path} with EVN and ODD stacks.')
        else:
            print(f'No EVN/ODD reconstructions found for {tomo.path}. Skipping.')
    
    dm = CryoCARE_DataModule()
    dm.setup(input_odd, input_evn, n_samples_per_tomo=num_slices,
             validation_fraction=(1.0 - split), sample_shape=[patch_shape]*3,
             tilt_axis=tilt_axis, n_normalization_samples=n_normalization_samples)
    dm.save(output_path)


@click.command()
@click.option('--epochs', type=int, default=100, show_default=True)
@click.option('--steps_per_epoch', type=int, default=200, show_default=True)
@click.option('--batch_size', type=int, default=16, show_default=True, help='Increase if multiple GPUs are used. Try 32 or 64, depending on available memory.')
@click.option('--unet_kern_size', type=int, default=3, show_default=True, help='Convolution kernel size of the U-Net. Has to be odd.')
@click.option('--unet_n_depth', type=int, default=3, show_default=True)
@click.option('--unet_n_first', type=int, default=16, show_default=True, help='Number of initial feature channels.')
@click.option('--learning_rate', type=float, default=0.0004, show_default=True)
@click.option('--gpu', type=str, default=None, help='Specify which GPUs to use. Default: All GPUs.')
@click.argument('extraction_dir', type=click.Path(dir_okay=True, file_okay=False))
@click.argument('training_dir', type=click.Path(dir_okay=True, file_okay=False), default='./')
@click.argument('model_name', type=str, default='model')
def cryocare_train(epochs, steps_per_epoch, batch_size, unet_kern_size, unet_n_depth, unet_n_first, learning_rate,
                   gpu, extraction_dir, training_dir, model_name):
    """ Trains a Noise2Noise model with cryoCARE.
    
    Can only be used after cryocare-extract was run. Takes the training data generated as an input. Optionally, the output path and the model name can be specified.
    """
    from cryocare.internals.CryoCARE import CryoCARE
    from csbdeep.models import Config
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule
    from cryocare.scripts.cryoCARE_predict import set_gpu_id

    if gpu is None:
        gpu_id = [int(i) for i in range(0,num_gpus())]

    else:
        # Turn GPU list into list of integers
        gpu_id = gpu.split(',')
        gpu_id = [int(gpu) for gpu in gpu_id]

    set_gpu_id({'gpu_id': gpu_id})

    dm = CryoCARE_DataModule()
    dm.load(extraction_dir)

    net_conf = Config(
        axes='ZYXC',
        train_loss='mse',
        train_epochs=epochs,
        train_steps_per_epoch=steps_per_epoch,
        train_batch_size=batch_size,
        unet_kern_size=unet_kern_size,
        unet_n_depth=unet_n_depth,
        unet_n_first=unet_n_first,
        train_tensorboard=False,
        train_learning_rate=learning_rate
    )

    model = CryoCARE(net_conf, model_name, basedir=training_dir)

    history = model.train(dm.get_train_dataset(), dm.get_val_dataset())
    mean, std = dm.train_dataset.mean, dm.train_dataset.std

    with open(join(training_dir, model_name, 'history.dat'), 'wb+') as f:
        pickle.dump(history.history, f)

    norm = {
        "mean": float(mean),
        "std": float(std)
    }
    
    with open(join(training_dir, model_name, 'norm.json'), 'w') as fp:
        json.dump(norm, fp)

    with tarfile.open(join(training_dir, f"{model_name}.tar.gz"), "w:gz") as tar:
        tar.add(join(training_dir, model_name), arcname=path.basename(join(training_dir, model_name)))

@click.command()
@click.option('--tiles', type=(int,int,int), default=(1, 1, 1), show_default=True, help='Specify number of tiles.')
@click.option('--gpu', type=str, default=None, help='Specify which GPUs to use. Default: All GPUs.')
@click.option('--model-path', type=click.Path(dir_okay = False, exists=True), default='./model.tar.gz', show_default=True, help='Specify the folder containing the model.')
@click.argument('input_files', nargs=-1, type=click.Path(exists=True), )
@click.argument('output', type=click.Path(dir_okay=True), default='./denoised')

def cryocare_predict(tiles, gpu, model_path, input_files, output):
    """ Predicts denoised tomogram using cryoCARE.
    
    Takes tomograms or folder containing them with associated EVN/ODD halves and the trained model as inputs.
    """

    import tempfile
    
    from cryocare.scripts.cryoCARE_predict import set_gpu_id, denoise

    # Parse input tomogram        
    input_tomo = list()
    input_evn = list()
    input_odd = list()
    
    # Convert all input_files into a list of Tomogram objects
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_tomo.append(Tomogram(Path(input_file)))
        elif input_file.is_dir():
            input_tomo += ([Tomogram(Path(file))for file in glob(join(input_file, '*_rec_bin_[0-9].mrc'))])
            
    for tomo in input_tomo:
        if path.isfile(tomo.path.with_name(f'{tomo.path.stem}_EVN.mrc')) and path.isfile(tomo.path.with_name(f'{tomo.path.stem}_ODD.mrc')):
            tomo = tomo.with_split_files(tomo.path.with_name(f'{tomo.path.stem}_EVN.mrc'), tomo.path.with_name(f'{tomo.path.stem}_ODD.mrc'))
            input_evn.append(tomo.evn_path)
            input_odd.append(tomo.odd_path)
            print(f'Found reconstruction {tomo.path} with EVN and ODD stacks.')
        else:
            print(f'No EVN/ODD reconstructions found for {tomo.path}. Skipping.')
    
    # Create output directory
    if not path.isdir(output):
        os.mkdir(output)
        
    # Take care of GPU stuff
    if gpu is None:
        gpu_id = [int(i) for i in range(0,num_gpus())]

    else:
        # Turn GPU list into list of integers
        gpu_id = gpu.split(',')
        gpu_id = [int(gpu) for gpu in gpu_id]

    set_gpu_id({'gpu_id': gpu_id})
    
    # Extract model and denoise   
    if os.path.isfile(model_path):
        with tempfile.TemporaryDirectory() as tmpdirname:
            tar = tarfile.open(model_path, "r:gz")
            tar.extractall(tmpdirname)
            tar.close()
            
            config = {}
            config['even'] = input_evn
            config['odd'] = input_odd
            config['output'] = output
            config['n_tiles'] = list(tiles)
            
            config['model_name'] = os.listdir(tmpdirname)[0]
            config['path'] = join(tmpdirname)
            
            with open(join(tmpdirname,config['model_name'],"norm.json")) as f:
                norm_data = json.load(f)
                mean = norm_data["mean"]
                std = norm_data["std"]

            if type(config['even']) is list:
                all_even=tuple(config['even'])
                all_odd=tuple(config['odd'])
            elif os.path.isdir(config['even']) and os.path.isdir(config['odd']):
                all_even = glob(join(config['even'],"*.mrc"))
                all_odd = glob(join(config['odd'],"*.mrc"))
            else:
                all_even = [config['even']]
                all_odd = [config['odd']]

            for even,odd in zip(all_even,all_odd):
                out_filename = join(config['output'], os.path.basename(even))
                denoise(config, mean, std, even=even, odd=odd, output_file=out_filename)