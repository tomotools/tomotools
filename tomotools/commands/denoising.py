import os
import click
import pickle

from os import path
from pathlib import Path
from glob import glob

from tomotools.utils.tomogram import Tomogram

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
    
    if not path.isdir(output_path):
        os.mkdir(output_path)
    
    # Convert all input_files into a list of Tomogram objects
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_tomo.append(Tomogram(Path(input_file)))
        elif input_file.is_dir():
            input_tomo += ([Tomogram(Path(file))for file in glob(path.join(input_file, '*_rec_bin_[0-9].mrc'))])
            
   
    
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
@click.option('--batch_size', type=int, default=16, show_default=True)
@click.option('--unet_kern_size', type=int, default=3, show_default=True, help='Convolution kernel size of the U-Net. Has to be odd.')
@click.option('--unet_n_depth', type=int, default=3, show_default=True)
@click.option('--unet_n_first', type=int, default=16, show_default=True, help='Number of initial feature channels.')
@click.option('--learning_rate', type=float, default=0.0004, show_default=True)
@click.argument('train_data', type=click.Path(dir_okay=True, file_okay=False), default='./')
@click.argument('path', type=click.Path(dir_okay=True, file_okay=False), default='./')
@click.argument('model_name', type=str, default='model')
def cryocare_train(**config):
    """
    Trains a Noise2Noise model with cryoCARE.
    
    Can only be used after cryocare-extract was run. Takes the training data generated as an input. Optionally, the output path and the model name can be specified.
    """
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule
    from cryocare.internals.CryoCARE import CryoCARE
    from csbdeep.models import Config
    dm = CryoCARE_DataModule()
    dm.load(config['train_data'])

    net_conf = Config(
        axes='ZYXC',
        train_loss='mse',
        train_epochs=config['epochs'],
        train_steps_per_epoch=config['steps_per_epoch'],
        train_batch_size=config['batch_size'],
        unet_kern_size=config['unet_kern_size'],
        unet_n_depth=config['unet_n_depth'],
        unet_n_first=config['unet_n_first'],
        train_tensorboard=False,
        train_learning_rate=config['learning_rate']
    )

    model = CryoCARE(net_conf, config['model_name'], basedir=config['path'])

    history = model.train(dm.get_train_dataset(), dm.get_val_dataset())

    print(list(history.history.keys()))
    with open(path.join(config['path'], config['model_name'], 'history.dat'), 'wb+') as f:
        pickle.dump(history.history, f)


@click.command()
@click.option('--n_tiles', type=(int, int, int), default=[1, 2, 2])
@click.option('--model_name', type=str, default='model')
@click.argument('even', type=click.Path(dir_okay=False))
@click.argument('odd', type=click.Path(dir_okay=False))
@click.argument('output_name', type=click.Path(dir_okay=False, exists=False))
def cryocare_predict(**config):
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule
    from cryocare.internals.CryoCARE import CryoCARE
    import mrcfile
    import numpy as np
    import datetime
    config['path'] = './'
    dm = CryoCARE_DataModule()
    dm.load(config['path'])

    model = CryoCARE(None, config['model_name'], basedir=config['path'])

    even = mrcfile.mmap(config['even'], mode='r', permissive=True)
    odd = mrcfile.mmap(config['odd'], mode='r', permissive=True)
    denoised = mrcfile.new_mmap(path.join(config['path'], config['output_name']), even.data.shape, mrc_mode=2,
                                overwrite=True)

    even.data.shape += (1,)
    odd.data.shape += (1,)
    denoised.data.shape += (1,)

    mean, std = dm.train_dataset.mean, dm.train_dataset.std

    model.predict(even.data, odd.data, denoised.data, axes='ZYXC', normalizer=None, mean=mean, std=std,
                  n_tiles=list(config['n_tiles']) + [1, ])

    for label in even.header.dtype.names:
        if label == 'label':
            new_label = np.concatenate((even.header[label][1:-1], np.array([
                'cryoCARE                                                ' + datetime.datetime.now().strftime(
                    "%d-%b-%y  %H:%M:%S") + "     "]),
                                        np.array([''])))
            print(new_label)
            denoised.header[label] = new_label
        else:
            denoised.header[label] = even.header[label]
    denoised.header['mode'] = 2
