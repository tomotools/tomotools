import os
import shutil
import subprocess
from glob import glob
from os import mkdir
from os import path
from os.path import abspath, basename, join, splitext
import re
from operator import itemgetter

import click

from tomotools.utils import mdocfile, frame_utils


@click.command()
@click.option('--cpus', default=8, show_default=True, help='Number of CPUs, passed to justblend')
@click.argument('input_files', nargs=-1)
@click.argument('output_dir')
def blend_montages(cpus, input_files, output_dir):
    """Blend montages using justblend

    The input files must be montage .mrc/.st files, so usually you will invoke this function with something like:
    blend-montages MMM*.mrc output_dir
    """
    if not path.isdir(output_dir):
        mkdir(output_dir)

    for input_file in input_files:
        os.symlink(abspath(input_file), join(output_dir, basename(input_file)))
    
    wd = os.getcwd()
    
    os.chdir(output_dir)
    links = [basename(input_file) for input_file in input_files]
    subprocess.run(['justblend', '--cpus', str(cpus)] + [basename(input_file) for input_file in input_files])
    # Delete temporary files
    for file in links + glob('*.ecd') + glob('*.pl') + glob('*.xef') \
                + glob('*.yef') + glob('*.com') + glob('*.log') + ['processchunks-jb.out']:
        os.remove(file)

    os.chdir(wd)

@click.command()
@click.option('--splitsum/--nosplitsum', is_flag=True, default=True, show_default=True,
              help='Create even/odd split sums, e.g. for denoising')
@click.option('--mcbin', '--motioncor_binning', default=2, show_default=True,
              help='Binning parameter passed to MotionCor2')
@click.option('--reorder/--noreorder', is_flag=True, default=True, show_default=True,
              help='Sort tilt-series by angle in ascending order and create an appropriate MDOC file')
@click.option('--frames', type=click.Path(exists=True, file_okay=False, dir_okay=True),
              help='If your frames are not automatically found, you can pass the path to the frames directory')
@click.option('--gainref', type=click.Path(exists=True, dir_okay=False),
              help='Use this gain reference instead looking for one in the Subframe MDOC files')
@click.option('--group', type=int, default=1, show_default=True,
              help='Group frames, useful for low-dose frames. Also see motioncor2 manual')
@click.option('--gpus', type=str, default=None,
              help='GPUs list, comma separated (e.g. 0,1), determined automatically if not passed')
@click.option('--exposuredose', type=float, default=None)
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.argument('output_dir', type=click.Path(writable=True))
def batch_prepare_tiltseries(splitsum, mcbin, reorder, frames, gainref, group, gpus, exposuredose, input_files,
                             output_dir):
    """Prepare tilt-series for reconstruction.

    This function runs MotionCor2 on movie frames, stacks the motion-corrected frames and sorts them by tilt-angle.
    The input files may be individual .mrc/.st tilt-series files or directories containing them.
    In the latter case, a simple search for MRC and ST files will be run (using the globs *.mrc and *.st).
    If a directory is given, will first check for PACEtomo targeting files and move them to a subdirectory to prevent interference.
    
    Every input file requires a corresponding .mdoc file. 
    The last argument is the output dir. It will be created if it doesn't exist.
    """
    # If input_files is a directory, check for PACEtomo files by regex _tgts.txt, save all roots
    wd = os.getcwd()
    
    if any(path.isdir(input_file) for input_file in input_files):
       
        tgts_temp = list()
        
        for input_file in input_files:
            tgts_temp.extend(glob(path.join(input_file, '*_tgts.txt')))
        
        if len(tgts_temp) == 0:
            print('No PACEtomo files found. Continuing.')
        
        else:
            # Move all targeting data (_tgt_*.mrc, _tgts.txt) to a separate directory
            for tgt in tgts_temp:
                
                pacetomo_dir = path.join(path.dirname(path.abspath(tgt)), 'PACEtomo_targets')
                
                if not path.isdir(pacetomo_dir):
                    mkdir(pacetomo_dir)
                    
                root = re.split('[_tgts_]',tgt)[0]
                print('Found PACEtomo root file ' + tgt)
            
                root_path = path.join(path.dirname(path.abspath(tgt)), root)
                cmd = "mv " + root_path + "*_tgt* "  + pacetomo_dir
                os.system(cmd)
                    
    os.chdir(wd)
        
    # Convert all directories into a list of MRC/ST files
    input_files_temp = list()
    for input_file in input_files:
        if path.isfile(input_file):
            input_files_temp.append(input_file)
        elif path.isdir(input_file):
            input_files_temp += glob(path.join(input_file, '*.mrc'))
            input_files_temp += glob(path.join(input_file, '*.st'))
    input_files = input_files_temp

    for input_file in input_files:
        if input_file.endswith('.mdoc'):
            mdoc = mdocfile.read(input_file)
            input_file = path.splitext(input_file)[0]
        else:
            try:
                mdoc = mdocfile.read(f'{input_file}.mdoc')
            except FileNotFoundError:
                print(f'No MDOC file found for {input_file}')
                continue
        if mdoc.get('Montage', 0) == 1:
            print(f'Skipping {input_file} because it is a montage')
            continue
        # Identify batch / anchoring files, as they all should have a tilt angle < abs(1) for all section -> feels a bit hacky
        if all(section['TiltAngle'] < abs(1) for section in mdoc['sections']):
            print(f'{input_file} is not a tilt series, as all TiltAngles are near zero. Skipping.')
            continue       
        
        # File is a tilt-series, look for subframes
        print(f'Working on {input_file}, which looks like a tilt series')        
        for section in mdoc['sections']:
            subframes_root_path = path.dirname(input_file) if frames is None else frames
            #print(f'SubFramePath field: {section.get("SubFramePath", "")}')
            section['SubFramePath'] = mdocfile.find_relative_path(
                subframes_root_path,
                section.get('SubFramePath', '').replace('\\', path.sep)
            )
            if exposuredose is not None:
                section['ExposureDose'] = exposuredose
            # TODO: warning if ExposureDose = 0 and not set
            #print(f'SubFramePath field: {section.get("SubFramePath", "")}')
        # Check if all subframes were found
        subframes = [frame_utils.SubFrame(section['SubFramePath'],section['TiltAngle']) for section in mdoc['sections']]
        if all(subframe.files_exist(is_split=False) for subframe in subframes):
            print(f'Subframes were found for {input_file}, will run MotionCor2 on them')
            
            # Get rotation and flip of Gain reference from mdoc file property
            mcrot, mcflip = frame_utils.sem2mc2(mdoc['sections'][0]['RotationAndFlip'])
                        
            frames_corrected_dir = path.join(output_dir, 'frames_corrected')
            subframes_corrected = frame_utils.motioncor2(subframes, frames_corrected_dir, splitsum=splitsum,
                                                          binning=mcbin, mcrot=mcrot, mcflip=mcflip, group=group, override_gainref=gainref,
                                                          gpus=gpus)
            
            # Reorder subframes and mdoc as unidirectional if desired           
            if reorder:
                subframes_corrected = frame_utils.sort_subframes_list(subframes_corrected)
                mdoc['sections'] = sorted(mdoc['sections'], key=itemgetter('TiltAngle'))
            
            # Create stack from individual tilts
            stack, stack_mdoc = frame_utils.frames2stack(subframes_corrected,
                                                          path.join(output_dir, path.basename(input_file)), full_mdoc=mdoc,
                                                          overwrite_titles=mdoc['titles'])
            
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created {path.basename(stack)}')
        else:
            print(f'No subframes were found for {input_file}, will continue without MotionCor2')
            # TODO: add implementation for non-subframe TS w/ and w/o reorder!            
            print('Not implemented yet, skipping')
            continue
            # raise NotImplementedError('Sorry, non-motioncor2 path is not implemented yet')

@click.command()
@click.option('--move', is_flag=True, help="Move files into a subdirectory")
@click.option('--local/--global', is_flag=True, default=False, show_default=True,
              help="Local or global alignments (local takes significantly longer)")
@click.option('--extra-thickness', default=0, show_default=True, help="Extra thickness in unbinned pixels")
@click.option('-b', '--bin', default=1, show_default=True, help="Final reconstruction binning")
@click.option('--sirt', default=5, show_default=True, help="SIRT-like filter iterations")
@click.option('--keep-ali-stack/--delete-ali-stack', is_flag=True, default=False, show_default=True, help="Keep or delete the non-dose-filtered aligned stack (useful for Relion)")
@click.option('--previous', type=click.Path(exists=True),
               help="Don't do alignments, but use previous alignments and MDOC file of the passed tilt-series")
@click.option('--batch-file', type=click.Path(exists=True, dir_okay=False),help = "You can pass a tab-separated file with tilt series names and views to exclude before reconstruction.")
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
def reconstruct(move, local, extra_thickness, bin, sirt, keep_ali_stack, previous, batch_file, input_files):
    if batch_file is not None:
        ts_info = {}
        with open(batch_file) as file:
            for line in file:
                if line != '\n':
                    l=line.split('\t')
                    temp={l[0]: l[1].rstrip()}
                    ts_info.update(temp)
                                      
    for tiltseries in input_files:
        mdoc_file = f'{tiltseries}.mdoc' if previous is None else f'{previous}.mdoc'
        if not path.isfile(mdoc_file):
            raise FileNotFoundError(f'No MDOC file found at {mdoc_file}')
        
        print(f'Working on file {tiltseries}.')
     
        # Check for tilts to exclude
        excludetilts = None
        if batch_file is not None:
            if tiltseries in ts_info:
                excludetilts = ts_info[tiltseries]
                print(f'Found tilts to exclude in {batch_file}. Will exclude tilts {excludetilts}.')
                
        if move:
            dir = splitext(tiltseries)[0]
            new_tiltseries = join(dir, basename(tiltseries))
            mkdir(dir)
            print(f'Move files to subdir {dir}')
            os.rename(tiltseries, new_tiltseries)
            tiltseries = new_tiltseries
            # Only move the MDOC file if it's not from a previous reconstruction
            if previous is None:
                new_mdoc_file = join(dir, basename(mdoc_file))
                os.rename(mdoc_file, new_mdoc_file)
                mdoc_file = new_mdoc_file       

        # Run newstack to exclude tilts
        # TODO: Consider already binning here before AreTomo?
        rootname = splitext(tiltseries)[0]
    
        if excludetilts is not None:
            exclude_file = f'{rootname}_excludetilts.mrc'
            subprocess.run(['newstack', 
                            '-in', tiltseries,
                            '-mdoc',
                            '-quiet',
                            '-exclude', excludetilts,
                            '-ou', exclude_file])
            print(f'Excluded specified tilts from {tiltseries}.')
            tiltseries = exclude_file
            mdoc_file = f'{tiltseries}.mdoc'
        
        mdoc = mdocfile.read(mdoc_file)
        
        # To account for different sensor sizes, read from mdoc file.
        # Define default thickness as function of pixel size -> always reconstruct 1 um for tomopitch. 
        thickness = str(round(10000 / mdoc['PixelSpacing']))
        full_x, full_y = mdoc['ImageSize']
        patch_x, patch_y = [round(full_x/1000), round(full_y/1000)]
        
        # Generate MRC filenames
        # TODO: Make a class?  
        ali_file = f'{rootname}_ali.mrc'
        ali_file_mtf = f'{rootname}_ali_mtf.mrc'
        ali_file_mtf_bin = f'{rootname}_ali_mtf_b{bin}.mrc'
        ali_file_mtf_bin8 = f'{rootname}_ali_mtf_b8.mrc'
        full_rec_file = f'{rootname}_full_rec.mrc'
        rec_file = f'{rootname}_rec_b{bin}.mrc'
        # Alignment files (depend on whether or not --previous is passed)
        ali_rootname = splitext(previous)[0] if previous is not None else rootname
        tlt_file = f'{ali_rootname}.tlt'
        tlt_file_ali = f'{ali_rootname}_ali.tlt'
        tomopitch_file = f'{ali_rootname}.mod'
        aln_file = f'{ali_rootname}.aln'

        # Run AreTomo 
        if previous is None:
            subprocess.run(['extracttilts', tiltseries, tlt_file],
                           stdout=subprocess.DEVNULL)
            subprocess.run([frame_utils.aretomo_executable(),
                            '-InMrc', tiltseries,
                            '-OutMrc', ali_file,
                            '-AngFile', tlt_file,
                            '-VolZ', '0',
                            '-TiltCor', '1'] + (['-Patch', patch_x, patch_y] if local else []),
                            stdout=subprocess.DEVNULL)
        else:
            subprocess.run([frame_utils.aretomo_executable(),
                            '-InMrc', tiltseries,
                            '-OutMrc', ali_file,
                            '-AlnFile', aln_file,
                            '-VolZ', '0'],
                            stdout=subprocess.DEVNULL)
            
        print(f'Done aligning {tiltseries} with AreTomo.')

        # TODO: Discuss whether to directly use the value from the mdoc here
        pix_size = subprocess.run(['header', '-PixelSize', tiltseries], capture_output=True, text=True).stdout        
        pix_size = ",".join(pix_size.strip().split())
        subprocess.run(['alterheader', '-PixelSize', pix_size, ali_file],
                       stdout=subprocess.DEVNULL)

        # Dose filtration. Only ExposureDose needs to be entered, as PriorRecordDose is deduced by mtffilter based on the DateTime entry, see mtffilter -help, section "-dtype"
        subprocess.run(['mtffilter', '-dtype', '4', '-dfile', mdoc_file, ali_file, ali_file_mtf],
                       stdout=subprocess.DEVNULL)
        if not keep_ali_stack:
            os.remove(ali_file)

        print(f'Done dose-filtering {tiltseries}.')

        # Tomo pitch
        if previous is None:
            subprocess.run(['binvol', '-x', '8', '-y', '8', '-z', '1', ali_file_mtf, ali_file_mtf_bin8],
                           stdout=subprocess.DEVNULL)
            subprocess.run(['tilt',
                           '-InputProjections', ali_file_mtf_bin8,
                           '-OutputFile', full_rec_file,
                           '-IMAGEBINNED', '8',
                           '-TILTFILE', tlt_file_ali,
                           '-THICKNESS', str(thickness),
                           '-RADIAL', '0.35,0.035',
                           '-FalloffIsTrueSigma', '1',
                           '-SCALE', '0.0,0.05',
                           '-PERPENDICULAR',
                           '-MODE', '2',
                           '-FULLIMAGE', f'{full_y} {full_x}',
                           '-SUBSETSTART', '0,0',
                           '-AdjustOrigin',
                           '-ActionIfGPUFails', '1,2',
                           '-OFFSET', '0.0',
                           '-SHIFT', '0.0,0.0',
                           '-UseGPU', '0'] +
                           (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []),
                           stdout=subprocess.DEVNULL)

            os.remove(ali_file_mtf_bin8)
            # Try to automatically find edges of tomogram
            fs = subprocess.run(['findsection',
                            '-tomo', full_rec_file,
                            '-pitch', tomopitch_file,
                            '-scales', '2',
                            '-size', '16,1,16',
                            '-samples', '5',
                            '-block', '48'],
                            stdout=subprocess.DEVNULL)
            
            # If it fails, just use default values
            if fs.returncode != 0:
                x_axis_tilt = '0'
                tomopitch_z = '0'
                z_shift = '0'
                thickness = str(thickness)
                print(f'{tiltseries}: findsection failed, using default values {tomopitch_z}, thickness {thickness}.')
            
            
            else:    
                # Else, get tomopitch
                tomopitch = subprocess.run([
                    'tomopitch',
                    '-mod', tomopitch_file,
                    '-extra', str(extra_thickness),
                    '-scale', str(8)], capture_output=True, text=True).stdout.splitlines()                
                # Check for failed process again. 
                if any(l.startswith('ERROR') for l in tomopitch):
                    x_axis_tilt = '0'
                    tomopitch_z = '0'
                    z_shift = '0'
                    thickness = str(thickness)
                    print(f'{tiltseries}: tomopitch failed, using default values {tomopitch_z}, thickness {thickness}.')
                else:    
                    x_axis_tilt = tomopitch[-3].split()[-1]
                    tomopitch_z = tomopitch[-1].split(';')
                    z_shift = tomopitch_z[0].split()[-1]
                    thickness = tomopitch_z[1].split()[-1]
                    print(f'{tiltseries}: Succesfully estimated tomopitch {tomopitch_z} and thickness {thickness}.')

        # Final reconstruction
        if bin == 1:
            ali_file_mtf_bin = ali_file_mtf
            print(f'{tiltseries}: Not binned.')

        else:
            subprocess.run(['binvol', '-x', str(bin), '-y', str(bin), '-z', '1', ali_file_mtf, ali_file_mtf_bin],
                           stdout=subprocess.DEVNULL)
            os.remove(ali_file_mtf)
            print(f'{tiltseries}: Binned to {bin}.')

        
        subprocess.run(['tilt']
                       + (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []) +
                       ['-InputProjections', ali_file_mtf_bin,
                        '-OutputFile', full_rec_file,
                        '-IMAGEBINNED', str(bin),
                        '-XAXISTILT', x_axis_tilt,
                        '-TILTFILE', f'{rootname}_ali.tlt',
                        '-THICKNESS', thickness,
                        '-RADIAL', '0.35,0.035',
                        '-FalloffIsTrueSigma', '1',
                        '-SCALE', '0.0,0.05',
                        '-PERPENDICULAR',
                        '-MODE', '2',
                        '-FULLIMAGE', f'{full_y} {full_x}',
                        '-SUBSETSTART', '0,0',
                        '-AdjustOrigin',
                        '-ActionIfGPUFails', '1,2',
                        '-OFFSET', '0.0',
                        '-SHIFT', f'0.0,{z_shift}',
                        '-UseGPU', '0'],
                        stdout=subprocess.DEVNULL)
        
        os.remove(ali_file_mtf_bin)

        print(f'{tiltseries}: Finished reconstruction.')

        # Trim
        # TODO: Consider case where image is not rotated 90deg in relation to mdoc (TiltAxis property?)
        thickness = int(thickness)
        subprocess.run(['trimvol',
                        '-x', f'1,{full_y / bin:.0f}',
                        '-y', f'1,{full_x / bin:.0f}',
                        '-z', f'1,{thickness / bin:.0f}',
                        '-sx', f'1,{full_y / bin:.0f}',
                        '-sy', f'1,{full_x / bin:.0f}',
                        '-sz', f'{thickness / bin / 3:.0f},{thickness / bin * 2 / 3:.0f}',
                        '-f', '-rx',
                        full_rec_file, rec_file],
                        stdout=subprocess.DEVNULL)
        
        print(f'{tiltseries}: Finished trimming.')

        os.remove(full_rec_file)
        if path.isfile('mask3000.mrc'):
            os.remove('mask3000.mrc')
