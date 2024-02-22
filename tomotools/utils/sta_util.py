import math
import os
import shutil
import subprocess
from glob import glob
from os import path
from pathlib import Path

import mrcfile

from tomotools.utils import mdocfile, tomogram
from tomotools.utils.tiltseries import (
    TiltSeries,
    align_with_imod,
    aretomo_executable,
    convert_input_to_TiltSeries,
    parse_ctfplotter,
    parse_darkimgs,
    run_ctfplotter,
    write_ctfplotter,
)


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


def tomotwin_prep(tomotwin_dir, ts_list, thickness, uid, bin_up=True):
    """Prepare list of TS for TomoTwin."""
    tomotwin_dir = Path(tomotwin_dir)
    tomo_dir = tomotwin_dir / "tomo"

    if not path.isdir(tomotwin_dir):
        os.mkdir(tomotwin_dir)

    if not path.isdir(tomo_dir):
        os.mkdir(tomo_dir)

    for ts in ts_list:
        # bin to about 10 Apix, prefer round binning to avoid artifacts
        if bin_up is True:
            binning = math.ceil(10 / ts.angpix / 2) * 2
        else:
            binning = math.floor(10 / ts.angpix / 2) * 2

        ts_ali = align_with_imod(ts, True, False, binning=binning)

        rec = tomogram.Tomogram.from_tiltseries(ts_ali, bin=1, sirt=0,
                                                thickness=round(thickness/binning),
                                                convert_to_byte=False)

        unique_name = f'{uid}_{ts.path.parent.absolute().name}.mrc'

        os.symlink(rec.path.absolute(), tomo_dir / unique_name)
