import os
import shutil
import subprocess
from glob import glob
from os import path
from pathlib import Path
from typing import Optional

import mrcfile
import pandas as pd

from tomotools.utils import comfile, mdocfile
from tomotools.utils.tiltseries import (
    TiltSeries,
    aretomo_executable,
    parse_ctfplotter,
    parse_darkimgs,
    run_ctfplotter,
    write_ctfplotter,
)


def aretomo_export(ts: TiltSeries):
    """Export AreTomo alignments to xf using -OutImod 2."""
    mdoc = mdocfile.read(ts.mdoc)

    angpix = mdoc['PixelSpacing']

    aln_file = ts.path.with_suffix('.aln')
    tlt_file = ts.path.with_suffix('.tlt')
    ali_stack = ts.path.with_name(f'{ts.path.stem}_ali.mrc')
    imod_dir = path.join(ts.path.parent, (ali_stack.stem + "_Imod"))

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
                    '-OutImod','2'],
                   stdout=subprocess.DEVNULL)

    ali_stack_imod = TiltSeries(Path(path.join(imod_dir, (ali_stack.stem + ".st"))))

    with mrcfile.mmap(ali_stack, mode='r+') as mrc:
        mrc.voxel_size = str(angpix)
        mrc.update_header_stats()

    with mrcfile.mmap(ali_stack_imod.path, mode='r+') as mrc:
        mrc.voxel_size = str(angpix)
        mrc.update_header_stats()

    # Get view exclusion list and create appropriate mdoc
    exclude = parse_darkimgs(ts)

    mdoc_cleaned = mdoc
    mdoc_cleaned['sections'] = [ele for idx, ele in enumerate(mdoc['sections'])
                                if idx not in exclude]
    mdocfile.write(mdoc_cleaned, ali_stack_imod.mdoc)

    return ali_stack_imod


def make_warp_dir(ts: TiltSeries, project_dir):
    """Export tiltseries to Warp."""
    required_files = [ts.path,
                      ts.mdoc,
                      ts.path.with_suffix(".xf")]

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

    [shutil.copy(file,ts_dir) for file in required_files[2:6]]

    # tilt images go to warp root directory
    subprocess.run(['newstack','-quiet',
                   '-split','0',
                   '-append','mrc',
                   '-in',ts.path,
                   path.join(project_dir,(ts.path.stem+"_sec_"))])

    # Create mdoc with SubFramePath and save it to the mdoc subdirectory
    mdoc = mdocfile.read(ts.mdoc)

    tiltlist = glob(path.join(project_dir,(ts.path.stem+"_sec_*.mrc")))

    # Check that mdoc has as many sections as there are tilt images
    if not len(mdoc['sections']) == len(tiltlist):
        raise FileNotFoundError(
            "The number of mdoc sections does not match the number of exported frames."
            )

    for i in range(0,len(mdoc['sections'])):
        mdoc['sections'][i]['SubFramePath'] = 'X:\\WarpDir\\' + Path(tiltlist[i]).name

    mdoc = mdocfile.downgrade_DateTime(mdoc)

    mdocfile.write(mdoc, path.join(project_dir,"mdoc",ts.path.stem+".mdoc"))


def make_relion_dir(ts: TiltSeries,
                    tomo_folder,
                    override_thickness: Optional[int]=None):
    """Generate tomogram folder for Relion 4."""
    # TODO: Check whether alignment is directly from imod or from AreTomo
    exclude = parse_darkimgs(ts)

    ali_stack_imod = path.join(ts.path.parent,
                               (ts.path.stem + "_ali_Imod"),
                               (ts.path.stem + "_ali.st"))

    # If required run ctfplotter or just return results of previous run.
    # Perform on original TiltSeries to avoid interpolation artefacts.
    ctffile = parse_ctfplotter(run_ctfplotter(ts, False))
    ctffile_cleaned = ctffile[~ctffile.view_start.isin([str(ele) for ele in exclude])]

    mdoc = mdocfile.read(Path(ali_stack_imod + ".mdoc"))

    # Relion4 requires a line for each tilt in the ctfplotter file.
    # If overlapping spectra were fit, duplicate the lines here
    # TODO: move to separate function!
    if len(mdoc['sections']) != len(ctffile_cleaned):

        # Figure out which tilts are missing
        for section in mdoc['sections']:
            tilt = round(section['TiltAngle'])

            if tilt not in [int(ele) for ele in
                            pd.to_numeric(ctffile_cleaned['tilt_start']).to_list()]:

                df_subset = ctffile_cleaned.loc[((pd.to_numeric(ctffile_cleaned['tilt_start']) #noqa: E501
                                                  < tilt) &
                                                 (pd.to_numeric(ctffile_cleaned['tilt_end'])
                                                  > tilt)
                                                 )]

                df_temp = pd.DataFrame({'view_start': pd.to_numeric(df_subset['view_start'])+1,  #noqa: E501
                                        'view_end': df_subset.view_end,
                                        'tilt_start': tilt,
                                        'tilt_end': tilt,
                                        'df_1_nm': df_subset.df_1_nm,
                                        'df_2_nm': df_subset.df_2_nm,
                                        'astig_ang': df_subset.astig_ang})

                ctffile_cleaned = pd.concat([ctffile_cleaned, df_temp])

    ctf_out = write_ctfplotter(ctffile_cleaned,
                               Path(Path(ali_stack_imod).parent/(f'{Path(ali_stack_imod).stem}.defocus')))

    # Create or symlink all relevant files:
    # pre-alignment stack, post-alignment stack,
    # tlt, xf, tilt.com, newst.com, ctfplotter
    os.symlink(Path(ali_stack_imod).parent.absolute(),
               tomo_folder,
               target_is_directory=True)

    df_temp = pd.DataFrame(data={'rlnTomoName': ts.path.stem,
                                 'rlnTomoImportImodDir': tomo_folder,
                                 'rlnTomoTiltSeriesName': f'{path.join(tomo_folder,Path(ali_stack_imod).name)}:mrc',  #noqa: E501
                                 'rlnTomoImportOrderList': mdocfile.convert_to_order_list(mdoc, tomo_folder),  #noqa: E501
                                 'rlnTomoImportCtfPlotterFile': ctf_out,
                                 'rlnTomoImportFractionalDose': mdoc['sections'][0]['ExposureDose'],  #noqa: E501
                                 'rlnOpticsGroupName': mdoc['sections'][0]['DateTime'].split()[0]},  #noqa: E501
                           dtype=str, index=[0])

    # Write override_thickness to tilt.com
    if override_thickness is not None:
        comfile.modify_value(path.join(tomo_folder,"tilt.com"),
                             "THICKNESS",override_thickness)

    return df_temp
