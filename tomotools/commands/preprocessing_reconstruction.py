import os
import shutil
import subprocess
from glob import glob
from os import mkdir
from os import path
from os.path import abspath, basename, join
from pathlib import Path
from warnings import warn

import click
import mrcfile

from tomotools.utils import mdocfile
from tomotools.utils.micrograph import Micrograph, sem2mc2
from tomotools.utils.movie import Movie
from tomotools.utils.tiltseries import TiltSeries, align_with_areTomo, align_with_imod, dose_filter
from tomotools.utils.tomogram import Tomogram


@click.command()
@click.option('--cpus', type=int, default=8, show_default=True, help='Number of CPUs, passed to justblend')
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
@click.option('--rotationandflip', type=int, default=None,
              help='Override RotationAndFlip for the gain reference (useful if it\'s not in the mdoc file)')
@click.option('--group', type=int, default=1, show_default=True,
              help='Group frames, useful for low-dose frames. Also see motioncor2 manual')
@click.option('--gpus', type=str, default=None,
              help='GPUs list, comma separated (e.g. 0,1), determined automatically if not passed')
@click.option('--exposuredose', type=float, default=None,
              help='Pass ExposureDose per tilt to override value in mdoc file.')
@click.option('--stack/--nostack', is_flag=True, default=True,
              help='Create a tilt-series stack or keep the motion-corrected frames as they are.')
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.argument('output_dir', type=click.Path(writable=True))
def batch_prepare_tiltseries(splitsum, mcbin, reorder, frames, gainref, rotationandflip, group, gpus, exposuredose,
                             stack, input_files, output_dir):
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
            input_files_temp += [Path(p) for p in glob(path.join(input_file, '*.mrc'))]
            input_files_temp += [Path(p) for p in glob(path.join(input_file, '*.st'))]
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

        # File is a tilt-series.
        print(f'Working on {input_file}, which looks like a tilt series')
        
        # Fix ExposureDose is required
        if exposuredose is not None:
            for section in mdoc['sections']:         
                section['ExposureDose'] = exposuredose
        
        if any(section['ExposureDose'] == 0 for section in mdoc['sections']) and exposuredose is None:
            print(f'{input_file} has no ExposureDose set. This might lead to problems down the road!')
         
        # Are any SubFrames present?    
        if any('SubFramePath' in section for section in mdoc['sections']):    
            for section in mdoc['sections']:
                subframes_root_path = path.dirname(input_file) if frames is None else frames
                section['SubFramePath'] = mdocfile.find_relative_path(
                    Path(subframes_root_path),
                    Path(section.get('SubFramePath', '').replace('\\', path.sep)))

            try:
                movies = [Movie(section['SubFramePath'], section['TiltAngle']) for section in mdoc['sections']]
            except FileNotFoundError:
                print(f'Not all movie frames were found for {input_file}, specify them using the --frames option. Skipping at this point.')
                continue
            
        else:
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
            mcrot, mcflip = sem2mc2(rotationandflip)
        elif 'RotationAndFlip' in mdoc['sections'][0]:
            mdoc_rotflip = mdoc['sections'][0]['RotationAndFlip']
            mcrot, mcflip = sem2mc2(mdoc_rotflip)

        # Grab frame size to estimate appropriate patch numbers
        patch_x, patch_y = [str(round(mdoc['ImageSize'][0] / 800)), str(round(mdoc['ImageSize'][1] / 800))]

        frames_corrected_dir = output_dir.joinpath('frames_corrected')
        micrographs = Micrograph.from_movies(movies, frames_corrected_dir,
                                             splitsum=splitsum, binning=mcbin, mcrot=mcrot, mcflip=mcflip,
                                             group=group, override_gainref=gainref, gpus=gpus, patch_x=patch_x,
                                             patch_y=patch_y)

        if stack:
            tilt_series = TiltSeries.from_micrographs(micrographs, output_dir / input_file.name,
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
@click.option('--zero-xaxis-tilt', is_flag=True,
              help='Run tomogram positioning, but keep X-axis tilt at zero. Remember to add some extra thickness if you do this, otherwise you might truncate your tomogram')
@click.option('--previous', is_flag=True, help="Use previous alignment found in the folder.")
@click.option('--gpu', type=str, default=None, help="Specify which GPUs to use for AreTomo. Default: GPU 0")
@click.option('--do-evn-odd', is_flag=True,
              help="Perform alignment, dose-filtration and reconstruction also on EVN/ODD stacks, if present. Needed for later cryoCARE processing. If the EVN/ODD stacks are found, they will be moved and tilts will be excluded as with the original stack regardless of this flag.")
@click.option('--batch-file', type=click.Path(exists=True, dir_okay=False),
              help="You can pass a tab-separated file with tilt series names and views to exclude before alignment and reconstruction.")
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
def reconstruct(move, local, extra_thickness, bin, sirt, keep_ali_stack, zero_xaxis_tilt, previous, gpu, do_evn_odd,
                batch_file, input_files):
    """Align and reconstruct the given tiltseries. 
    
    Optionally moves tilt series and excludes specified tilts. Then runs AreTomo alignment and ultimately dose-filtration and imod WBP reconstruction.   
    """
    # Read in batch tilt exclude file
    ts_info = {}
    if batch_file is not None:
        with open(batch_file) as file:
            for line in file:
                if line != '\n':
                    l = line.rsplit(maxsplit=1)
                    if len(l) != 2:
                        warn(f'Skipping invalid line in the batch file: "{line}"')
                        continue
                    temp = {l[0]: l[1].rstrip()}
                    ts_info.update(temp)

    input_ts = list()
    
    # Sanitize input list to only include the main stack and create TiltSeries objects
    for input_file in input_files:
        if input_file.endswith('_EVN.mrc') or input_file.endswith('_ODD.mrc') or input_file.endswith('.mdoc'):
            print(f'Skipping file {input_file}')
            continue
        else:
            print(f'Found TiltSeries {input_file}.')
            tiltseries = TiltSeries(Path(input_file))
            # Look for MDOC file
            if not path.isfile(tiltseries.mdoc):
                raise FileNotFoundError(f'No MDOC file found at {tiltseries.mdoc}')
            # Check if there are EVN/ODD files for this tiltseries
            evn_path = tiltseries.path.with_name(f'{tiltseries.path.stem}_EVN.mrc')
            odd_path = tiltseries.path.with_name(f'{tiltseries.path.stem}_ODD.mrc')
            if evn_path.is_file() and odd_path.is_file():
                print(f'Found EVN and ODD stacks for {input_file}.')
                tiltseries = tiltseries.with_split_files(evn_path, odd_path)
            input_ts.append(tiltseries)
    
    # Iterate over the tiltseries objects and align and reconstruct
    for tiltseries in input_ts:
        excludetilts = None
        if str(tiltseries.path) in ts_info:
            excludetilts = ts_info[str(tiltseries.path)]
            print(f'Found tilts to exclude in {batch_file}. Will exclude tilts {excludetilts}.')

        if move:
            dir = tiltseries.path.with_suffix('')
            dir.mkdir()
            print(f'Move files to subdir {dir}')
            tiltseries.path = tiltseries.path.rename(dir / tiltseries.path.name)
            tiltseries.mdoc = tiltseries.mdoc.rename(dir / tiltseries.mdoc.name)
            if tiltseries.is_split:
                tiltseries.evn_path = tiltseries.evn_path.rename(dir / tiltseries.evn_path.name)
                tiltseries.odd_path = tiltseries.odd_path.rename(dir / tiltseries.odd_path.name)
                    
        # Exclude tilts
        if excludetilts is not None:
            exclude_cmd = ['excludeviews', '-views', excludetilts, '-delete']
            subprocess.run(exclude_cmd + [str(tiltseries.path)])
            print(f'Excluded specified tilts from {tiltseries.path}.')

            if tiltseries.is_split:
                subprocess.run(exclude_cmd + [str(tiltseries.evn_path)])
                subprocess.run(exclude_cmd + [str(tiltseries.odd_path)])
                print(f'Excluded specified tilts from EVN and ODD stacks for {tiltseries.path}.')
                
            # To clean the directory up a bit, move the excluded views to a separate subdirectory
            excludedir = join(tiltseries.path.parent, 'excluded_views')
            if not path.isdir(excludedir):
                os.mkdir(excludedir)
            
            for file in glob(join(tiltseries.path.parent,'*_cutviews0.*')):
                os.rename(file, join(excludedir,Path(file).name))
            
            with open(join(excludedir,'README'), mode = 'w+') as file:
                file.write('Restore full stack by moving these files back and running command excludeviews -restore')
                
                            
        # Align Stack
        # If previous is passed and imod alignment file .xf is found, use imod. Otherwise, use AreTomo.
        # TODO: Once imod batch alignment is implemented, figure out a better way of doing this, eg. with a flag (--imod / --aretomo)
        
        if previous and path.isfile(tiltseries.path.with_suffix('.xf')):
            tiltseries_ali = align_with_imod(tiltseries, previous, do_evn_odd)     
            
        else:
            tiltseries_ali = align_with_areTomo(tiltseries, local, previous, do_evn_odd, gpu)

        # Do dose filtration.
        tiltseries_dosefiltered = dose_filter(tiltseries_ali, do_evn_odd)

        # Get AngPix
        with mrcfile.mmap(tiltseries.path, mode='r') as mrc:
            pix_xy = float(mrc.voxel_size.x)

        # Perform reconstruction at bin 8 to find pitch / thickness        
        tomo_pitch = Tomogram.from_tiltseries(tiltseries_dosefiltered, bin=8, do_EVN_ODD=False, trim=False,
                                              thickness=round(10000 / pix_xy))

        # Try to automatically find edges of tomogram
        pitch_mod = tomo_pitch.path.with_name(f'{tiltseries.path.stem}_pitch.mod')

        # The parameters for findsection are taken from the etomo source code
        fs = subprocess.run(['findsection',
                             '-tomo', tomo_pitch.path,
                             '-pitch', pitch_mod,
                             '-scales', '2',
                             '-size', '16,1,16',
                             '-samples', '5',
                             '-block', '48'],
                            stdout=subprocess.DEVNULL)
        x_axis_tilt: float = 0
        z_shift: float = 0
        thickness: int = round(6000 / pix_xy) + extra_thickness
        # If it fails, just use default values
        if fs.returncode != 0:
            print(
                f'{tiltseries.path}: findsection failed, using default values: thickness {thickness}, z_shift {z_shift}, x_axis_tilt {x_axis_tilt}')
        else:
            # Else, get tomopitch
            tomopitch = subprocess.run([
                'tomopitch',
                '-mod', pitch_mod,
                '-extra', str(extra_thickness),
                '-scale', str(8)], capture_output=True, text=True).stdout.splitlines()
            # Check for failed process again. 
            if any(l.startswith('ERROR') for l in tomopitch):
                print(
                    f'{tiltseries.path}: tomopitch failed, using default values: thickness {thickness}, z_shift {z_shift}, x_axis_tilt {x_axis_tilt}')
            else:
                x_axis_tilt = float(tomopitch[-3].split()[-1])
                z_shift_line, thickness_line = tomopitch[-1].split(';')
                z_shift = z_shift_line.split()[-1]
                thickness = int(thickness_line.split()[-1]) + extra_thickness
                print(
                    f'{tiltseries.path}: Succesfully estimated tomopitch: thickness {thickness}, z_shift {z_shift}, x_axis_tilt {x_axis_tilt}')
        pitch_mod.unlink(missing_ok=True)
        tomo_pitch.path.unlink(missing_ok=True)
        if zero_xaxis_tilt:
            print('Setting X-axis tilt to zero due to --zero-xaxis-tilt option')
            x_axis_tilt = 0

        # Perform final reconstruction
        Tomogram.from_tiltseries(tiltseries_dosefiltered, bin=bin, thickness=thickness, x_axis_tilt=x_axis_tilt,
                                 z_shift=z_shift,
                                 sirt=sirt, do_EVN_ODD=do_evn_odd)

        if not keep_ali_stack:
            tiltseries_ali.delete_files(delete_mdoc=False)
        tiltseries_dosefiltered.delete_files(delete_mdoc=False)
