import os
import pickle
import shutil
import subprocess
from glob import glob
from os import path, mkdir

import click

from utils import comfile, util


# @click.command()
# @click.option('--evnodd_dir', type=click.Path(exists=True, file_okay=False), show_default='reconstruction_dir')
# @click.argument('reconstruction_dir', type=click.Path(exists=True, file_okay=False))
# @click.argument('output_dir', type=click.Path(file_okay=False))
def split_reconstruct(evnodd_dir, reconstruction_dir, output_dir):
    """WORK IN PROGRESS, DON'T USE"""
    evnodd_dir = reconstruction_dir if evnodd_dir is None else evnodd_dir
    input_ts = comfile.get_value(path.join(reconstruction_dir, 'newst.com'), 'InputFile')
    input_ts_basename, input_ts_ext = path.splitext(input_ts)
    if not path.isdir(output_dir):
        mkdir(output_dir)
    for eo in ['EVN']:  # , 'ODD']:
        eo_dir = path.join(output_dir, eo)
        eo_ts = f'{input_ts_basename}_{eo}{input_ts_ext}'
        print(f'Reconstructing {eo_ts}')
        # Create the reconstruction dir
        mkdir(eo_dir)
        # Link tilt-series: rec_dir/TS_xx_EVN.mrc -> eo_dir/TS_xx.mrc
        os.symlink(path.abspath(path.join(evnodd_dir, eo_ts)), path.join(eo_dir, input_ts))
        # Copy files for reconstruction
        for file in glob(path.join(reconstruction_dir, '*.com')) \
                + glob(path.join(reconstruction_dir, '*.xf')) \
                + glob(path.join(reconstruction_dir, '*.xtilt')) \
                + glob(path.join(reconstruction_dir, '*.tlt')) \
                + glob(path.join(reconstruction_dir, '*.tltxf')) \
                + glob(path.join(reconstruction_dir, '*.rawtlt')) \
                + glob(path.join(reconstruction_dir, '*.resid')) \
                + glob(path.join(reconstruction_dir, '*.resmod')) \
                + glob(path.join(reconstruction_dir, '*.seed')) \
                + glob(path.join(reconstruction_dir, '*.maggrad')) \
                + glob(path.join(reconstruction_dir, '*.defocus')) \
                + glob(path.join(reconstruction_dir, '*.fid')) \
                + glob(path.join(reconstruction_dir, '*.3dmod')) \
                + glob(path.join(reconstruction_dir, '*.prexf')) \
                + glob(path.join(reconstruction_dir, '*.prexg')) \
                + glob(path.join(reconstruction_dir, '*.xyz')) \
                + glob(path.join(reconstruction_dir, '*.mod')) \
                + glob(path.join(reconstruction_dir, '*.mdoc')):
            shutil.copyfile(file, path.join(eo_dir, path.basename(file)))
        # Run comscripts
        subprocess.run(['submfg', 'newst.com'], cwd=eo_dir)
        subprocess.run(['submfg', 'ctf3dsetup.com'], cwd=eo_dir)
        comfile.modify_value(path.join(eo_dir, 'ctf3d-001-sync.com'), 'DoseWeightingFile', f'{input_ts}.mdoc')
        gpu_list = ':'.join([str(i + 1) for i in range(int(util.gpuinfo()['Attached GPUs']))])
        subprocess.run(['processchunks', '-G', f'localhost:{gpu_list}', 'ctf3d'], cwd=eo_dir)
        # subprocess.run(['submfg', 'trimvol.com'], cwd=eo_dir)


@click.command()
@click.option('--num_slices', type=int, default=1200, show_default=True)
@click.option('--split', type=float, default=0.9, show_default=True)
@click.option('--patch_shape', type=int, default=72, show_default=True)
@click.option('--tilt_axis', type=str, default='Y', show_default=True)
@click.option('--n_normalization_samples', type=int, default=500, show_default=True)
@click.argument('even', type=click.Path(dir_okay=False, exists=True))
@click.argument('odd', type=click.Path(dir_okay=False, exists=True))
@click.argument('output_path', type=click.Path(dir_okay=True, file_okay=False), default='./')
def cryocare_extract(**config):
    from cryocare.internals.CryoCAREDataModule import CryoCARE_DataModule
    dm = CryoCARE_DataModule()
    dm.setup([config['odd']], [config['even']], n_samples_per_tomo=config['num_slices'],
             validation_fraction=(1.0 - config['split']), sample_shape=[config['patch_shape']]*3,
             tilt_axis=config['tilt_axis'], n_normalization_samples=config['n_normalization_samples'])
    dm.save(config['output_path'])


@click.command()
@click.option('--epochs', type=int, default=100, show_default=True)
@click.option('--steps_per_epoch', type=int, default=200, show_default=True)
@click.option('--batch_size', type=int, default=16, show_default=True)
@click.option('--unet_kern_size', type=int, default=3, show_default=True)
@click.option('--unet_n_depth', type=int, default=3, show_default=True)
@click.option('--unet_n_first', type=int, default=16, show_default=True)
@click.option('--learning_rate', type=float, default=0.0004, show_default=True)
@click.argument('train_data', type=click.Path(dir_okay=True, file_okay=False), default='./')
@click.argument('path', type=click.Path(dir_okay=True, file_okay=False), default='./')
@click.argument('model_name', type=str, default='model')
def cryocare_train(**config):
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
