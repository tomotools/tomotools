import os
import subprocess
from os import path
from os.path import splitext, isfile, join, isdir, dirname, basename, abspath
from shutil import rmtree
from typing import Optional, Tuple, List

import mrcfile

from tomotools.utils import mdocfile, util


def assert_subframes_list(subframes: list, is_split):
    if not all(isinstance(subframe, SubFrame) for subframe in subframes):
        raise ValueError('Only a list of SubFrames is supported!')
    for subframe in subframes:
        subframe.assert_files_exist(is_split)


def sanitize_subframes_list(subframes: list):
    if not all(isinstance(subframe, SubFrame) for subframe in subframes):
        raise ValueError('Only a list of SubFrames is supported!')
    sanitized_list = list()
    for subframe in subframes:
        base_name, ext = splitext(basename(subframe.path))
        if not (base_name.endswith('_EVN') or base_name.endswith('_ODD')):
            sanitized_list.append(subframe)
    return sanitized_list


def sort_subframes_list(subframes: list):
    '''Sorts a list of SubFrames by tilt-angle
    Requires that all SubFrames have a corresponding MDOC file'''
    # Check if the list is a list of subframes
    if not all(isinstance(subframe, SubFrame) for subframe in subframes):
        raise ValueError('sort_subframes_list only supports lists of SubFrames')
    return sorted(subframes, key=lambda subframe: subframe.mdoc['framesets'][0]['TiltAngle'])


def frames2stack(subframes: list, stack_path, overwrite_titles=None, skip_evnodd=False):
    # Check if frames and their respective mdoc files exist
    assert_subframes_list(subframes, is_split=False)

    # Merge the mdoc files (except titles, see below)
    stack_mdoc = {'titles': list(), 'sections': list(), 'framesets': list()}
    for subframe in subframes:
        # Update titles and append frameset as new section
        mdoc = subframe.mdoc
        stack_mdoc['titles'] = mdoc['titles']
        stack_mdoc['sections'].append(mdoc['framesets'][0])
        # Copy global vars (overwrite existing, so again only the last values are kept)
        for key, value in mdoc.items():
            if key not in ('framesets', 'titles', 'sections'):
                stack_mdoc[key] = value

    # Merging the titles is too difficult, I'll just keep the title of the last frame
    if overwrite_titles is not None:
        stack_mdoc['titles'] = overwrite_titles

    # Build pair(s) of output stack and list of movie sums
    full_stack_basename, full_stack_ext = splitext(stack_path)
    stack_subframes_pairs = [(stack_path, [subframe.path for subframe in subframes])]
    if not skip_evnodd and all(subframe.is_split for subframe in subframes):
        stack_subframes_pairs += [
            (f'{full_stack_basename}_EVN{full_stack_ext}', [subframe.path_evn for subframe in subframes]),
            (f'{full_stack_basename}_ODD{full_stack_ext}', [subframe.path_odd for subframe in subframes])
        ]

    # Run newstack for the full stack and, if desired, the EVN/ODD halves
    for partial_stack_path, partial_stack_subframes in stack_subframes_pairs:
        subprocess.run(['newstack'] + partial_stack_subframes + [partial_stack_path])
        # Update the header of the stack MRC
        with mrcfile.mmap(partial_stack_path, 'r+') as mrc:
            # Copy the first 10 titles into the newly created mrc
            mrc.update_header_from_data()
            mrc.update_header_stats()
            for i in range(10):
                title = stack_mdoc['titles'][i].encode() if i < len(stack_mdoc['titles']) else b''
                mrc.header['label'][i] = title
            mrc.header['nlabl'] = len(stack_mdoc['titles'])
            mrc.voxel_size = stack_mdoc['sections'][0]['PixelSpacing']
            # Copy over some global information from the first section into the mdoc
            stack_mdoc['PixelSpacing'] = stack_mdoc['sections'][0]['PixelSpacing']
            stack_mdoc['ImageFile'] = basename(partial_stack_path)
            stack_mdoc['ImageSize'] = [mrc.header['nx'].item(), mrc.header['ny'].item()]
            stack_mdoc['DataMode'] = mrc.header['mode'].item()
    mdocfile.write(stack_mdoc, f'{stack_path}.mdoc')
    return stack_path, stack_mdoc


class SubFrame:
    @property
    def mdoc_path(self):
        return f'{self.path}.mdoc'

    @property
    def mdoc(self):
        if self._mdoc is None:
            self._mdoc = mdocfile.read(self.mdoc_path)
        return self._mdoc

    @property
    def path_evn(self):
        base, ext = splitext(self.path)
        return f'{base}_EVN{ext}'

    @property
    def path_odd(self):
        base, ext = splitext(self.path)
        return f'{base}_ODD{ext}'

    @property
    def is_split(self):
        return isfile(self.path_evn) and isfile(self.path_odd)

    def __init__(self, path: str):
        self.path = path
        # MDOC files are read lazily
        self._mdoc = None

    def files_exist(self, is_split) -> bool:
        return self.path is not None and isfile(self.path) and isfile(self.mdoc_path) and is_split == self.is_split

    def assert_files_exist(self, is_split):
        for file in [self.path, self.mdoc_path] + ([self.path_evn, self.path_odd] if is_split else []):
            if not isfile(file):
                raise FileNotFoundError(f'File does not exist: {file}')


def motioncor2(subframes: list, output_dir: str, splitsum: bool = False, binning: int = 2, group: int = 1,
               override_gainref: str = None, gpus: Optional[str]=None):
    assert_subframes_list(subframes, is_split=False)
    tempdir = join(output_dir, 'motioncor2_temp')
    if not isdir(tempdir):
        os.makedirs(tempdir)

    # Currently, only zero or one unique gain refs are supported, so check if that's given
    # Also, use the provided gain ref if it is supplied (option: override_gainref)
    gain_refs = set([subframe.mdoc['framesets'][0].get('GainReference', None) for subframe in subframes]) \
        if override_gainref is None \
        else {override_gainref}
    if len(gain_refs) != 1:
        raise Exception(
            f'Only zero or one unique gain refs are supported, yet {len(gain_refs)} were found in the MDOC files:\n{", ".join(gain_refs)}')
    # The gain ref should be in the same folder as the input file(s), so check if it's there
    gain_ref_dm4 = gain_refs.pop()
    gain_ref_mrc = None
    if gain_ref_dm4 is not None:
        gain_ref_dm4 = join(dirname(subframes[0].path), basename(gain_ref_dm4))
        if not isfile(gain_ref_dm4):
            raise FileNotFoundError(f'Expected gain reference at {gain_ref_dm4}, aborting')
        print(f'Found unique gain reference {gain_ref_dm4}, converting to MRC')
        # The gain ref is saved in dm4 format, convert to MRC for motioncor
        gain_ref_mrc = splitext(basename(gain_ref_dm4))[0]  # Basename of gain ref without extension and path
        gain_ref_mrc = join(tempdir, gain_ref_mrc) + '.mrc'
        subprocess.run(['dm2mrc', gain_ref_dm4, gain_ref_mrc])
    else:
        print('No gain reference is specified in the MDOC files, continuing without')

    # Link the input files to the working dir
    # so that files that should not be motioncor'ed are not
    for subframe in subframes:
        os.symlink(abspath(subframe.path), join(tempdir, basename(subframe.path)))

    command = ['/net/urz/sds-hd/sd18g002/Moritz/scripts/MotionCor2_1.4.2/MotionCor2_1.4.2_Cuda111-02-15-2020',
               '-InTiff', abspath(tempdir) + path.sep,
               '-OutMrc', abspath(output_dir) + path.sep,
               # '-InSuffix', '.tif',
               '-Patch', '7', '5',
               '-Iter', '10',
               '-Tol', '0.5',
               '-Kv', '300',
               '-Ftbin', str(binning),
               '-Group', str(group),
               '-Serial', '1']
    if gpus is None:
        num_gpus = int(util.gpuinfo()['Attached GPUs'])
        command += ['-Gpu'] + [str(i) for i in range(num_gpus)] if num_gpus > 0 else []
    else:
        command += ['-Gpu', gpus]
    if splitsum:
        command += ['-SplitSum', '1']
    if gain_ref_mrc is not None:
        command += ['-Gain', abspath(gain_ref_mrc)]

    print(f'Running motioncor2 with command:\n{" ".join(command)}')
    with open(join(output_dir, 'motioncor2.log'), 'a') as out, open(join(output_dir, 'motioncor2.err'), 'a') as err:
        subprocess.run(command, cwd=tempdir, stdout=out, stderr=err)
    # Copy the mdoc files to the output dir, rename from .tif.mdoc to .mrc.mdoc
    # they are read and then written and not just copied so that the GainReference field can be removed
    # and the pixel spacing can be adjusted
    for subframe in subframes:
        # Sanity check: there should be only one frameset
        if not (isinstance(subframe.mdoc['framesets'], list) and len(subframe.mdoc['framesets']) == 1):
            raise 'Unexpected MDOC format: tomotools can only handle a single frameset per mdoc'
        subframe.mdoc['framesets'][0]['PixelSpacing'] *= binning
        subframe.mdoc['framesets'][0]['Binning'] *= binning
        if 'GainReference' in subframe.mdoc['framesets'][0]:
            del subframe.mdoc['framesets'][0]['GainReference']
        mdocfile.write(subframe.mdoc,
                       join(output_dir, splitext(splitext(basename(subframe.mdoc_path))[0])[0] + '.mrc.mdoc'))
    rmtree(tempdir)

    # Build a list of output files that will be returned to the caller
    output_frames = [SubFrame(path=join(output_dir, splitext(basename(subframe.path))[0] + '.mrc')) for subframe in
                     subframes]
    print('Checking MotionCor2 output files')
    assert_subframes_list(output_frames, is_split=splitsum)
    return output_frames
