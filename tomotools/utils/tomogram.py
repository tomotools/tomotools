import os
import subprocess
from glob import glob
from os import path
from pathlib import Path
from typing import List, Optional

import mrcfile

from tomotools.utils import comfile
from tomotools.utils.tiltseries import TiltSeries


class Tomogram:
    """Tomogram class."""

    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        self.path: Path = path
        self.is_split: bool = False
        self.evn_path: Optional[Path] = None
        self.odd_path: Optional[Path] = None

    def with_split_files(self, evn_file: Path, odd_file: Path) -> "Tomogram":
        """Create tomogram with EVN/ODD by passing their paths."""
        if not evn_file.is_file():
            raise FileNotFoundError(f"File not found: {evn_file}")
        if not odd_file.is_file():
            raise FileNotFoundError(f"File not found: {odd_file}")
        self.evn_path = evn_file
        self.odd_path = odd_file
        self.is_split = True
        return self

    def with_split_dir(self, dir: Path) -> "Tomogram":
        """Create tomogram with EVN/ODD by passing directory containing them."""
        if not dir.is_dir():
            raise NotADirectoryError(f'{dir} is not a directory!')
        return find_Tomogram_halves(self, dir)

    @property
    def angpix(self):
        """Return angpix from header."""
        with mrcfile.mmap(self.path, mode="r") as mrc:
            self.angpix = float(mrc.voxel_size.x)
        return self.angpix

    def dimZYX(self):
        """Return full dimensions from data shape."""
        with mrcfile.mmap(self.path, mode="r") as mrc:
            self.dimZYX = mrc.data.shape
        return self.dimZYX

    @staticmethod
    def from_tiltseries(
        tiltseries: TiltSeries,
        bin: int = 1,
        sirt: int = 5,
        thickness: Optional[int] = None,
        x_axis_tilt: float = 0,
        z_shift: float = 0,
        do_EVN_ODD: bool = False,
        trim: bool = True,
        convert_to_byte: bool = True
    ) -> "Tomogram":
        """Create Tomogram from TiltSeries, aka reconstruct."""
        # TODO: Reduce complexity C901
        ali_stack = tiltseries.path

        if do_EVN_ODD and tiltseries.is_split:
            ali_stack_evn = tiltseries.evn_path
            ali_stack_odd = tiltseries.odd_path

        pix_xy = tiltseries.angpix

        if thickness is None:
            # Define default thickness as function of pixel size
            # always reconstruct 600 nm if no better number is given
            thickness = str(round(6000 / pix_xy))

        # Get dimensions of aligned stack - assumption is that tilt is around the y axis
        [full_reconstruction_y,full_reconstruction_x] = tiltseries.dimZYX[1:3]

        # Bring stack to desired binning level

        # TODO: skip here if passed pre-binned aligned stack
        if bin != 1:
            binned_stack = tiltseries.path.with_name(
                f'{tiltseries.path.stem}_bin_{bin}.mrc')

            subprocess.run(['newstack',
                            '-in', tiltseries.path,
                            '-bin', str(bin),
                            '-antialias', '-1',
                            '-ou', binned_stack,
                            '-quiet'],
                           stdout=subprocess.DEVNULL)

            ali_stack = binned_stack
            print(f"{tiltseries.path}: Binned to {bin}.")

            if do_EVN_ODD and tiltseries.is_split:
                binned_stack_evn = tiltseries.evn_path.with_name(
                    f'{tiltseries.path.stem}_bin_{bin}_EVN.mrc')
                binned_stack_odd = tiltseries.odd_path.with_name(
                    f'{tiltseries.path.stem}_bin_{bin}_ODD.mrc')

                subprocess.run(['newstack',
                                '-in', tiltseries.evn_path,
                                '-bin', str(bin),
                                '-antialias', '-1',
                                '-ou', binned_stack_evn,
                                '-quiet'],
                               stdout=subprocess.DEVNULL)

                subprocess.run(['newstack',
                                '-in', tiltseries.odd_path,
                                '-bin', str(bin),
                                '-antialias', '-1',
                                '-ou', binned_stack_odd,
                                '-quiet'],
                               stdout=subprocess.DEVNULL)

                ali_stack_evn = binned_stack_evn
                ali_stack_odd = binned_stack_odd
                print(f"{tiltseries.path}: Binned EVN/ODD to {bin}.")

        # Perform imod WBP
        full_rec = tiltseries.path.with_name(f'{tiltseries.path.stem}_full_rec.mrc')

        subprocess.run(['tilt']
                       + (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []) +
                       ['-InputProjections', ali_stack,
                        '-OutputFile', full_rec,
                        '-IMAGEBINNED', str(bin),
                        '-XAXISTILT', str(x_axis_tilt),
                        '-TILTFILE', f'{list(tiltseries.path.parent.glob("*.tlt"))[0]}',
                        '-THICKNESS', str(thickness),
                        '-RADIAL', '0.35,0.035',
                        '-FalloffIsTrueSigma', '1',
                        '-SCALE', '0.0,0.05',
                        '-PERPENDICULAR',
                        '-MODE', '2',
                        '-FULLIMAGE', f'{full_reconstruction_x} {full_reconstruction_y}', #noqa: E501
                        '-SUBSETSTART', '0,0',
                        '-AdjustOrigin',
                        '-ActionIfGPUFails', '1,2',
                        '-OFFSET', '0.0',
                        '-SHIFT', f'0.0,{z_shift}',
                        '-UseGPU', '0'],
                        stdout=subprocess.DEVNULL)

        print(f'{tiltseries.path}: Finished reconstruction.')

        if do_EVN_ODD and tiltseries.is_split:
            full_rec_evn = tiltseries.path.with_name(f'{tiltseries.path.stem}_full_rec_EVN.mrc') #noqa: E501
            full_rec_odd = tiltseries.path.with_name(f'{tiltseries.path.stem}_full_rec_ODD.mrc') #noqa: E501

            subprocess.run(['tilt']
                           + (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []) +
                           ['-InputProjections', ali_stack_evn,
                            '-OutputFile', full_rec_evn,
                            '-IMAGEBINNED', str(bin),
                            '-XAXISTILT', str(x_axis_tilt),
                            '-TILTFILE', f'{list(tiltseries.path.parent.glob("*.tlt"))[0]}', #noqa: E501
                            '-THICKNESS', str(thickness),
                            '-RADIAL', '0.35,0.035',
                            '-FalloffIsTrueSigma', '1',
                            '-SCALE', '0.0,0.05',
                            '-PERPENDICULAR',
                            '-MODE', '2',
                            '-FULLIMAGE', f'{full_reconstruction_x} {full_reconstruction_y}', #noqa: E501
                            '-SUBSETSTART', '0,0',
                            '-AdjustOrigin',
                            '-ActionIfGPUFails', '1,2',
                            '-OFFSET', '0.0',
                            '-SHIFT', f'0.0,{z_shift}',
                            '-UseGPU', '0'],
                            stdout=subprocess.DEVNULL)

            subprocess.run(['tilt']
                           + (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []) +
                           ['-InputProjections', ali_stack_odd,
                            '-OutputFile', full_rec_odd,
                            '-IMAGEBINNED', str(bin),
                            '-XAXISTILT', str(x_axis_tilt),
                            '-TILTFILE', f'{list(tiltseries.path.parent.glob("*.tlt"))[0]}', #noqa: E501
                            '-THICKNESS', str(thickness),
                            '-RADIAL', '0.35,0.035',
                            '-FalloffIsTrueSigma', '1',
                            '-SCALE', '0.0,0.05',
                            '-PERPENDICULAR',
                            '-MODE', '2',
                            '-FULLIMAGE', f'{full_reconstruction_x} {full_reconstruction_y}', #noqa: E501
                            '-SUBSETSTART', '0,0',
                            '-AdjustOrigin',
                            '-ActionIfGPUFails', '1,2',
                            '-OFFSET', '0.0',
                            '-SHIFT', f'0.0,{z_shift}',
                            '-UseGPU', '0'],
                            stdout=subprocess.DEVNULL)

            if bin != 1:
                os.remove(binned_stack_evn)
                os.remove(binned_stack_odd)

            print(f'{tiltseries.path}: Finished reconstruction of EVN/ODD stacks.')

        if bin != 1:
            os.remove(binned_stack)

        if trim:
            # Trim: Read in dimensions of full_rec (as YZX)
            with mrcfile.mmap(full_rec, mode = 'r') as mrc:
                full_rec_dim = mrc.data.shape

            final_rec = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}.mrc') #noqa: E501

            tr =subprocess.run(['trimvol',
                                '-x', f'1,{full_rec_dim[2]}',
                                '-y', f'1,{full_rec_dim[0]}',
                                '-z', f'1,{full_rec_dim[1]}',
                                '-f', '-rx'] +
                               (['-sx', f'1,{full_rec_dim[2]}',
                                 '-sy', f'1,{full_rec_dim[0]}',
                                 '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}'] #noqa: E501
                                if convert_to_byte else []) +
                               [full_rec, final_rec],
                               stdout=subprocess.DEVNULL)

            if tr.returncode != 0:
                print(f"{tiltseries.path}: Trimming failed, keeping full_rec file.")
                if do_EVN_ODD and tiltseries.is_split:
                    return Tomogram(full_rec).with_split_files(
                        full_rec_evn, full_rec_odd
                    )
                else:
                    return Tomogram(full_rec)

            if do_EVN_ODD and tiltseries.is_split:
                final_rec_evn = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}_EVN.mrc') #noqa: E501
                final_rec_odd = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}_ODD.mrc') #noqa: E501

                subprocess.run(['trimvol',
                                '-x', f'1,{full_rec_dim[2]}',
                                '-y', f'1,{full_rec_dim[0]}',
                                '-z', f'1,{full_rec_dim[1]}',
                                '-f', '-rx'] +
                               (['-sx', f'1,{full_rec_dim[2]}',
                                 '-sy', f'1,{full_rec_dim[0]}',
                                 '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}'] #noqa: E501
                                if convert_to_byte else []) +
                               [full_rec_evn, final_rec_evn],
                                stdout=subprocess.DEVNULL)

                subprocess.run(['trimvol',
                                '-x', f'1,{full_rec_dim[2]}',
                                '-y', f'1,{full_rec_dim[0]}',
                                '-z', f'1,{full_rec_dim[1]}',
                                '-f', '-rx'] +
                               (['-sx', f'1,{full_rec_dim[2]}',
                                 '-sy', f'1,{full_rec_dim[0]}',
                                 '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}'] #noqa: E501
                                if convert_to_byte else []) +
                               [full_rec_odd, final_rec_odd],
                                stdout=subprocess.DEVNULL)

                print(f'{tiltseries.path}: Finished trimming.')

                os.remove(full_rec)
                os.remove(full_rec_evn)
                os.remove(full_rec_odd)

                return Tomogram(final_rec).with_split_files(
                    final_rec_evn, final_rec_odd
                )

            os.remove(full_rec)
            return Tomogram(final_rec)

        return Tomogram(full_rec)

    @staticmethod
    def from_tiltseries_3dctf(tiltseries: TiltSeries, binning=1,
                              thickness=3000, z_slices_nm=25,
                              fullimage: Optional[List] = None) -> 'Tomogram':
        """
        Calculate Tomogram with imod ctf3d.

        As ctf3d requires tilt.com and ctfcorrection.com, provide imod-aligned
        stack as input (either from etomo or AreTomo + export).
        Stack is assumed to be at the desired binning level and dose-filtered.

        This is only useful for STA, so the following options are unavailable:
        - fSIRT
        - EVN/ODD
        - x_axis_tilt
        - convert_to_byte
        """
        if fullimage is None:
            fullimage = [1000, 1000]

        # Check necessary files are there
        if not path.isfile(tiltseries.path.with_name("ctfcorrection.com")):
            raise FileNotFoundError("ctfcorrection.com not found.")

        if not path.isfile(tiltseries.path.with_name("tilt.com")):
            raise FileNotFoundError("tilt.com not found")

        # Fix tilt.com
        comfile.fix_tiltcom(tiltseries, thickness, 0, binning, fullimage)

        print(f'Fixed tilt.com file for {tiltseries.path.parent.name}.')

        # Set up files
        subprocess.run(['ctf3dsetup',
                        '-th', str(z_slices_nm),
                        '-pa','tilt'], cwd = tiltseries.path.parent)

        print(f'Reconstructing {tiltseries.path.parent.name} with ctf3d.')

        # Perform actual reconstruction
        subprocess.run(['processchunks',
                        'localhost',
                        'ctf3d'], cwd = tiltseries.path.parent,
                       stdout = subprocess.DEVNULL)

        print(f'Reconstruction of {tiltseries.path.parent.name} done.')

        # Clean up
        tiltseries.delete_files(False)

        # Rotate tomogram to default
        subprocess.run(['clip','rotx',
                        tiltseries.path.parent /
                        f'{tiltseries.path.stem}_3dctf_rec.mrc',
                        tiltseries.path.parent /
                        f'{tiltseries.mdoc.with_suffix("").stem}_3dctf_rec_rot.mrc'])
        print(f'Rotation of {tiltseries.path.parent.name} done.')

        os.remove(tiltseries.path.parent /
                  f'{tiltseries.path.stem}_3dctf_rec.mrc')

        return Tomogram(tiltseries.path.parent /
                        f'{tiltseries.mdoc.with_suffix("").stem}_3dctf_rec_rot.mrc')


def find_Tomogram_halves(tomo: Tomogram, split_dir: Optional[Path] = None):
    """Check whether tomogram has EVN/ODD halves.

    Optionally, you can pass a directory where the split reconstructions are.
    """
    if split_dir is None:
        parent_dir = tomo.path.parent

    else:
        parent_dir = split_dir

    # Generate plausible filenames either after MotionCor2 or imod notation:
    EVN_file = parent_dir / f'{tomo.path.stem}_EVN.mrc'
    ODD_file = parent_dir / f'{tomo.path.stem}_ODD.mrc'

    even_file = parent_dir / f'{tomo.path.stem[:-3]}even_rec.mrc'
    odd_file = parent_dir / f'{tomo.path.stem[:-3]}odd_rec.mrc'

    if path.isfile(EVN_file) and path.isfile(ODD_file):
        return tomo.with_split_files(EVN_file, ODD_file)
    elif path.isfile(even_file) and path.isfile(odd_file):
        return tomo.with_split_files(even_file, odd_file)
    else:
        return tomo

def convert_input_to_Tomogram(input_files: List[Path]):
    """Takes list of input files or folders from Click.

    Returns list of Tomogram objects with or without split reconstructions.
    """
    input_tomo = []

    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_tomo.append(Tomogram(Path(input_file)))
        elif input_file.is_dir():
            input_tomo += ([Tomogram(Path(file)) for file in glob(path.join(input_file,
                                                                            '*_rec_bin_[0-9].mrc'))])
            # Do not include full_rec, even_rec and odd_rec
            input_tomo += ([Tomogram(Path(Path(file))) for file in list(set(glob(path.join(input_file, '*_rec.mrc'))) #noqa: E501
                                                                        -set(glob(path.join(input_file,'*even_rec.mrc')))
                                                                        -set(glob(path.join(input_file,'*_odd_rec.mrc')))
                                                                        -set(glob(path.join(input_file,'*_full_rec.mrc')))
                                                                        )])

    for tomo in input_tomo:
        tomo = find_Tomogram_halves(tomo)
        if tomo.is_split:
            print(f'Found reconstruction {tomo.path} with EVN and ODD stacks.')
        else:
            tomo = tomo
            print(f'Found reconstruction {tomo.path}.')

    return input_tomo
