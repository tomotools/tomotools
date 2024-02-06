import os
import shutil
import subprocess
from glob import glob
from os import mkdir, path
from os.path import abspath, basename, join
from pathlib import Path

import click

from tomotools.utils import mdocfile
from tomotools.utils.micrograph import Micrograph, sem2mc2
from tomotools.utils.movie import Movie
from tomotools.utils.tiltseries import (
    TiltSeries,
    align_with_areTomo,
    align_with_imod,
    convert_input_to_TiltSeries,
    dose_filter,
)
from tomotools.utils.tomogram import Tomogram


@click.command()
@click.option(
    "--cpus",
    type=int,
    default=8,
    show_default=True,
    help="Number of CPUs, passed to justblend",
)
@click.argument("input_files", nargs=-1)
@click.argument("output_dir")
def blend_montages(cpus, input_files, output_dir):
    """Blend montages using justblend.

    The input files must be montage .mrc/.st files, example:
    blend-montages MMM*.mrc output_dir
    """
    if not path.isdir(output_dir):
        mkdir(output_dir)

    for input_file in input_files:
        os.symlink(abspath(input_file), join(output_dir, basename(input_file)))

    wd = os.getcwd()

    os.chdir(output_dir)
    links = [basename(input_file) for input_file in input_files]
    subprocess.run(
        ["justblend", "--cpus", str(cpus)]
        + [basename(input_file) for input_file in input_files]
    )
    # Delete temporary files
    for file in (
        links
        + glob("*.ecd")
        + glob("*.pl")
        + glob("*.xef")
        + glob("*.yef")
        + glob("*.com")
        + glob("*.log")
        + ["processchunks-jb.out"]
    ):
        os.remove(file)

    os.chdir(wd)


@click.command()
@click.option(
    "--splitsum/--nosplitsum",
    is_flag=True,
    default=True,
    show_default=True,
    help="Create even/odd split sums, e.g. for denoising",
)
@click.option(
    "--mcbin",
    "--motioncor_binning",
    default=2,
    show_default=True,
    help="Binning parameter passed to MotionCor2",
)
@click.option(
    "--reorder/--noreorder",
    is_flag=True,
    default=True,
    show_default=True,
    help="Sort tilt-series by angle in ascending order",
)
@click.option(
    "--frames",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="If your frames are not automatically found, pass frame directory.",
)
@click.option(
    "--gainref",
    type=click.Path(exists=True, dir_okay=False),
    help="Use this gain reference instead looking for one in the Subframe MDOC files",
)
@click.option(
    "--rotationandflip",
    type=int,
    default=None,
    help="Override RotationAndFlip for the gain reference, else read from mdoc.",
)
@click.option(
    "--group",
    type=int,
    default=1,
    show_default=True,
    help="Group frames, useful for low-dose frames. Also see motioncor2 manual.",
)
@click.option(
    "--patch/--global",
    is_flag=True,
    default=False,
    show_default=True,
    help="Perform full-frame or patch alignment.",
)
@click.option(
    "--gpu",
    type=str,
    default=None,
    help="GPUs to use, eg. 0,1. Default: all available",
)
@click.option(
    "--exposuredose",
    type=float,
    default=None,
    help="Pass ExposureDose per tilt to override value in mdoc file.",
)
@click.option(
    "--stack/--nostack",
    is_flag=True,
    default=True,
    help="Create a tilt-series stack or keep the motion-corrected frames as they are.",
)
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
@click.argument("output_dir", type=click.Path(writable=True))
# TODO: Fix complexity error C901
def batch_prepare_tiltseries(
    splitsum,
    mcbin,
    reorder,
    frames,
    gainref,
    rotationandflip,
    group,
    gpu,
    patch,
    exposuredose,
    stack,
    input_files,
    output_dir,
):
    """Prepare tilt-series for reconstruction.

    This function runs MotionCor2 on movie frames, stacks the motion-corrected frames
    and sorts them by tilt-angle.

    The input files may be individual .mrc/.st tilt-series files
    or directories containing them.
    In the latter case, a simple search for MRC and ST files will be run
    (using the globs *.mrc and *.st).
    Every input file requires a corresponding .mdoc file.

    The last argument is the output dir. It will be created if it doesn't exist.
    """
    # Convert all directories into a list of MRC/ST files
    input_files_temp = []
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_files_temp.append(input_file)
        elif input_file.is_dir():
            input_files_temp += [Path(p) for p in glob(path.join(input_file, "*.mrc"))]
            input_files_temp += [Path(p) for p in glob(path.join(input_file, "*.st"))]
    input_files = input_files_temp

    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        output_dir.mkdir(parents=True)

    for input_file in input_files:
        if input_file.suffix == ".mdoc":
            mdoc = mdocfile.read(input_file)
            input_file = input_file.with_suffix("")
        else:
            try:
                mdoc = mdocfile.read(Path(str(input_file) + ".mdoc"))
            except FileNotFoundError:
                print(f'No MDOC file found for {input_file}. \n')
                continue
        if mdoc.get('Montage', 0) == 1:
            print(f'Skipping {input_file} because it is a montage. \n')
            continue
        # Identify batch / anchoring files, using two criteria:
        # 1. Fewer than three sections
        # 2. abs(tilt angle) < 1 for all sections -> feels a bit hacky, but works
        elif len(mdoc["sections"]) < 3:
            print(f"{input_file} has fewer than three sections. Skipping.")
            continue
        elif all(abs(section["TiltAngle"]) < 1 for section in mdoc["sections"]):
            print(
                f"{input_file} is not a tilt series, all angles near 0. Skipping."
            )
            continue

        # File is a tilt-series.
        print(f"\nWorking on {input_file}, which looks like a tilt series")

        # Fix ExposureDose if required
        if exposuredose is not None:
            for section in mdoc["sections"]:
                section["ExposureDose"] = exposuredose

        if (
            any(section["ExposureDose"] == 0 for section in mdoc["sections"])
            and exposuredose is None
        ):
            print(
                f"{input_file} has no ExposureDose set. This might lead to problems!"
            )

        # Are any SubFrames present?
        if any("SubFramePath" in section for section in mdoc["sections"]):
            for section in mdoc["sections"]:
                subframes_root_path = (
                    path.dirname(input_file) if frames is None else frames
                )
                section["SubFramePath"] = mdocfile.find_relative_path(
                    Path(subframes_root_path),
                    Path(section.get("SubFramePath", "").replace("\\", path.sep)),
                )

            try:
                movies = [
                    Movie(section["SubFramePath"], section["TiltAngle"])
                    for section in mdoc["sections"]
                ]
            except FileNotFoundError:
                print(
                    f"Movie frames not found for {input_file}, use --frames. Skipping."
                )
                continue

        else:
            if reorder:
                print(f'Running newstack -reorder on {input_file}. \n')
                subprocess.run(['newstack',
                                '-reorder', str(1),
                                '-mdoc',
                                '-in', input_file,
                                '-ou', str(output_dir.joinpath(input_file.name))])
            else:
                print(f'Just copying {input_file} to {output_dir}. \n')
                subprocess.run(['cp',
                                input_file,
                                output_dir])
                subprocess.run(['cp',
                                f'{input_file}.mdoc',
                                output_dir])
            continue

        print(f'Subframes were found for {input_file}, will run MotionCor2 on them.')

        # Get rotation and flip of Gain reference from mdoc file property
        mcrot, mcflip = None, None
        if rotationandflip is not None:
            mcrot, mcflip = sem2mc2(rotationandflip)
        elif "RotationAndFlip" in mdoc["sections"][0]:
            mdoc_rotflip = mdoc["sections"][0]["RotationAndFlip"]
            mcrot, mcflip = sem2mc2(mdoc_rotflip)

        # Grab frame size to estimate appropriate patch numbers
        # Will only be used if --patch is specified
        patch_x, patch_y = [
            str(round(mdoc["ImageSize"][0] / 800)),
            str(round(mdoc["ImageSize"][1] / 800)),
        ]

        frames_corrected_dir = output_dir.joinpath("frames_corrected")
        if frames_corrected_dir.is_dir():
            print("Temporary motioncor2 directory already exists, will overwrite it")
            shutil.rmtree(frames_corrected_dir)

        micrographs = Micrograph.from_movies(
            movies,
            frames_corrected_dir,
            splitsum=splitsum,
            binning=mcbin,
            mcrot=mcrot,
            mcflip=mcflip,
            group=group,
            override_gainref=gainref,
            gpu=gpu,
            patch=patch,
            patch_x=patch_x,
            patch_y=patch_y,
        )

        if stack:
            tilt_series = TiltSeries.from_micrographs(
                micrographs,
                output_dir / input_file.name,
                orig_mdoc_path=mdoc["path"],
                reorder=True,
            )
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created {tilt_series.path}. \n')

        else:
            for micrograph in micrographs:
                micrograph.path.rename(output_dir.joinpath(micrograph.path.name))
            shutil.rmtree(frames_corrected_dir)
            print(f'Successfully created micrograph images in {output_dir}. \n')


@click.command()
@click.option("--move", is_flag=True, help="Move files into a subdirectory")
@click.option(
    "--local/--global",
    is_flag=True,
    default=False,
    show_default=True,
    help="Local or global alignments (local takes significantly longer)",
)
@click.option('-d','--thickness', default=None, show_default=True,
              help="Total thickness in unbinned pixels")
@click.option(
    "--extra-thickness",
    default=0,
    show_default=True,
    help="Extra thickness in unbinned pixels",
)
@click.option(
    "--ali-d",
    default = 250,
    show_default = True,
    help="Sample thickness passed to AreTomo for optimal alignment, in nm.")
@click.option(
    "-b", "--bin", default=1, show_default=True, help="Final reconstruction binning"
)
@click.option(
    "--sirt",
    default=5,
    show_default=True,
    help="SIRT-like filter iterations"
)
@click.option('--aretomo/--imod',
              is_flag=True,
              default=True,
              show_default=True,
              help="Use AreTomo or imod for alignment.")
@click.option(
    "--previous",
    is_flag=True,
    default=False,
    help="Use previous alignment found in the folder."
)
@click.option(
    "--gpu",
    type=str,
    default=None,
    help="Specify which GPUs to use for AreTomo. [default: all]",
)
@click.option('--skip-positioning',
              is_flag=True,
              default=False,
              show_default=True,
              help='Skip tomogram positioning. Useful for STA.')
@click.option(
    "--do-evn-odd",
    is_flag=True,
    default=False,
    show_default = True,
    help="Reconstruct ENV/ODD stacks also.",
)
@click.option(
    "--bytes/--nobytes",
    is_flag=True,
    default=True,
    show_default=True,
    help="Convert tomogram to bytes after rotation?",
)
@click.option(
    "--batch-file",
    type=click.Path(exists=True, dir_okay=False),
    help="Pass a tab-separated file with tilt series names and views to exclude.",
)
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
# TODO: Fix complexity error C901
def reconstruct(
    move,
    thickness,
    local,
    aretomo,
    extra_thickness,
    bin,
    ali_d,
    sirt,
    skip_positioning,
    previous,
    gpu,
    do_evn_odd,
    bytes,
    batch_file,
    input_files,
):
    r"""Align and reconstruct the given tiltseries.

    Optionally moves tilt series and excludes specified tilts.
    Then runs AreTomo alignment, dose-filtration and imod WBP reconstruction.
    EVN/ODD stacks will always be moved and tilts excluded, but alignment and
    reconstruction will only be performed if the --do-evn-odd flag is passed.

    Batch file for tilt exclusion should look like this (tab-separated):
    TS_01.mrc    1,39-41 \n
    TS_02.mrc    1-4,41
    """
    # Exclusion and previous clash with each other!
    if previous and batch_file is not None:
        raise ValueError(f"You passed the flag --previous, but also want to exclude the tilts specified in {batch_file}. \n This will mess up alignment files. \n Either the tilts were already excluded in the initial run, then you can skip the --batch-file, or you want to add exclusions, then you have to skip the --previous flag. \n") #noqa: E501

    # Read in batch tilt exclude file
    ts_info = {}
    if batch_file is not None:
        with open(batch_file) as file:
            for line in file:
                if line != "\n":
                    lsplit = line.rsplit(maxsplit=1)
                    if len(lsplit) != 2:
                        print(f'Skipping invalid line in the batch file: "{line}"')
                        continue
                    temp = {lsplit[0]: lsplit[1].rstrip()}
                    ts_info.update(temp)

    # Iterate over the tiltseries objects and align and reconstruct
    input_ts = convert_input_to_TiltSeries(input_files)

    for tiltseries in input_ts:

        print(f"\nNow working on {tiltseries.path.name}.")

        if move:
            tsdir = tiltseries.path.with_suffix('')
            tsdir.mkdir()
            print(f'Moving files to subdir {tsdir}.')
            tiltseries.path = tiltseries.path.rename(tsdir / tiltseries.path.name)
            tiltseries.mdoc = tiltseries.mdoc.rename(tsdir / tiltseries.mdoc.name)
            if tiltseries.is_split:
                tiltseries.evn_path = tiltseries.evn_path.rename(tsdir / tiltseries.evn_path.name) #noqa: E501
                tiltseries.odd_path = tiltseries.odd_path.rename(tsdir / tiltseries.odd_path.name) #noqa: E501

        # If imod alignment is wanted and no previous tag is passed, stop here
        # imod batch alignment can handle the rest!
        if not aretomo and not previous:
            print(f'Moved {tiltseries.path.name} into subfolder. Continue in etomo. \n')
            continue

        if batch_file is not None:
            # Check for Tilts to exclude
            excludetilts = None
            if tiltseries.path.name in ts_info:
                excludetilts = ts_info[str(tiltseries.path.name)]
                print(f'Will exclude tilts {excludetilts}.')

            if excludetilts is not None:
                exclude_cmd = ['excludeviews', '-views', excludetilts, '-delete']
                subprocess.run(exclude_cmd + [str(tiltseries.path)],
                               stdout=subprocess.DEVNULL)
                print(f'Excluded specified tilts from {tiltseries.path}.')

                if tiltseries.is_split:
                    subprocess.run(exclude_cmd + [str(tiltseries.evn_path)], stdout=subprocess.DEVNULL) #noqa: E501
                    subprocess.run(exclude_cmd + [str(tiltseries.odd_path)], stdout=subprocess.DEVNULL) #noqa: E501
                    print('Excluded specified tilts from EVN and ODD stacks.')

                # Move the excluded views to a separate subdirectory
                excludedir = join(tiltseries.path.parent, 'excluded_views')
                if not path.isdir(excludedir):
                    os.mkdir(excludedir)

                for file in glob(join(tiltseries.path.parent,'*_cutviews0.*')):
                    os.rename(file, join(excludedir,Path(file).name))

                with open(join(excludedir,'README'), mode = 'w+') as file:
                    file.write('Restore full stack by moving these files back and running command excludeviews -restore') #noqa: E501


        # Align Stack
        # If previous is passed and imod alignment file .xf is found, use imod.
        # Otherwise, use AreTomo.

        if previous and not aretomo and path.isfile(tiltseries.path.with_suffix('.xf')):
            tiltseries_ali = align_with_imod(tiltseries, previous, do_evn_odd)
        else:
            tiltseries_ali = align_with_areTomo(
                tiltseries, local, previous, do_evn_odd, gpu, volz=ali_d
            )

        # Do dose filtration.
        tiltseries_dosefiltered = dose_filter(tiltseries_ali, do_evn_odd)

        # Get AngPix
        pix_xy = tiltseries.angpix

        # Define x_axis_tilt and thickness
        x_axis_tilt: float = 0
        z_shift: float = 0
        if thickness is None:
            thickness: int = round(6000 / pix_xy) + extra_thickness

        if not skip_positioning:
            print(f"Trying to run automatic positioning on {tiltseries.path.name}.")
            # Perform reconstruction at bin 8 to find pitch / thickness
            tomo_pitch = Tomogram.from_tiltseries(tiltseries_dosefiltered,
                                                  bin=8,
                                                  do_EVN_ODD=False,
                                                  trim=False,
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

            # If it fails, just use default values
            if fs.returncode != 0:
                print(
                    f'{tiltseries.path}: findsection failed, using default values.')
            else:
                # Else, get tomopitch
                tomopitch = subprocess.run([
                    'tomopitch',
                    '-mod', pitch_mod,
                    '-extra', str(extra_thickness),
                    '-scale', str(8)],
                    capture_output=True,
                    text=True).stdout.splitlines()

                # Check for failed process again.
                if any(line.startswith('ERROR') for line in tomopitch):
                    print(
                        f'{tiltseries.path}: tomopitch failed, using default values.')
                else:
                    x_axis_tilt = float(tomopitch[-3].split()[-1])
                    z_shift_line, thickness_line = tomopitch[-1].split(';')
                    z_shift = z_shift_line.split()[-1]
                    thickness = int(thickness_line.split()[-1]) + extra_thickness
                    print(
                        f'{tiltseries.path}: Succesfully estimated tomopitch: thickness {thickness}, z_shift {z_shift}, x_axis_tilt {x_axis_tilt}') #noqa: E501
            pitch_mod.unlink(missing_ok=True)
            tomo_pitch.path.unlink(missing_ok=True)

        # Perform final reconstruction
        Tomogram.from_tiltseries(tiltseries_dosefiltered,
                                 bin=bin,
                                 thickness=thickness,
                                 x_axis_tilt=x_axis_tilt,
                                 z_shift=z_shift,
                                 sirt=sirt,
                                 do_EVN_ODD=do_evn_odd,
                                 convert_to_byte=bytes)

        tiltseries_ali.delete_files(delete_mdoc=False)

        tiltseries_dosefiltered.delete_files(delete_mdoc=False)
        print("\n")
