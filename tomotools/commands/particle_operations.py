import os
import click
import starfile
import mrcfile
import subprocess

import numpy as np
import pandas as pd

from pathlib import Path
from tqdm import tqdm

@click.command()
@click.option('--ctf', is_flag=True, default=False, show_default=True, 
              help = 'Perform CTF correction prior to projection using the ctf_volume given in .star file.')
@click.option('-z', '--z-thickness', default = None, show_default=True, 
               help = 'If given, project only central number of pixels.')
@click.option('-r', '--radius', help = 'Radius of particle in pixels, for background normalization.')
@click.argument('input_star', nargs=1)
def project_particles(ctf, z_thickness, radius, input_star):
    """ Project subtomograms to 2D. 
    
    Takes starfile from Warp etc as input. Performs projection of all subtomograms listed. Writes out starfile to be used for 2D cleaning.
    
    """
    
    input_star = Path(input_star)
    
    particles = starfile.read(input_star)
    
    # Check if starfile is Relion >3.1 format.
    if "particles" in particles:
        particles = particles['particles']
            
    print(f"Found {len(particles.index)} Particles to project.")
    
    # Prime some values, so that they only have to be read once
    with mrcfile.open(particles.iloc[0]['rlnImageName']) as mrc:
        dim = mrc.data.shape
        angpix = mrc.voxel_size.x
    
    # Preallocate for mrcs
    projections = np.empty(shape=(len(particles.index),dim[1],dim[2]), dtype= np.float32)
    
    with tqdm(total = len(particles.index)) as pbar:
        for index, row in particles.iterrows():
            
            subtomo = mrcfile.read(row['rlnImageName'])
                    
            if ctf:
                subtomo_in = subtomo
                ctf_volume = mrcfile.read(row['rlnCtfImage'])
            
                # Check how the CTF volume is stored
                # Warp stores it in a FFTW-like way, which allows use of fast rfftn
                if not ctf_volume.shape == dim:
                    subtomo = np.fft.irfftn(np.fft.rfftn(subtomo_in)*ctf_volume, dim)
                    
                # Legacy approaches might store full array, use fftn
                else:
                    subtomo = np.real(np.fft.ifftn(np.fft.fftn(subtomo)*ctf_volume))    
            
            if z_thickness is not None:
                z_thickness = int(z_thickness)
                z_upper = int(np.floor(dim[0]/2+z_thickness/2))
                z_lower = int(np.floor(dim[0]/2-z_thickness/2))
                
                projections[index] = np.sum(subtomo[z_lower:z_upper], axis = 0)
                        
            else:#mrcfile reads as ZYX
                projections[index] = np.sum(subtomo.data, axis = 0)
                
            pbar.update(1)
        
    # TODO: Write Image Stack Space group 0
    print('Particles projected, writing out stack.')     
    mrcfile.write(input_star.with_name("temp.mrcs"),data=projections, voxel_size=angpix, overwrite=True)

    # make particles star
    particles_2d = pd.DataFrame()
    particles_2d['rlnMicrographName'] = particles['rlnMicrographName']
    particles_2d['rlnCoordinateX'] = particles['rlnCoordinateX']
    particles_2d['rlnCoordinateY'] = particles['rlnCoordinateY']
    particles_2d['rlnCoordinateZ'] = particles['rlnCoordinateZ']
    particles_2d['rlnAngleRot'] = particles['rlnAngleRot']
    particles_2d['rlnAngleTilt'] = particles['rlnAngleTilt']
    particles_2d['rlnAnglePsi'] = particles['rlnAnglePsi']

    particles_2d['rlnImageName'] = [f'{i}@{input_star.with_name(input_star.stem)}_projected.mrcs' for i in range(1,len(particles.index)+1)]
    particles_2d['rlnOpticsGroup'] = '1'

    # Make _optics group for compatibility > 3.0
    star_optics = pd.DataFrame.from_dict([{'rlnOpticsGroupName': 'opticsGroup1',
                   'rlnOpticsGroup': '1',
                   'rlnMicrographPixelSize': angpix,
                   'rlnImageSize': dim[2],
                   'rlnVoltage': '300',
                   'rlnSphericalAberration': '2.7',
                   'rlnAmplitudeContrast': '0.1',
                   'rlnImageDimensionality': '2'}])
    
    starfile.write({'optics': star_optics, 'particles': particles_2d}, f"{input_star.with_name(input_star.stem)}_projected.star")

    subprocess.run(['relion_preprocess',
                    '--operate_on','temp.mrcs',
                    '--norm',
                    '--bg_radius', str(radius),
                    '--operate_out', f"{input_star.with_name(input_star.stem)}_projected.mrcs"])    
   
    os.unlink('temp.mrcs')

@click.command()
@click.argument('star', nargs=1)
def upgrade_star(star):
    """
    Take subtomogram starfile from Warp and make it compatible with Relion 3.1.
        
    """
    star = Path(star)
    
    particles = starfile.read(star)    
    
    if len(particles) == 2:
        particles = particles['particles']
                
    # Get some values for optics header
    with mrcfile.open(particles.iloc[0]['rlnImageName']) as mrc:
        dim = mrc.data.shape
        angpix = mrc.voxel_size.x
    
    del particles['rlnMagnification']
    del particles['rlnDetectorPixelSize']
    particles['rlnOpticsGroup'] = '1'
    
    # Make _optics group for compatibility > 3.0
    star_optics = pd.DataFrame.from_dict([{'rlnOpticsGroupName': star.stem,
                   'rlnOpticsGroup': '1',
                   'rlnMicrographPixelSize': angpix,
                   'rlnImageSize': dim[2],
                   'rlnVoltage': '300',
                   'rlnSphericalAberration': '2.7',
                   'rlnAmplitudeContrast': '0.1',
                   'rlnImageDimensionality': '3'}])
    
    starfile.write({'optics': star_optics, 'particles': particles}, f"{star.with_name(star.stem)}_upgraded.star")


@click.command()
@click.argument('subset_star', nargs=1)
@click.argument('subtomo_stars', nargs=-1) 
def apply_subset(subset_star, subtomo_stars):
    """
    Apply subset selection to 3D dataset. 
    
    Give the star file from subset selection job in relion and the (multiple) star files in which subtomograms are listed. 
    Will output one starfile for each subtomogram star, in the structure expected for Warp. Uses the filename of the projections stack to match.
        
    """
    
    subset = starfile.read(subset_star)
    subset = subset['particles']
    
    subset['origin_star'] = subset['rlnImageName'].str.split("@", expand = True)[1]

    for st_star in subtomo_stars:
        
        subtomo = starfile.read(st_star)
        subset_2d = subset[subset['rlnImageName'].str.split("@", expand=True)[1] == f'{Path(st_star).stem}_projected.mrcs']
        
        selected_idx = subset_2d['rlnImageName'].str.split("@", expand=True)[0].tolist()

        # indices in mrcs are 1-based
        selected_idx = [int(idx)-1 for idx in selected_idx]        
        
        subset_3d = subtomo.iloc[selected_idx]
        
        starfile.write(subset_3d, Path(st_star).with_name(f'{Path(st_star).stem}_selected.star'))
        
        print(f'Wrote out {len(subset_3d.index)} particles from {st_star}. \n')
