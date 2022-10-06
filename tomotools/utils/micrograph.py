import os
import shutil
import subprocess
import warnings
from glob import glob
from os.path import join, isfile
from pathlib import Path
from typing import Optional, List

from tomotools.utils import util, mdocfile
from tomotools.utils.movie import Movie


class Micrograph:
    def __init__(self, path: Path, tilt_angle: float = 0.0):
        if not path.is_file():
            raise FileNotFoundError(f'File not found: {path}')
        self.path: Path = path
        self.mdoc_path: Path = Path(str(path) + '.mdoc')
        self.mdoc = mdocfile.read(self.mdoc_path) if self.mdoc_path.is_file() else None
        self.tilt_angle: float = tilt_angle
        self.is_split: bool = False
        self.evn_path: Optional[Path] = None
        self.odd_path: Optional[Path] = None

    def with_split_files(self, evn_file: Path, odd_file: Path) -> 'Micrograph':
        if not evn_file.is_file():
            raise FileNotFoundError(f'File not found: {evn_file}')
        if not odd_file.is_file():
            raise FileNotFoundError(f'File not found: {odd_file}')
        self.evn_path = evn_file
        self.odd_path = odd_file
        self.is_split = True
        return self

    def with_split_dir(self, dir: Path) -> 'Micrograph':
        if not dir.is_dir():
            raise NotADirectoryError(f'{dir} is not a directory!')
        stem = self.path.stem
        suffix = self.path.suffix
        evn_file = dir.joinpath(f'{stem}_EVN{suffix}')
        odd_file = dir.joinpath(f'{stem}_ODD{suffix}')
        return self.with_split_files(evn_file, odd_file)

    @staticmethod
    def from_movies(movies: List[Movie], output_dir: Path,
                    splitsum: bool = False, binning: int = 2,
                    group: int = 1, patch_x: int = 5, patch_y: int = 7, 
                    mcrot: Optional[int] = None, mcflip: Optional[int] = None,
                    override_gainref: Optional[Path] = None,
                    gpus: Optional[str] = None) -> 'List[Micrograph]':
        tempdir = output_dir.joinpath('motioncor2_temp')
        tempdir.mkdir(parents=True)
        gain_ref_dm4 = None
        gain_ref_mrc = None
        mc2_exe = motioncor2_executable()
        if mc2_exe is None:
            raise FileNotFoundError('The MotionCor2 executable could not be found. '
                                    'Either specify it by setting MOTIONCOR2_EXECUTABLE '
                                    'or put it into the PATH and rename it to "motioncor2"')

        # If override_gainref is given, check if it is already mrc or needs to be converted.
        if override_gainref is not None:
            override_gainref = Path(override_gainref)
            if override_gainref.suffix == '.dm4':
                gain_ref_dm4 = override_gainref
            elif override_gainref.suffix == '.mrc':
                gain_ref_mrc = override_gainref
            else:
                raise AttributeError('Gain reference can only be in .dm4 or .mrc format!')
        elif movies[0].mdoc is not None:
            # Check if there is a subframe mdoc and if so, if there is a unique gain reference
            gain_refs = set([movie.mdoc['framesets'][0].get('GainReference', None) for movie in movies])
            if len(gain_refs) != 1:
                raise Exception(
                    f'Only zero or one unique gain refs are supported, yet {len(gain_refs)} were found in the MDOC files:\n{", ".join(gain_refs)}')
            # The gain ref should be in the same folder as the input file(s), so check if it's there
            gain_ref_dm4 = movies[0].path.parent.joinpath(gain_refs.pop())

        if gain_ref_dm4 is not None and gain_ref_mrc is None:
            if not gain_ref_dm4.is_file():
                raise FileNotFoundError(f'Expected gain reference at {gain_ref_dm4}, aborting')
            # The gain ref is saved in dm4 format, convert to MRC for MotionCor2
            # Write to a separate directory to prevent MotionCor2 from trying to open it.
            temp_gain = output_dir.joinpath('motioncor2_gain')
            temp_gain.mkdir()
            gain_ref_mrc = temp_gain.joinpath(gain_ref_dm4.stem + '.mrc')
            print(f'Found unique gain reference {gain_ref_dm4}, converting to MRC at {gain_ref_mrc}')
            subprocess.run(['dm2mrc', gain_ref_dm4, gain_ref_mrc])

        if gain_ref_mrc is not None:
            if not gain_ref_mrc.is_file():
                raise FileNotFoundError(
                    f"The GainRef file {gain_ref_mrc} doesn't exist, something must have gone wrong!")
            print(f'Using gainref file {gain_ref_mrc}')
        else:
            print(
                'No gain reference is specified in the MDOC files or given as an argument, continuing without gain correction')

        # Link the input files to the working dir
        # so that files that should not be motioncor'ed are not
        for movie in movies:
            tempdir.joinpath(movie.path.name).symlink_to(movie.path.absolute())

        # TODO: here, -Bft should probably be zero to prevent high-pass filtering from later frames -> will be done during reconstruction?
        command = [mc2_exe,
                   '-OutMrc', str(output_dir.absolute()) + os.path.sep,
                   '-Patch', str(patch_x), str(patch_y),
                   '-Iter', '10',
                   '-Tol', '0.5',
                   '-FtBin', str(binning),
                   '-Group', str(group),
                   '-Serial', '1']
        if movies[0].is_mrc:
            command += ['-InMrc', str(tempdir.absolute()) + '/']
        elif movies[0].is_tiff:
            command += ['-InTiff', str(tempdir.absolute()) + '/']
        if gpus is None:
            num_gpus = int(util.gpuinfo()['Attached GPUs'])
            command += ['-Gpu'] + [str(i) for i in range(num_gpus)] if num_gpus > 0 else []
        else:
            command += ['-Gpu', gpus]
        if splitsum:
            command += ['-SplitSum', '1']
        
        if gain_ref_mrc is not None:
            command += ['-Gain', gain_ref_mrc.absolute()]
            
        if mcrot is not None and mcflip is not None:
            command += ['-RotGain', str(mcrot),
                        '-FlipGain', str(mcflip)]

        if gain_ref_dm4 is not None and check_defects(gain_ref_dm4) is not None:
            command += ['-DefectMap', defects_tif(gain_ref_dm4, tempdir, movies[0].path).absolute()]

        with open(join(output_dir, 'motioncor2.log'), 'a') as out, open(join(output_dir, 'motioncor2.err'), 'a') as err:
            subprocess.run(command, cwd=tempdir, stdout=out, stderr=err)

        # If present, copy the mdoc files to the output dir, rename from .tif.mdoc to .mrc.mdoc
        # they are read and then written and not just copied so that the GainReference field can be removed
        # and the pixel spacing can be adjusted
        for movie in movies:
            if movie.mdoc is not None:
                # Sanity check: there should be only one frameset
                if not (isinstance(movie.mdoc['framesets'], list) and len(movie.mdoc['framesets']) == 1):
                    raise Exception('Unexpected MDOC format: tomotools can only handle a single frameset per mdoc')
                # Adjust pixel size and binning
                movie.mdoc['framesets'][0]['PixelSpacing'] *= binning
                movie.mdoc['framesets'][0]['Binning'] *= binning
                # Delete GainReference entry
                if 'GainReference' in movie.mdoc['framesets'][0]:
                    del movie.mdoc['framesets'][0]['GainReference']
                mdocfile.write(movie.mdoc,
                               output_dir.joinpath(Path(movie.mdoc_path.stem).stem + '.mrc.mdoc'))
        shutil.rmtree(tempdir)

        print('Checking MotionCor2 output files')
        
        if gain_ref_mrc is not None:
            with open(join(output_dir, 'motioncor2.log'), 'r') as log:
                if any(l.startswith('Warning: Gain ref not found.') for l in log):
                    raise Exception('Gain reference was specified, but not applied by MotionCor2. Check log file!')
            shutil.rmtree(temp_gain)
        
        output_micrographs = [
            Micrograph(path=output_dir.joinpath(movie.path.with_suffix('.mrc').name), tilt_angle=movie.tilt_angle)
            for movie in movies]
        if splitsum:
            output_micrographs = [mic.with_split_dir(output_dir) for mic in output_micrographs]
        return output_micrographs


def sem2mc2(RotationAndFlip: int = 0):
    ''' Converts SerialEM property RotationAndFlip into MotionCor2-compatibly -RotGain / -FlipGain values.
    Using List on https://bio3d.colorado.edu/SerialEM/hlp/html/setting_up_serialem.htm#cameraOrientation as Reference,
    For MotionCor2: Rotation = n*90deg, Flip 1 = flip around X, Flip 2 = flip around Y
    Returns a List with first item as rotation and second item as flip.'''
    conv = {0: [0, 0], 1: [3, 0], 2: [2, 0], 3: [1, 0], 4: [0, 2], 5: [1, 2], 6: [2, 2], 7: [3, 2]}
    return conv[RotationAndFlip]


def check_defects(gainref: Path):
    ''' Checks for a SerialEM-created defects file and -if found- returns file name. '''
    defects_temp = list()
    defects_temp.extend(glob(str(gainref.parent.joinpath('defects*.txt'))))

    if len(defects_temp) == 1:
        return defects_temp[0]
    elif len(defects_temp) > 1:
        print('Multiple defect files are found. Skipping defect correction.')
        return None
    else:
        return None


def defects_tif(gainref: Path, tempdir: Path, template: Path):
    ''' Creates a -DefectsMap input for MotionCor2 from SerialEM defects txt in the passed temporary directory.
    Requires a template file with the dimensions of the frames to be corrected. '''
    defects_txt = Path(check_defects(gainref))
    defects_tif = defects_txt.with_suffix(".tif")
    if isfile(defects_tif):
        return defects_tif
        print(f'Found defects file {str(defects_tif)}')
    else:
        subprocess.run(['clip', 'defect', '-D', defects_txt, template, defects_tif])
        print(f'Found defects file and converted to {str(defects_tif)}')
        return defects_tif


def motioncor2_executable() -> Optional[Path]:
    '''The MotionCor executable can be set with one of the following ways (in order of priority):
    1. Setting the MOTIONCOR2_EXECUTABLE variable to the full path of the executable file
    2. Putting the appropriate executable into the PATH and renaming it to "motioncor2"'''
    if 'MOTIONCOR2_EXECUTABLE' in os.environ:
        mc2_exe = Path(os.environ['MOTIONCOR2_EXECUTABLE'])
        if mc2_exe.is_file():
            return mc2_exe
        else:
            warnings.warn(
                f'MOTIONCOR2_EXECUTABLE is set to "{mc2_exe}", but the file does not exist. Falling back to PATH')
    return shutil.which('motioncor2')
