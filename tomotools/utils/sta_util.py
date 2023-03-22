import os
import shutil
import subprocess
import mrcfile

from os import path
from glob import glob
from pathlib import Path
from tomotools.utils import mdocfile
from tomotools.utils.tiltseries import TiltSeries, aretomo_executable, parse_darkimgs

def aretomo_export(ts: TiltSeries):
    mdoc = mdocfile.read(ts.mdoc)
    
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
    mdoc_cleaned['sections'] = [ele for idx, ele in enumerate(mdoc['sections']) if idx not in exclude]
    mdocfile.write(mdoc_cleaned, ali_stack_imod.mdoc)    
    
    return ali_stack_imod

def make_warp_dir(ts: TiltSeries, project_dir):
    
    required_files = [ts.path,
                      ts.mdoc,
                      ts.path.with_suffix(".xf")]
    
    # Check that all files are present
    if all([path.isfile(req) for req in required_files]) and any([path.isfile(ts.path.with_suffix(".rawtlt")),path.isfile(ts.path.with_suffix(".tlt"))]):
        print("All required alignment files found.")
        
    else:
        raise FileNotFoundError(f"Not all alignment files found for {ts.path.name}.")
        
    # Create imod subdirectory and copy alignment files (to protect against later modification)
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
    
    subframelist = glob(path.join(project_dir,(ts.path.stem+"_sec_*.mrc")))
    
    # Check that mdoc has as many sections as there are tilt images
    if not len(mdoc['sections']) == len(subframelist):
        raise FileNotFoundError(f"There are {len(mdoc['sections'])} mdoc entries but {len(subframelist)} exported frames.")

    for i in range(0,len(mdoc['sections'])):
        mdoc['sections'][i]['SubFramePath'] = 'X:\\WarpDir\\' + Path(subframelist[i]).name

    mdoc = mdocfile.downgrade_DateTime(mdoc)
    
    mdocfile.write(mdoc, path.join(project_dir,"mdoc",ts.path.stem+".mdoc"))

def make_relion_dir():
    pass