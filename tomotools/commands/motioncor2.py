import shutil
from glob import glob
from os import path
from pathlib import Path

import click

from tomotools.utils import mdocfile
from tomotools.utils.click_utils import generator
from tomotools.utils.micrograph import sem2mc2, Micrograph
from tomotools.utils.movie import Movie
from tomotools.utils.tiltseries import TiltSeries


@click.command()
@click.pass_context
@click.option('--splitsum/--nosplitsum', is_flag=True, default=True, show_default=True,
              help='Create even/odd split sums, e.g. for denoising')
@click.option('--mcbin', '--motioncor_binning', default=2, show_default=True,
              help='Binning parameter passed to MotionCor2')
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
@click.option('-i', '--input-file', 'input_files', multiple=True, type=click.Path(exists=True))
@generator
def motioncor2(ctx, splitsum, mcbin, frames, gainref, rotationandflip, group, gpus, exposuredose,
               stack, input_files):
    """Prepare tilt-series for reconstruction.

    This function runs MotionCor2 on movie frames, stacks the motion-corrected frames and sorts them by tilt-angle.
    The input files may be individual .mrc/.st tilt-series files or directories containing them.
    In the latter case, a simple search for MRC and ST files will be run (using the globs *.mrc and *.st).

    Every input file requires a corresponding .mdoc file.
    The last argument is the output dir. It will be created if it doesn't exist.
    """
    # Convert all directories into a list of MRC/ST files
    print(f'Starting motioncor2 function!')
    output_dir = Path(ctx.obj['OUTPUT_DIR'])
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
    output_dir.mkdir(parents=True, exist_ok=True)
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
                print(
                    f'Not all movie frames were found for {input_file}, specify them using the --frames option. Skipping at this point.')
                continue

        print(f'Subframes were found for {input_file}, will run MotionCor2 on them')
        # Get rotation and flip of Gain reference from mdoc file property
        mcrot, mcflip = None, None
        if rotationandflip is None:
            mdoc_rotflip = mdoc['sections'][0].get('RotationAndFlip', None)
            mcrot, mcflip = sem2mc2(mdoc_rotflip)

        # Grab frame size to estimate appropriate patch numbers
        patch_x, patch_y = [str(round(mdoc['ImageSize'][0] / 800)), str(round(mdoc['ImageSize'][1] / 800))]

        frames_corrected_dir = output_dir / 'frames_corrected'
        micrographs = Micrograph.from_movies(movies, frames_corrected_dir,
                                             splitsum=splitsum, binning=mcbin, mcrot=mcrot, mcflip=mcflip,
                                             group=group, override_gainref=gainref, gpus=gpus, patch_x=patch_x,
                                             patch_y=patch_y)

        if stack:
            tilt_series = TiltSeries.from_micrographs(micrographs, output_dir / input_file.name,
                                                      orig_mdoc_path=mdoc['path'], reorder=True)
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created {tilt_series.path}')
            yield tilt_series.path
        else:
            for micrograph in micrographs:
                micrograph.path = micrograph.path.rename(output_dir / micrograph.path.name)
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created micrograph images in {output_dir}')
            for micrograph in micrographs:
                yield micrograph.path
