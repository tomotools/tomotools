import os
import shutil
import subprocess
import warnings
from pathlib import Path
from typing import Optional, List
from operator import itemgetter

import mrcfile

from tomotools.utils import util, mdocfile
from tomotools.utils.micrograph import Micrograph


class TiltSeries:
    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f'File not found: {path}')
        self.path: Path = path
        self.is_split: bool = False
        self.evn_path: Optional[Path] = None
        self.odd_path: Optional[Path] = None

    def with_split_files(self, evn_file: Path, odd_file: Path) -> 'TiltSeries':
        if not evn_file.is_file():
            raise FileNotFoundError(f'File not found: {evn_file}')
        if not odd_file.is_file():
            raise FileNotFoundError(f'File not found: {odd_file}')
        self.evn_path = evn_file
        self.odd_path = odd_file
        self.is_split = True
        return self

    def with_split_dir(self, dir: Path) -> 'TiltSeries':
        if not dir.is_dir():
            raise NotADirectoryError(f'{dir} is not a directory!')
        stem = self.path.stem
        suffix = self.path.suffix
        evn_file = dir.joinpath(f'{stem}_EVN{suffix}')
        odd_file = dir.joinpath(f'{stem}_ODD{suffix}')
        return self.with_split_files(evn_file, odd_file)

    # TODO: parse ctffind or ctfplotter files
    def get_defocus(self, output_file: Optional[Path] = None):
        pass

    @staticmethod
    # TODO: run ctffind
    def find_defocus(self):
        pass

    @staticmethod
    def _update_mrc_header_from_mdoc(path: Path, mdoc: dict):
        with mrcfile.mmap(path, 'r+') as mrc:
            # Copy the first 10 titles into the newly created mrc
            mrc.update_header_from_data()
            mrc.update_header_stats()
            for i in range(10):
                title = mdoc['titles'][i].encode() if i < len(mdoc['titles']) else b''
                mrc.header['label'][i] = title
            mrc.header['nlabl'] = len(mdoc['titles'])
            mrc.voxel_size = mdoc['sections'][0]['PixelSpacing']

    @staticmethod
    def _update_mdoc_from_mrc_header(path: Path, mdoc: dict):
        with mrcfile.mmap(path, 'r+') as mrc:
            # Copy over some global information from the first section into the mdoc
            mdoc['PixelSpacing'] = mdoc['sections'][0]['PixelSpacing']
            mdoc['ImageFile'] = path.name
            mdoc['ImageSize'] = [mrc.header['nx'].item(), mrc.header['ny'].item()]
            mdoc['DataMode'] = mrc.header['mode'].item()

    @staticmethod
    def from_micrographs(micrographs: List[Micrograph], ts_path: Path, orig_mdoc_path: Optional[Path] = None,
                         reorder=False, overwrite_titles: Optional[List[str]] = None) -> 'TiltSeries':
        # TODO: Possibly remove overwrite_titles
        if ts_path.exists():
            raise FileExistsError(f'File at {ts_path} already exists!')
        if reorder:
            micrographs = sorted(micrographs, key=lambda micrograph: micrograph.tilt_angle)

        # First, take care of the MDOC files
        if all(micrograph.mdoc for micrograph in micrographs):
            # If all movies have their own associated mdoc, merge the mdoc files (except titles, see below)
            stack_mdoc = {'titles': list(), 'sections': list(), 'framesets': list()}
            for micrograph in micrographs:
                mdoc = micrograph.mdoc
                stack_mdoc['titles'] = mdoc['titles']
                stack_mdoc['sections'].append(mdoc['framesets'][0])
                # Copy global vars (overwrite existing, so again only the last values are kept)
                for key, value in mdoc.items():
                    if key not in ('framesets', 'titles', 'sections'):
                        stack_mdoc[key] = value

            # Merging the titles is too difficult, I'll just keep the title of the last frame
            if overwrite_titles is not None:
                # Update titles and append frameset as new section
                stack_mdoc['titles'] = overwrite_titles

        elif orig_mdoc_path is not None:
            stack_mdoc = mdocfile.read(orig_mdoc_path)
            if reorder:
                stack_mdoc['sections'] = sorted(stack_mdoc['sections'], key=itemgetter('TiltAngle'))

        else:
            raise FileNotFoundError('No original MDOC was provided and the movies don\'t have MDOCs, aborting!')

        # Now, create the TiltSeries files
        micrograph_paths = [str(micrograph.path) for micrograph in micrographs]
        subprocess.run(['newstack'] + micrograph_paths + [ts_path, '-quiet'])

        # Remove MRC header and MDOC, remove unnecessary entries
        TiltSeries._update_mrc_header_from_mdoc(ts_path, stack_mdoc)
        TiltSeries._update_mdoc_from_mrc_header(ts_path, stack_mdoc)
        for section in stack_mdoc['sections']:
            for key in ('SubFramePath', 'NumSubFrames', 'FrameDosesAndNumber'):
                if key in section:
                    del section[key]
        mdocfile.write(stack_mdoc, str(ts_path) + '.mdoc')

        if all(micrograph.is_split for micrograph in micrographs):
            micrograph_evn_paths = [str(micrograph.evn_path) for micrograph in micrographs]
            micrograph_odd_paths = [str(micrograph.odd_path) for micrograph in micrographs]
            ts_evn = ts_path.with_stem(ts_path.stem + '_EVN')
            ts_odd = ts_path.with_stem(ts_path.stem + '_ODD')
            subprocess.run(['newstack'] + micrograph_evn_paths + [ts_evn, '-quiet'])
            subprocess.run(['newstack'] + micrograph_odd_paths + [ts_odd, '-quiet'])
            TiltSeries._update_mrc_header_from_mdoc(ts_evn, stack_mdoc)
            TiltSeries._update_mrc_header_from_mdoc(ts_odd, stack_mdoc)
            return TiltSeries(ts_path).with_split_files(ts_evn, ts_odd)
        else:
            return TiltSeries(ts_path)


def aretomo_executable() -> Optional[Path]:
    '''The AreTomo executable can be set with one of the following ways (in order of priority):
    1. Setting the ARETOMO_EXECUTABLE variable to the full path of the executable file
    2. Putting the appropriate executable into the PATH and renaming it to "aretomo"'''
    if 'ARETOMO_EXECUTABLE' in os.environ:
        aretomo_exe = Path(os.environ['ARETOMO_EXECUTABLE'])
        if aretomo_exe.is_file():
            return aretomo_exe
        else:
            warnings.warn(
                f'ARETOMO_EXECUTABLE is set to "{aretomo_exe}", but the file does not exist. Falling back to PATH')
    return shutil.which('AreTomo')

def align_with_areTomo(ts: TiltSeries, local: bool, previous: Optional):
    ''' Takes a TiltSeries as input and runs AreTomo on it, if desired with local alignment. A previously generated .aln file can be passed optionally.'''
    # TODO: make sure reconstruct handles exclusion of tilts and moving to subfolders if desired

    ali_stack = ts.path.with_name(f'{ts.path.stem}_ali.mrc')

    if previous is None:
        tlt_file = ts.path.with_suffix('.tlt')
        aln_file = ts.path.with_suffix('.aln')

        subprocess.run(['extracttilts', ts.path, tlt_file],
                       stdout=subprocess.DEVNULL)

        num_gpus = int(util.gpuinfo()['Attached GPUs'])

        mdoc = mdocfile.read(f'{ts.path}.mdoc')
        full_dimensions = mdoc['ImageSize']
        patch_x, patch_y = [str(round(full_dimensions[0]/1000)), str(round(full_dimensions[1]/1000))]

        subprocess.run([aretomo_executable(),
                        '-InMrc', ts.path,
                        '-OutMrc', ali_stack,
                        '-AngFile', tlt_file,
                        '-VolZ', '0',
                        '-TiltCor', '1'] +
                        (['-Gpu', [str(i) for i in range(num_gpus)]] if num_gpus > 0 else []) +
                        (['-Patch', patch_x, patch_y] if local else []),
                        stdout=subprocess.DEVNULL)

    else:
        subprocess.run([aretomo_executable(),
                        '-InMrc', ts.path,
                        '-OutMrc', ali_stack,
                        '-AlnFile', previous,
                        '-VolZ', '0'],
                        stdout=subprocess.DEVNULL)

    print(f'Done aligning {ts.path.stem} with AreTomo.')

    if ts.evn_path is not None and ts.odd_path is not None:
        ali_stack_evn = ts.evn_path.with_name(f'{ts.evn_path.stem}_ali.mrc')
        ali_stack_odd = ts.odd_path.with_name(f'{ts.odd_path.stem}_ali.mrc')
        subprocess.run([aretomo_excecutable(),
                        '-InMrc', ts.evn_path,
                        '-OutMrc', ali_stack_evn,
                        '-AlnFile', aln_file,
                        '-VolZ', '0'])

        subprocess.run([aretomo_excecutable(),
                        '-InMrc', ts.odd_path,
                        '-OutMrc', ali_stack_odd,
                        '-AlnFile', aln_file,
                        '-VolZ', '0'])

        print(f'Done aligning ENV and ODD stacks for {ts.path.stem} with AreTomo.')

def align_with_imod(ts: TiltSeries, excludetilts: Optional[Path]):
    # implement batch alignment with imod adoc here!
    pass