import os
import click
import starfile
import subprocess
import mrcfile

import pandas as pd

from os import path
from datetime import date
from pathlib import Path

from tomotools.utils import mdocfile
from tomotools.utils.tiltseries import run_ctfplotter, convert_input_to_TiltSeries, aretomo_executable, TiltSeries, parse_ctfplotter, parse_darkimgs, write_ctfplotter
from tomotools.utils.tomogram import Tomogram

@click.command()
@click.argument('input_files', nargs=-1)
def fit_ctf(input_files):
    """ Performs interactive CTF-Fitting. 
    
    Takes tiltseries or folders containing them as input. Runs imod ctfplotter interactively. Defaults to overwriting previous results. Saves results to folder.  
    
    """

    tiltseries = convert_input_to_TiltSeries(input_files)
    
    for ts in tiltseries:
        run_ctfplotter(ts, True)
        
@click.command()
@click.option('--bin', default=4, show_default=True, help="Binning for reconstruction used to pick particles.")
@click.option('--sirt', default=5, show_default=True, help="SIRT-like filter for reconstruction used to pick particles.")
@click.option('-b', '--batch-input', is_flag=True, default=False, show_default=True,
              help="Read input files as text, each line is a tiltseries (folder)")
@click.argument('input_files', nargs=-1)
@click.argument('relion_root', nargs=1)
def tomotools2relion(bin, sirt, batch_input, input_files, relion_root):
    """ Prepares Relion4 project. 
    
    Takes as input several tiltseries (folders) obtained after processing with tomotools batch-prepare-tiltseries and tomotools reconstruct.
    Gets all required output files from AreTomo, makes a new binned reconstruction for particle picking.
    
    Provide the relion root folder. This may be a previously existing project. Generates starfile for tomogram import in the relion root with current date.
    Makes one optics group per date. 
    
    """
    
    # Parse input files
    if batch_input:
        input_files_parsed = list()
        with open(input_files[0], "r+") as f:
            for line in f:
                input_files_parsed.append(line.strip("\n"))
                
    else:
        input_files_parsed = input_files
        
    # Convert to list of tiltseries
    ts_list = convert_input_to_TiltSeries(input_files_parsed)
    
    print(f'Found {len(ts_list)} TiltSeries to work on.')
    
    # Create Relion directory    
    if not path.isdir(relion_root):
        os.mkdir(relion_root)
        print(f'Created Relion root directory at {relion_root}')
    
    # Prepare tomogram folders
    tomo_root = path.join(relion_root, 'tomograms')
    
    if not path.isdir(tomo_root):
        os.mkdir(tomo_root)
        print(f'Created ./tomograms directory at {tomo_root}.')
    
    df = pd.DataFrame()
    
    for ts in ts_list:
        
        print(f'Now working on {ts.path.name}.')
        
        tomo_folder = Path(path.join(tomo_root, ts.path.stem))
        mdoc = mdocfile.read(ts.mdoc)
        
        if path.isdir(tomo_folder):
            raise FileExistsError("This tomogram seems to already exist in the target relion project. Maybe names are non-unique?")
                           
        # TODO: deal with imod alignments
        
        # Run AreTomo based on previous alignment file to create additional outputs
        
        angpix = mdoc['PixelSpacing']
        
        aln_file = ts.path.with_suffix('.aln')
        tlt_file = ts.path.with_suffix('.tlt')
        ali_stack = ts.path.with_name(f'{ts.path.stem}_ali.mrc')
        imod_dir = path.join(ts.path.parent, (ali_stack.stem + "_Imod"))
        
        if not path.isfile(aln_file):
            raise FileNotFoundError(
                f'{ts.path}: No previous alignment was found at {aln_file}. You need to first run alignments using tomotools reconstruct.')

        subprocess.run([aretomo_executable(),
                        '-InMrc', ts.path,
                        '-OutMrc', ali_stack,
                        '-AngFile', tlt_file,
                        '-AlnFile', aln_file,
                        '-VolZ', '0',
                        '-OutImod','3'],
                       stdout=subprocess.DEVNULL)
        
        ali_stack_imod = TiltSeries(Path(path.join(imod_dir, (ali_stack.stem + ".st"))))
        
        with mrcfile.mmap(ali_stack, mode='r+') as mrc:
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()
            
        with mrcfile.mmap(ali_stack_imod.path, mode='r+') as mrc:
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()
        
        print(f'Performed AreTomo export of {ts.path.stem}.')
        
        # Make reconstruction for picking
        ali_rec = Tomogram.from_tiltseries(ali_stack_imod, bin = bin, sirt = sirt)
        
        print(f'Created reconstruction for particle picking at {ali_rec.path.name}.')
                
        # Get view exclusion list and create appropriate mdoc
        exclude = parse_darkimgs(ts)

        mdoc_cleaned = mdoc  
        mdoc_cleaned['sections'] = [ele for idx, ele in enumerate(mdoc['sections']) if idx not in exclude]
        mdocfile.write(mdoc_cleaned, ali_stack_imod.mdoc)
        
        # If required run ctfplotter or just return results of previous run - this is done on the original tiltseries to avoid artifacts from alignment
        ctffile = parse_ctfplotter(run_ctfplotter(ts, False))
        ctffile_cleaned = ctffile[~ctffile.view_start.isin([str(ele) for ele in exclude])]
        
        # Relion4 requires a line for each tilt in the ctfplotter file; if overlapping spectra were fit, duplicate the lines here:
        if len(mdoc_cleaned['sections']) != len(ctffile_cleaned):
            
            # Figure out which tilts are missing
            for section in mdoc_cleaned['sections']:
                tilt = round(section['TiltAngle'])
                
                if not tilt in [int(ele) for ele in pd.to_numeric(ctffile_cleaned['tilt_start']).to_list()]:
                    df_subset = ctffile_cleaned.loc[((pd.to_numeric(ctffile_cleaned['tilt_start']) < tilt) & (pd.to_numeric(ctffile_cleaned['tilt_end']) > tilt))]
                    
                    df_temp = pd.DataFrame({'view_start': pd.to_numeric(df_subset['view_start'])+1,
                                            'view_end': df_subset.view_end,
                                            'tilt_start': tilt,
                                            'tilt_end': tilt,
                                            'df_1_nm': df_subset.df_1_nm,
                                            'df_2_nm': df_subset.df_2_nm,
                                            'astig_ang': df_subset.astig_ang})
                    
                    ctffile_cleaned = pd.concat([ctffile_cleaned, df_temp])
            
        
        ctf_out = write_ctfplotter(ctffile_cleaned, Path(path.join(ali_stack_imod.path.parent,(f'{ali_stack_imod.path.stem}_ctfplotter.txt'))))
        
        # Create or symlink all relevant files: pre-alignment stack, post-alignment stack, tlt, xf, tilt.com, newst.com, ctfplotter
        os.symlink(imod_dir, tomo_folder, target_is_directory=True)
        
        print(f'Successfully created tomograms folder for {ts.path.name}.')

        df_temp = pd.DataFrame(data = {'rlnTomoName': ts.path.stem, 
                                       'rlnTomoImportImodDir': tomo_folder,
                                        'rlnTomoTiltSeriesName': path.join(tomo_folder, (f'{ali_stack_imod.path.name}:mrc')),
                                        'rlnTomoImportOrderList': mdocfile.convert_to_order_list(mdoc_cleaned, tomo_folder),
                                        'rlnTomoImportCtfPlotterFile': ctf_out,
                                        'rlnTomoImportFractionalDose': mdoc_cleaned['sections'][0]['ExposureDose'],
                                        'rlnOpticsGroupName': mdoc_cleaned['sections'][0]['DateTime'].split()[0]},
                               dtype = str, index=[0])
                               
        df = pd.concat([df_temp.astype(object), df])
                
    
    # Write out import_tomos.star file w/ current date for easy ID
    
    today = date.today()
    id = today.strftime("%y%m%d")
    
    starfile_path = path.join(relion_root, (id + "_tomotools_import.star"))
    
    starfile.write(df, starfile_path)
    
    print(f'Wrote out file for Relion import at {starfile_path}.')
