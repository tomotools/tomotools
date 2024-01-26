import os
import shutil
import subprocess
from glob import glob
from os import path
from pathlib import Path

import mrcfile
import pandas as pd
import starfile

from tomotools.utils import comfile, mdocfile, tiltseries
from tomotools.utils.tiltseries import (
    TiltSeries,
    aretomo_executable,
    convert_input_to_TiltSeries,
    parse_ctfplotter,
    parse_darkimgs,
    run_ctfplotter,
    write_ctfplotter,
)
from tomotools.utils.tomogram import Tomogram


def aretomo_export(ts: TiltSeries):
    """Export AreTomo alignments to xf using -OutImod 2."""
    mdoc = mdocfile.read(ts.mdoc)

    angpix = ts.angpix

    with mrcfile.mmap(ts.path) as mrc:
        labels = mrc.get_labels()

    aln_file = ts.path.with_suffix('.aln')
    tlt_file = ts.path.with_suffix('.tlt')
    ali_stack = ts.path.with_name(f'{ts.path.stem}_ali.mrc')

    imod_dir = path.join(ts.path.parent, (ali_stack.stem + "_Imod"))

    if path.isdir(imod_dir) and path.isfile(path.join(imod_dir,
                                                      (ali_stack.stem + ".st"))):
        print(f'Previous AreTomo export found for {ts.path.name}. Re-using.')

        ali_stack_imod = TiltSeries(
            Path(path.join(imod_dir, (ali_stack.stem + ".st"))))

        with mrcfile.mmap(ali_stack_imod.path, mode='r+') as mrc:
                mrc.voxel_size = str(angpix)

                # Check whether labels were already added
                if len(mrc.get_labels()) == 0:
                    for label in labels:
                        mrc.add_label(label)
                mrc.update_header_stats()

        return ali_stack_imod

    if not path.isfile(aln_file):
        raise FileNotFoundError(
            f'{ts.path}: No previous alignment was found at {aln_file}.')

    subprocess.run([aretomo_executable(),
                    '-InMrc', ts.path,
                    '-OutMrc', ali_stack,
                    '-AngFile', tlt_file,
                    '-AlnFile', aln_file,
                    '-TiltCor', '0',
                    '-VolZ', '0',
                    '-OutImod', '2'],
                   stdout=subprocess.DEVNULL)

    ali_stack_imod = TiltSeries(
        Path(path.join(imod_dir, (ali_stack.stem + ".st"))))

    with mrcfile.mmap(ali_stack, mode='r+') as mrc:
        mrc.voxel_size = str(angpix)
        mrc.update_header_stats()

    with mrcfile.mmap(ali_stack_imod.path, mode='r+') as mrc:
        mrc.voxel_size = str(angpix)
        for label in labels:
            mrc.add_label(label)
        mrc.update_header_stats()

    # Get view exclusion list and create appropriate mdoc
    exclude = parse_darkimgs(ts)

    mdoc_cleaned = mdoc

    mdoc_cleaned['sections'] = [ele for idx, ele in enumerate(mdoc['sections'])
                                if idx not in exclude]

    mdocfile.write(mdoc_cleaned, ali_stack_imod.mdoc)

    return ali_stack_imod


def make_warp_dir(ts: TiltSeries, project_dir: Path, imod: bool = False):
    """Export tiltseries to Warp."""
    required_files = [ts.path,
                      ts.mdoc,
                      ts.path.with_suffix(".xf")]

    if imod:
        required_files.append(ts.path.parent/"taSolution.log")

    # Check that all files are present
    if (all(path.isfile(req) for req in required_files) and
        any([path.isfile(ts.path.with_suffix(".rawtlt")),
             path.isfile(ts.path.with_suffix(".tlt"))])
        ):
        print("All required alignment files found.")

    else:
        raise FileNotFoundError(f"Not all alignment files found for {ts.path.name}.")

    # Create imod subdirectory
    # copy alignment files (to protect against later modification)
    ts_dir = path.join(project_dir,"imod",ts.path.stem)
    os.mkdir(ts_dir)

    [shutil.copy(file,ts_dir) for file in required_files[2:]]

    # tilt images go to warp root directory
    subprocess.run(['newstack','-quiet',
                   '-split','0',
                   '-append','mrc',
                   '-in',ts.path,
                   path.join(project_dir,(ts.path.stem+"_sec_"))])

    # Create mdoc with SubFramePath and save it to the mdoc subdirectory
    mdoc = mdocfile.read(ts.mdoc)

    subframelist = glob(path.join(project_dir, (ts.path.stem+"_sec_*.mrc")))

    # Check that mdoc has as many sections as there are tilt images
    if not len(mdoc['sections']) == len(subframelist):
        raise FileNotFoundError(
            "Error: Mismatch between mdoc entries and frames!")

    for i in range(0, len(mdoc['sections'])):
        mdoc['sections'][i]['SubFramePath'] = 'X:\\WarpDir\\' + \
            Path(subframelist[i]).name

    mdoc = mdocfile.downgrade_DateTime(mdoc)

    mdocfile.write(mdoc, path.join(project_dir, "mdoc", ts.path.stem+".mdoc"))

    return


def batch_parser(input_files: [], batch: bool):
    """Batch-parse tiltseries to work on from textfile."""
    input_files_parsed = []

    # Check whether you already received a correctly formatted list of TiltSeries
    if isinstance(input_files[0], TiltSeries):
        return input_files

    if isinstance(input_files[0], list):
        return input_files[0]

    # Parse input files
    if batch:
        with open(input_files[0], "r+") as f:
            for line in f:
                input_files_parsed.append(line.strip("\n"))

    else:
        input_files_parsed = input_files

    # Convert to list of tiltseries
    ts_list = convert_input_to_TiltSeries(input_files_parsed)

    return ts_list


def ctfplotter_aretomo_export(ts: TiltSeries):
    """Exclude AreTomo Excludeview from ctfplotter file."""
    exclude = parse_darkimgs(ts)

    # If required run ctfplotter or just return results of previous run.
    # Perform on original TiltSeries to avoid interpolation artefacts.
    ctffile = parse_ctfplotter(run_ctfplotter(ts, False))

    # ctfplotter is 1-indexed, excludeviews are 0-indexed
    ctffile_cleaned = ctffile[~ctffile.view_start.isin(
        [str(ele+1) for ele in exclude])]

    # Write to AreTomo export folder
    ctf_out = write_ctfplotter(ctffile_cleaned,
                               ts.path.parent / f'{ts.path.stem}_ali_Imod' /
                               f'{ts.path.stem}_ali.defocus')

    return ctf_out


def tomo2stopgap(ts: TiltSeries, bin: int, thickness: int):
    """Prepare tomogram for STOPGAP.

    Align, dose-filter, reconstruct with ctf3d.
    Build wedge list.
    """
    # Re-align + bin
    ts_ali = tiltseries.align_with_imod(ts, True, False, binning=bin)

    # Perform dose filtration
    ts_ali_filt = tiltseries.dose_filter(ts_ali, False)
    ts_ali.delete_files(False)

    # Check that ctfplotter is there + create file
    if ts.defocus_file() is None:
        print(f'Defocus file not found for {ts.path.name}. Running ctfplotter now.')
        run_ctfplotter(ts, True)

    comfile.fake_ctfcom(ts_ali_filt, 1)

    # Create wedge list
    # First, build database with global info:
    dim_x, dim_y = tiltseries.binned_size(ts, 1)

    # Then, go over tilts and add: tilt angle, defocus mean (in um), exposure
    tilts = []

    with open(ts.path.with_suffix(".tlt")) as file:
        for line in file:
            if line.startswith('\n'):
                continue
            else:
                tilts.append(float(line.strip()))

    ctf_file = parse_ctfplotter(ts.defocus_file())
    mdoc = mdocfile.insert_prior_dose(mdocfile.read(ts.mdoc))

    # Angpix, XY from header (so other tools can handle the correct rotation)
    # Z as thickness
    # z-shift left at 0
    # pshift left at 0
    # voltage, cs: 300kV, 2.7 mm
    # amplitude contrast 0.07 as in run_ctfplotter

    df_temp_tomo = pd.DataFrame(data={'pixelsize': f"{ts.angpix:.3f}",
                                 'tomo_x': dim_x,
                                 'tomo_y': dim_y,
                                 'tomo_z': thickness,
                                 'z_shift': 0,
                                 'pshift': 0,
                                 'voltage': 300,
                                 'cs': 2.7,
                                 'amp_contrast': 0.07,
                                 'tilt_angle': tilts,
                                 'defocus': 0,
                                 'exposure': 0},dtype = str)

    for i in range(len(tilts)):

        df_temp_tomo.iat[i,10] = f"{(float(ctf_file.iloc[i].df_1_nm) + float(ctf_file.iloc[i].df_2_nm)) / 2000:.2f}" #noqa:E501
        df_temp_tomo.iat[i,11] = "{:.1f}".format(mdoc['sections'][i]['ExposureDose'] + mdoc['sections'][i]['PriorRecordDose']) #noqa:E501

    return ts_ali_filt, df_temp_tomo


def list2stopgap(bin, thickness, ts_list: [], stopgap_dir):
    """Take list of tiltseries, prepare STOPGAP project."""
    # Create target folder
    stopgap_dir = Path(stopgap_dir)
    target_dir = stopgap_dir / f"tomos_bin{bin}"

    # If folder does not exist, initialise
    if not path.isdir(stopgap_dir / f"tomos_bin{bin}"):

        os.mkdir(target_dir)

        wedgelist = pd.DataFrame()

        tomo_num = 1

        subprocess.run(['touch',
                        target_dir / "tomo_dict.txt"])

    else:
        # read previous wedgelist
        wedgelist = starfile.read(target_dir / "wedgelist.star")
        # set tomo index to avoid clashed
        tomo_num = max(wedgelist['tomo_num']) + 1

    # First, check that all required files are there

    rec_todo = {}
    tomo_dict = {}

    print(f'Exporting {len(ts_list)} tomograms to STOPGAP. \n')

    for ts in ts_list:

        print(f'\nWorking on {ts.path.name}, tomo_num {tomo_num}.')

        # Save index assignment for later
        tomo_dict[tomo_num] = str(ts.path.absolute())

        # Get stack for reconstruction and wedge list
        final_stack, wedgelist_temp = tomo2stopgap(ts, bin, thickness)

        rec_todo[tomo_num] = final_stack
        wedgelist_temp['tomo_num'] = tomo_num

        wedgelist = pd.concat([wedgelist, wedgelist_temp])

        tomo_num += 1

    print('\n')
    print('STOPGAP files have been prepared. Now starting reconstruction. \n')

    # Write wedgelist and dictionary to map tomogram identity
    starfile.write({'stopgap_wedgelist': wedgelist},
                   target_dir / "wedgelist.star", overwrite=True)

    with open(target_dir / "tomo_dict.txt", 'a') as file:
        for tomo_num in tomo_dict:
            file.write(f'{tomo_num} {tomo_dict[tomo_num]}\n')

    # Get full dimensions of unbinned stack for reconstruction
    # Right now, assumption is that all tomograms have the same xy dimensions.
    dim_x = wedgelist['tomo_x'].values[0]
    dim_y = wedgelist['tomo_y'].values[0]

    for tomo_num in rec_todo:

        rec = Tomogram.from_tiltseries_3dctf(
            rec_todo[tomo_num], binning=bin, thickness=thickness,
            z_slices_nm=25, fullimage=[dim_x,dim_y])

        os.symlink(rec.path.absolute(), target_dir / f'{tomo_num}.rec')

        print('\n')
