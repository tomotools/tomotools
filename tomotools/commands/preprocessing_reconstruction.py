import os
import shutil
import subprocess
import mrcfile
from glob import glob
from os import mkdir
from os import path
from os.path import abspath, basename, join
from pathlib import Path

import click

from tomotools.utils import mdocfile
from tomotools.utils.micrograph import Micrograph, sem2mc2
from tomotools.utils.movie import Movie
from tomotools.utils.tiltseries import TiltSeries, align_with_areTomo, dose_filter
from tomotools.utils.tomogram import Tomogram


@click.command()
@click.option('--cpus', default=8, show_default=True, help='Number of CPUs, passed to justblend')
@click.argument('input_files', nargs=-1)
@click.argument('output_dir')
def blend_montages(cpus, input_files, output_dir):
    """Blend montages using justblend.

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
@click.option('--rotationandflip', type=int,
              help='Override RotationAndFlip for the gain reference (useful if it\'s not in the mdoc file)')
@click.option('--group', type=int, default=1, show_default=True,
              help='Group frames, useful for low-dose frames. Also see motioncor2 manual')
@click.option('--gpus', type=str, default=None,
              help='GPUs list, comma separated (e.g. 0,1), determined automatically if not passed')
@click.option('--exposuredose', type=float, default=None)
@click.option('--stack/--nostack', is_flag=True, default=True,
              help='Create a tilt-series stack or keep the motion-corrected frames as they are')
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.argument('output_dir', type=click.Path(writable=True))
def batch_prepare_tiltseries(splitsum, mcbin, reorder, frames, gainref, rotationandflip, group, gpus, exposuredose,
                             stack,
                             input_files, output_dir):
    """Prepare tilt-series for reconstruction.

    This function runs MotionCor2 on movie frames, stacks the motion-corrected frames and sorts them by tilt-angle.
    The input files may be individual .mrc/.st tilt-series files or directories containing them.
    In the latter case, a simple search for MRC and ST files will be run (using the globs *.mrc and *.st).
    
    Every input file requires a corresponding .mdoc file. 
    The last argument is the output dir. It will be created if it doesn't exist.
    """
    # Convert all directories into a list of MRC/ST files
    input_files_temp = list()
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_files_temp.append(input_file)
        elif input_file.is_dir():
            input_files_temp += glob(path.join(input_file, '*.mrc'))
            input_files_temp += glob(path.join(input_file, '*.st'))
    input_files = input_files_temp

    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        output_dir.mkdir(parents=True)

    for input_file in input_files:
        if input_file.suffix == '.mdoc':
            mdoc = mdocfile.read(input_file)
            input_file = input_file.with_suffix('')
        else:
            try:
                mdoc = mdocfile.read(Path(str(input_file) + '.mdoc'))
            except FileNotFoundError:
                print(f'No MDOC file found for {input_file}')
                continue
        if mdoc.get('Montage', 0) == 1:
            print(f'Skipping {input_file} because it is a montage')
            continue
        # Identify batch / anchoring files, as they all should have an abs tilt angle < 1 for all sections -> feels a bit hacky
        if all(abs(section['TiltAngle']) < 1 for section in mdoc['sections']):
            print(f'{input_file} is not a tilt series, as all TiltAngles are near zero. Skipping.')
            continue

        # File is a tilt-series, look for subframes
        print(f'Looking for movie frames for {input_file}, which looks like a tilt series')
        for section in mdoc['sections']:
            subframes_root_path = path.dirname(input_file) if frames is None else frames
            section['SubFramePath'] = mdocfile.find_relative_path(
                Path(subframes_root_path),
                Path(section.get('SubFramePath', '').replace('\\', path.sep))
            )
            if exposuredose is not None:
                section['ExposureDose'] = exposuredose

        if any(section['ExposureDose'] == 0 for section in mdoc['sections']) and exposuredose is None:
            print(f'{input_file} has no ExposureDose set. This might lead to problems down the road!')

            # Check if all subframes were found
        try:
            movies = [Movie(section['SubFramePath'], section['TiltAngle']) for section in mdoc['sections']]
        except FileNotFoundError:
            print(f'Not all movie frames were found for {input_file}, not using them')
            if reorder:
                print(f'Running newstack -reorder on {input_file}')
                subprocess.run(['newstack',
                                '-reorder', str(1),
                                '-mdoc',
                                '-in', input_file,
                                '-ou', str(output_dir.joinpath(input_file.name))])
            else:
                print(f'Just copying {input_file} to {output_dir}')
                subprocess.run(['cp',
                                input_file,
                                output_dir])
                subprocess.run(['cp',
                                f'{input_file}.mdoc',
                                output_dir])
            continue

        print(f'Subframes were found for {input_file}, will run MotionCor2 on them')
        # Get rotation and flip of Gain reference from mdoc file property
        mcrot, mcflip = None, None
        if rotationandflip is not None:
            rotationandflip = mdoc['sections'][0].get('RotationAndFlip', None)
            mcrot, mcflip = sem2mc2(rotationandflip)

        frames_corrected_dir = output_dir.joinpath('frames_corrected')
        micrographs = Micrograph.from_movies(movies, frames_corrected_dir,
                                             splitsum=splitsum, binning=mcbin, mcrot=mcrot, mcflip=mcflip,
                                             group=group, override_gainref=gainref, gpus=gpus)

        if stack:
            tilt_series = TiltSeries.from_micrographs(micrographs, output_dir.joinpath(input_file.name),
                                                      orig_mdoc_path=mdoc['path'], reorder=True)
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created {tilt_series.path}')
        else:
            for micrograph in micrographs:
                micrograph.path.rename(output_dir.joinpath(micrograph.path.name))
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created micrograph images in {output_dir}')


@click.command()
@click.option('--move', is_flag=True, help="Move files into a subdirectory")
@click.option('--local/--global', is_flag=True, default=False, show_default=True,
              help="Local or global alignments (local takes significantly longer)")
@click.option('--extra-thickness', default=0, show_default=True, help="Extra thickness in unbinned pixels")
@click.option('-b', '--bin', default=1, show_default=True, help="Final reconstruction binning")
@click.option('--sirt', default=5, show_default=True, help="SIRT-like filter iterations")
@click.option('--keep-ali-stack/--delete-ali-stack', is_flag=True, default=False, show_default=True,
              help="Keep or delete the non-dose-filtered aligned stack (useful for Relion)")
@click.option('--previous', is_flag = True, help="Use previous alignment found in the folder.")
@click.option('--do-evn-odd', is_flag = True, help="Perform alignment, dose-filtration and reconstruction also on EVN/ODD stacks, if present. Needed for later cryoCARE processing. If the EVN/ODD stacks are found, they will be moved and tilts will be excluded as with the original stack regardless of this flag.")
@click.option('--batch-file', type=click.Path(exists=True, dir_okay=False),help = "You can pass a tab-separated file with tilt series names and views to exclude before alignment and reconstruction.")
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
def reconstruct(move, local, extra_thickness, bin, sirt, keep_ali_stack, previous, do_evn_odd, batch_file, input_files):
    """Align and reconstruct the given tiltseries. 
    
    Optionally moves tilt series and excludes specified tilts. Then runs AreTomo alignment and ultimately dose-filtration and imod WBP reconstruction.   
    """
    # Read in batch tilt exclude file
    if batch_file is not None:
        ts_info = {}
        with open(batch_file) as file:
            for line in file:
                if line != '\n':
                    l=line.split('\t')
                    temp={l[0]: l[1].rstrip()}
                    ts_info.update(temp)

    input_ts = list()
    
    # Sanitize input list to only include the main stack.
    for input_file in input_files:
        if not input_file.endswith('_EVN.mrc') and not input_file.endswith('_ODD.mrc') and not input_file.endswith('.mdoc'):
            input_ts.append(Path(input_file))
    
    for ts in input_ts:
        # merge main EVN ODD into one TiltSeries object
        if path.isfile(ts.with_name(f'{ts.stem}_EVN.mrc')) and path.isfile(ts.with_name(f'{ts.stem}_ODD.mrc')):
            tiltseries = TiltSeries(ts).with_split_files(ts.with_name(f'{ts.stem}_EVN.mrc'), ts.with_name(f'{ts.stem}_ODD.mrc'))
            print(f'Found TiltSeries {ts} with EVN and ODD stacks.')
        else:
            tiltseries = TiltSeries(ts)
            print(f'Found TiltSeries {ts}.')

        if not path.isfile(tiltseries.mdoc):
            raise FileNotFoundError(f'No MDOC file found at {tiltseries.mdoc}')

        # Check for tilts to exclude
        excludetilts = None
        if batch_file is not None:
            if tiltseries in ts_info:
                excludetilts = ts_info[tiltseries]
                print(f'Found tilts to exclude in {batch_file}. Will exclude tilts {excludetilts}.')

        if move:
            dir = tiltseries.path.stem
            mkdir(dir)
            print(f'Move files to subdir {dir}')
            
            shutil.move(tiltseries.path, dir)
            shutil.move(tiltseries.mdoc, dir)
            
            if tiltseries.is_split:
                shutil.move(tiltseries.evn_path, dir)
                shutil.move(tiltseries.odd_path, dir)
                tiltseries = TiltSeries(Path(join(dir,tiltseries.path.name))).with_split_files(Path(join(dir,tiltseries.evn_path.name)), Path(join(dir,tiltseries.odd_path.name)))
            
            else:
                tiltseries = TiltSeries(Path(join(dir,tiltseries.path.name)))
                
        # Run newstack to exclude tilts 
        if excludetilts is not None:
            exclude_file = tiltseries.path.with_name(f'{tiltseries.path.stem}_excludetilts.mrc')
            
            subprocess.run(['newstack',
                            '-in', str(tiltseries.path),
                            '-mdoc',
                            '-quiet',
                            '-exclude', excludetilts,
                            '-ou', str(exclude_file)])
            print(f'Excluded specified tilts from {tiltseries.path}.')
            tiltseries.path = exclude_file
            tiltseries.mdoc = Path(f'{tiltseries.path}.mdoc')
            
            if tiltseries.is_split:
                exclude_evn = tiltseries.evn_path.with_name(f'{tiltseries.path.stem}_excludetilts_EVN.mrc')
                exclude_odd = tiltseries.odd_path.with_name(f'{tiltseries.path.stem}_excludetilts_ODD.mrc')
                
                subprocess.run(['newstack',
                                '-in', str(tiltseries.evn_path),
                                '-quiet',
                                '-exclude', excludetilts,
                                '-ou', str(exclude_evn)])
                subprocess.run(['newstack',
                                '-in', str(tiltseries.odd_path),
                                '-quiet',
                                '-exclude', excludetilts,
                                '-ou', str(exclude_odd)])
                
                tiltseries.evn_path = exclude_evn
                tiltseries.odd_path = exclude_odd
                
                print(f'Excluded specified tilts from EVN and ODD stacks for {tiltseries.path}.')
        
        # Align Stack
        # TODO: somehow decide whether imod or AreTomo should be used!
        tiltseries = align_with_areTomo(tiltseries, local, previous, do_evn_odd)

        # Do dose filtration.
        tiltseries = dose_filter(tiltseries,keep_ali_stack, do_evn_odd)
        
        # Get AngPix
        with mrcfile.mmap(tiltseries.path, mode = 'r') as mrc:
           pix_xy = float(mrc.voxel_size.x)
        
        # Perform reconstruction at bin 8 to find pitch / thickness        
        tomo_pitch = Tomogram.from_tiltseries(tiltseries, bin = 8, do_EVN_ODD = False, trim = False, thickness = str(round(10000 / pix_xy)))
        
        # Try to automatically find edges of tomogram
        pitch_mod = tomo_pitch.path.with_name(f'{tiltseries.path.stem}_pitch.mod')
        
        fs = subprocess.run(['findsection',
                        '-tomo', tomo_pitch.path,
                        '-pitch', pitch_mod,
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
            thickness = str(round(6000 / pix_xy)+extra_thickness)
            print(f'{tiltseries.path}: findsection failed, using default values pitch {tomopitch_z}, thickness {thickness}.')

        else:
            # Else, get tomopitch
            tomopitch = subprocess.run([
                'tomopitch',
                '-mod', pitch_mod,
                '-extra', str(extra_thickness),
                '-scale', str(8)], capture_output=True, text=True).stdout.splitlines()
            # Check for failed process again. 
            if any(l.startswith('ERROR') for l in tomopitch):
                x_axis_tilt = '0'
                tomopitch_z = '0'
                z_shift = '0'
                thickness = str(round(6000 / pix_xy)+extra_thickness)
                print(f'{tiltseries.path}: tomopitch failed, using default values pitch {tomopitch_z}, thickness {thickness}.')
            else:
                x_axis_tilt = tomopitch[-3].split()[-1]
                tomopitch_z = tomopitch[-1].split(';')
                z_shift = tomopitch_z[0].split()[-1]
                thickness = str(int(tomopitch_z[1].split()[-1])+extra_thickness)
                print(f'{tiltseries.path}: Succesfully estimated tomopitch {x_axis_tilt} and thickness {thickness}.')
        
        os.remove(tomo_pitch.path)
        
        # Perform final reconstruction
        Tomogram.from_tiltseries(tiltseries, bin = bin,thickness = thickness, x_axis_tilt=x_axis_tilt, z_shift = z_shift, sirt = sirt, do_EVN_ODD = do_evn_odd)