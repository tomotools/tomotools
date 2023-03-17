import os
import click
import starfile
import mrcfile
import subprocess

import numpy as np
import pandas as pd

from os import path
from glob import glob

@click.command()
@click.option('-z', '--z-thickness', default = None, show_default=True, 
               help = 'If given, project only central number of pixels.')
@click.option('-r', '--radius', help = 'Radius of particle, for background normalization.')
@click.argument('input_star', nargs=1)
def project_particles(z_thickness, radius, input_star):
    """ Project subtomograms to 2D. 
    
    Takes starfile from Warp etc as input. Performs projection of all subtomograms listed. Writes out starfile to be used for 2D cleaning.
    
    """
    
    
    particles = starfile.read(input_star)
    
    if len(particles) == 2:
        particles = particles['particles']
            
    print(f"Found {len(particles.index)} Particles to project.")
    
    # Prime some values, so that they only have to be read once
    with mrcfile.open(particles.iloc[0]['rlnImageName']) as mrc:
        dim = mrc.data.shape
        angpix = mrc.voxel_size.x
    
    # Preallocate for mrcs
    projections = np.empty(shape=(len(particles.index),dim[1],dim[2]), dtype= np.float32)
    
    for index, row in particles.iterrows():
        
        subtomo = mrcfile.read(row['rlnImageName'])
                
        if z_thickness is not None:
            z_thickness = int(z_thickness)
            z_upper = int(np.floor(subtomo.shape[0]/2+z_thickness/2))
            z_lower = int(np.floor(subtomo.shape[0]/2-z_thickness/2))
            
            projections[index] = np.sum(subtomo[z_lower:z_upper], axis = 0)
                    
        else:#mrcfile reads as ZYX
            projections[index] = np.sum(subtomo.data, axis = 0)
        
    # Image Stack Space group 0 
    mrcfile.write("projections.mrcs",data=projections, voxel_size=angpix)

    # make particles star
    particles_2d = pd.DataFrame()
    particles_2d['rlnMicrographName'] = particles['rlnMicrographName']
    particles_2d['rlnCoordinateX'] = particles['rlnCoordinateX']
    particles_2d['rlnCoordinateY'] = particles['rlnCoordinateY']
    particles_2d['rlnCoordinateZ'] = particles['rlnCoordinateZ']
    particles_2d['rlnAngleRot'] = particles['rlnAngleRot']
    particles_2d['rlnAngleTilt'] = particles['rlnAngleTilt']
    particles_2d['rlnAnglePsi'] = particles['rlnAnglePsi']

    particles_2d['rlnImageName'] = [f'{i}@preprocessed.mrcs' for i in range(1,len(particles.index)+1)]
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
    
    starfile.write({'optics': star_optics, 'particles': particles_2d}, "particles_projected.star")

    subprocess.run(['relion_preprocess',
                    '--operate_on','projections.mrcs',
                    '--norm',
                    '--bg_radius', str(radius)])    
    