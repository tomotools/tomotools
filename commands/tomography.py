import os
import shutil
import subprocess
from glob import glob
from os import mkdir
from os import path
from os.path import abspath, basename, join, splitext

import click

from utils import mdocfile, frame_utils


@click.command()
@click.argument('input_files', nargs=-1)
@click.argument('output_dir')
def blend_montages(input_files, output_dir):
    """Blend montages using justblend

    The input files must be montage .mrc/.st files, so usually you will invoke this function with something like:
    blend-montages MMM*.mrc output_dir
    """
    if not path.isdir(output_dir):
        mkdir(output_dir)

    for input_file in input_files:
        os.symlink(abspath(input_file), join(output_dir, basename(input_file)))

    os.chdir(output_dir)
    links = [basename(input_file) for input_file in input_files]
    subprocess.run(['justblend', '--cpus', '32'] + [basename(input_file) for input_file in input_files])
    # Delete temporary files
    for file in links + glob('*.ecd') + glob('*.pl') + glob('*.xef')\
            + glob('*.yef') + glob('*.com') + glob('*.log') + ['processchunks-jb.out']:
        os.remove(file)


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
              help='Use this gain reference instead looking for one in the MDOC files')
@click.option('--group', type=int, default=1, show_default=True,
              help='Group frames, useful for low-dose frames. Also see motioncor2 manual')
@click.option('--gpus', type=str, default=None, help='GPUs list, comma separated (e.g. 0,1), determined automatically if not passed')
@click.option('--exposuredose', type=float, default=None)
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.argument('output_dir', type=click.Path(writable=True))
def batch_prepare_tiltseries(splitsum, mcbin, reorder, frames, gainref, group, gpus, exposuredose, input_files, output_dir):
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
        # File is a tilt-series, look for subframes
        for section in mdoc['sections']:
            subframes_root_path = path.dirname(input_file) if frames is None else frames
            print(f'SubFramePath field: {section.get("SubFramePath", "")}')
            section['SubFramePath'] = mdocfile.find_relative_path(
                subframes_root_path,
                section.get('SubFramePath', '').replace('\\', path.sep)
            )
            if exposuredose is not None:
                section['ExposureDose'] = exposuredose
            print(f'SubFramePath field: {section.get("SubFramePath", "")}')
        # Check if all subframes were found
        subframes = [frame_utils.SubFrame(section['SubFramePath']) for section in mdoc['sections']]
        if all(subframe.files_exist(is_split=False) for subframe in subframes):
            print(f'Subframes were found for {input_file}, will run MotionCor2 on them')
            frames_corrected_dir = path.join(output_dir, 'frames_corrected')
            subframes_corrected = frame_utils.motioncor2(subframes, frames_corrected_dir, splitsum=splitsum,
                                                         binning=mcbin, group=group, override_gainref=gainref, gpus=gpus)
            if reorder:
                subframes_corrected = frame_utils.sort_subframes_list(subframes_corrected)
            stack, stack_mdoc = frame_utils.frames2stack(subframes_corrected,
                                                         path.join(output_dir, path.basename(input_file)),
                                                         overwrite_titles=mdoc['titles'])
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created {path.basename(stack)}')
        else:
            print(f'No subframes were found for {input_file}, will continue without MotionCor2')
            print('Not implemented yet, skipping')
            continue
            # raise NotImplementedError('Sorry, non-motioncor2 path is not implemented yet')

@click.command()
@click.option('--subdirectory/--nosubdirectory', is_flag=True, default=True, show_default=True, help="Move file into a subdirectory")
@click.option('--local_alignment/--global_alignment', is_flag=True, default=False, show_default=True, help="Local or global alignments (local takes significantly longer)")
@click.option('--extra_thickness', default=0, show_default=True, help="Extra thickness in unbinned pixels")
@click.option('-b', '--bin', default=1, show_default=True, help="Final reconstruction binning")
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
def reconstruct(subdirectory, local_alignment, extra_thickness, bin, input_files):
    for tiltseries in input_files:
        mdoc_file = f'{tiltseries}.mdoc'
        if not path.isfile(mdoc_file):
            raise FileNotFoundError(f'No MDOC file found at {mdoc_file}')
        if subdirectory:
            print('Move files to subdir {subdir}')
            subdir = splitext(tiltseries)[0]
            new_tiltseries = join(subdir, basename(tiltseries))
            new_mdoc_file = join(subdir, basename(mdoc_file))
            mkdir(subdir)
            os.rename(tiltseries, new_tiltseries)
            os.rename(mdoc_file, new_mdoc_file)
            tiltseries = new_tiltseries
            mdoc_file = new_mdoc_file

        rootname = splitext(tiltseries)[0]
        ali_file = f'{rootname}_ali.mrc'
        ali_file_bin = f'{rootname}_ali_b{bin}.mrc'
        ali_file_bin8 = f'{rootname}_ali_b8.mrc'
        full_rec_file = f'{rootname}_full_rec.mrc'
        rec_file = f'{rootname}_rec_b{bin}.mrc'
        tlt_file = f'{rootname}.tlt'
        tlt_file_ali = f'{rootname}_ali.tlt'
        tomopitch_file = f'{rootname}.mod'

        # Aretomo
        subprocess.run(['extracttilts', tiltseries, tlt_file])
        subprocess.run(['/opt/aretomo/aretomo',
                        '-InMrc', tiltseries,
                        '-OutMrc', ali_file,
                        '-AngFile', tlt_file,
                        '-VolZ', '0',
                        '-TiltCor', '1'] + (['-Patch', '6', '4'] if local_alignment else []))
        subprocess.run(['mtffilter', '-dtype', '4', '-dfile', mdoc_file, ali_file, f'{rootname}_mtf.mrc'])
        os.replace(f'{rootname}_mtf.mrc', ali_file)

        # Tomo pitch
        subprocess.run(['binvol', '-x', '8', '-y', '8', '-z', '1', ali_file, ali_file_bin8])
        subprocess.run(['tilt',
            '-FakeSIRTiterations', '5',
            '-InputProjections', ali_file_bin8,
            '-OutputFile', full_rec_file,
            '-IMAGEBINNED', '8',
            '-TILTFILE', tlt_file_ali,
            '-THICKNESS', '2000',
            '-RADIAL', '0.35,0.035',
            '-FalloffIsTrueSigma', '1',
            '-SCALE', '0.0,0.05',
            '-PERPENDICULAR',
            '-MODE', '2',
            '-FULLIMAGE', '4092,5760',
            '-SUBSETSTART', '0,0',
            '-AdjustOrigin',
            '-ActionIfGPUFails', '1,2',
            '-OFFSET', '0.0',
            '-SHIFT', '0.0,0.0',
            '-UseGPU', '0'])
        os.remove(ali_file_bin8)
        subprocess.run([
            'findsection',
            '-tomo', full_rec_file,
            '-pitch', tomopitch_file,
            '-scales', '2',
            '-size', '16,1,16',
            '-samples', '5',
            '-block', '48'])
        # Get tomopitch
        tomopitch = subprocess.run([
            'tomopitch',
            '-mod', tomopitch_file,
            '-extra', str(extra_thickness),
            '-scale', str(8)], capture_output=True, text=True).stdout.splitlines()
        x_axis_tilt = tomopitch[-3].split()[-1]
        tomopitch_z = tomopitch[-1].split(';')
        z_shift = tomopitch_z[0].split()[-1]
        thickness = tomopitch_z[1].split()[-1]

        # Final reconstruction
        subprocess.run(['binvol', '-x', str(bin), '-y', str(bin), '-z', '1', ali_file, ali_file_bin])
        subprocess.run([
            'tilt',
                '-FakeSIRTiterations', '5',
                '-InputProjections', ali_file_bin,
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
                '-FULLIMAGE', '4092,5760',
                '-SUBSETSTART', '0,0',
                '-AdjustOrigin',
                '-ActionIfGPUFails', '1,2',
                '-OFFSET', '0.0',
                '-SHIFT', f'0.0,{z_shift}',
                '-UseGPU', '0'])
        os.remove(ali_file_bin)

        # Trim
        bin = int(bin)
        thickness = int(thickness)
        subprocess.run(['trimvol',
            '-x', f'1,{4092/bin:.0f}',
            '-y', f'1,{5760/bin:.0f}',
            '-z', f'1,{thickness/bin:.0f}',
            '-sx', f'1,{4092/bin:.0f}',
            '-sy', f'1,{5760/bin:.0f}',
            '-sz', f'{thickness/bin/3:.0f},{thickness/bin*2/3:.0f}',
            '-f', '-rx',
            full_rec_file, rec_file])
        os.remove(full_rec_file)
