import mrcfile
import numpy as np
from os import path

import click

from tomotools.utils import mathutil

@click.command()
@click.option('--defocus', help = 'Defocus in um. Positive values denote underfocus. If not given, will be automatically determined.')
@click.option('--snrfalloff', default=1, show_default=True, help='How fast the SNR falls off - 1.0 or 1.2 usually')
@click.option('--deconvstrength', default=1, show_default=True, help='Overall deconvolution strength, depends on SNR. 1 for SNR 1000, 0.67 for SNR 100, etc.')
@click.option('--hpnyquist', default = 0.02, show_default=True, help='Fraction of Nyquist frequency to be cut off on the lower end.')
@click.option('--phaseshift', default = 0, show_default= True, help='Phase shift in degrees')
@click.option('--phaseflipped', default = False, show_default = True, help='Is data already phase-flipped?')
@click.argument('input_files', nargs=-1, required=True)

def deconv(defocus,snrfalloff,deconvstrength,hpnyquist,phaseshift,phaseflipped,input_files):
    """Deconvolute your tomogram or list of tomograms. Python implementation Dimitri Tegunovs tom_deconv.m.
    
    The input file should be a reconstructed tomogram. AngPix is automatically read from the header.
    Output file will be an mrc in the same folder, with added _deconv suffix.
    
    Original Script at https://github.com/dtegunov/tom_deconv/.
    """
    
    # TODO: automatically determine defocus!
    
    for input_file in input_files:
        
        with mrcfile.open(input_file) as mrc:
            angpix = float(mrc.voxel_size.x)
            volume_in = mrc.data
                        
        wiener = mathutil.wiener(angpix, float(defocus), float(snrfalloff), float(deconvstrength), float(hpnyquist), phaseflipped, int(phaseshift))
        
        # Define coordinates along xyz in relationship to center of volume 
        # TODO: test what happens with even dimension!          
        sx = -1*np.floor(volume_in.shape[2]/2)
        fx = sx + volume_in.shape[2] -1
        
        sy = -1*np.floor(volume_in.shape[1]/2)
        fy = sy + volume_in.shape[1] -1
        
        sz = int(-1*np.floor(volume_in.shape[0]/2))
        fz = sz + volume_in.shape[0] -1
                
        # in mcrfile convention, the array is ordered zyx! 
        x = np.arange(sx,fx+1,dtype = 'int16')
        x = x * np.ones(list(volume_in.shape[1:3]),dtype = 'int16')
        x = x[:,:,np.newaxis] * np.ones(volume_in.shape[0],dtype = 'int16')
        x = x.transpose(2,0,1)
        
        y = np.arange(sy,fy+1,dtype = 'int16')
        y = y * np.ones(list(volume_in.shape[0:2]),dtype = 'int16')
        y = y[:,:,np.newaxis] * np.ones(volume_in.shape[2],dtype = 'int16')
        
        z = np.arange(sz,fz+1,dtype = 'int16')
        z = z * np.ones(list(volume_in.shape[0:2]),dtype = 'int16').transpose()
        z = z[:,:,np.newaxis] * np.ones(volume_in.shape[2],dtype = 'int16')
        z = z.transpose(1,0,2)        
        
        x = np.divide(x,np.abs(sx),dtype = 'float32')
        y = np.divide(y,np.abs(sy), dtype = 'float32')
        z = np.divide(z,np.maximum(1,np.abs(sz)), dtype = 'float32')

        r = np.sqrt(np.power(x,2)+np.power(y,2)+np.power(z,2))
        
        del(x,y,z,sx,sy,sz,fx,fy,fz)
        
        r = np.minimum(1, r)
        r = np.fft.ifftshift(r)
        
        x = np.linspace(0,1,2048)
        
        ramp = np.interp(r,x,wiener)
    
        del(r)

        vol_deconv = np.real(np.fft.ifftn(np.fft.fftn(volume_in)*ramp))
        
        vol_deconv = vol_deconv.astype('float32')
        
        output_file = f'{path.splitext(input_file)[0]}_deconv.mrc'
        
        with mrcfile.open(output_file, mode = 'w+') as mrc:
            mrc.voxel_size = angpix
            mrc.set_data(vol_deconv)
            mrc.update_header_stats()