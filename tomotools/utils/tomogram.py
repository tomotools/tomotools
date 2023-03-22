import os
import subprocess
import mrcfile

from pathlib import Path
from typing import Optional
from os import path
from glob import glob

from tomotools.utils.tiltseries import TiltSeries


class Tomogram:
    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f'File not found: {path}')
        self.path: Path = path
        self.is_split: bool = False
        self.evn_path: Optional[Path] = None
        self.odd_path: Optional[Path] = None

    def with_split_files(self, evn_file: Path, odd_file: Path) -> 'Tomogram':
        if not evn_file.is_file():
            raise FileNotFoundError(f'File not found: {evn_file}')
        if not odd_file.is_file():
            raise FileNotFoundError(f'File not found: {odd_file}')
        self.evn_path = evn_file
        self.odd_path = odd_file
        self.is_split = True
        return self

    def with_split_dir(self, dir: Path) -> 'Tomogram':
        if not dir.is_dir():
            raise NotADirectoryError(f'{dir} is not a directory!')
        return find_Tomogram_halves(self, dir)
    
    def angpix(self):
        with mrcfile.mmap(self.path,mode = 'r') as mrc:
            self.angpix = float(mrc.voxel_size.x)
        return self.angpix

    def dimZYX(self):
        with mrcfile.mmap(self.path,mode = 'r') as mrc:
            self.dimZYX = mrc.data.shape
        return self.dimZYX

    @staticmethod
    def from_tiltseries(tiltseries: TiltSeries, bin: int = 1, sirt: int = 5, thickness: Optional[int] = None,
                        x_axis_tilt: float = 0,
                        z_shift: float = 0, do_EVN_ODD: bool = False, trim: bool = True, convert_to_byte: bool = True) -> 'Tomogram':

        ali_stack = tiltseries.path

        if do_EVN_ODD and tiltseries.is_split:
            ali_stack_evn = tiltseries.evn_path
            ali_stack_odd = tiltseries.odd_path

        # Get stack dimensions to define size of the output tomogram.
        with mrcfile.mmap(tiltseries.path, mode='r') as mrc:
            pix_xy = float(mrc.voxel_size.x)
            stack_dimensions = mrc.data.shape 
        
        if thickness is None:    
            # Define default thickness as function of pixel size -> always reconstruct 600 nm if no better number is given
            thickness = str(round(6000 / pix_xy))        

        # Get dimensions of aligned stack - assumption is that tilt is around the y axis        
        [full_reconstruction_y,full_reconstruction_x] = stack_dimensions[1:3]
        
        # Bring stack to desired binning level
        if bin != 1:
            binned_stack = tiltseries.path.with_name(f'{tiltseries.path.stem}_bin_{bin}.mrc')
            subprocess.run(['binvol', '-x', str(bin), '-y', str(bin), '-z', '1', tiltseries.path, binned_stack],
                           stdout=subprocess.DEVNULL)
            ali_stack = binned_stack
            print(f'{tiltseries.path}: Binned to {bin}.')
            
            if do_EVN_ODD and tiltseries.is_split:
                binned_stack_evn = tiltseries.evn_path.with_name(f'{tiltseries.path.stem}_bin_{bin}_EVN.mrc')
                binned_stack_odd = tiltseries.odd_path.with_name(f'{tiltseries.path.stem}_bin_{bin}_ODD.mrc')
                
                subprocess.run(['binvol', '-x', str(bin), '-y', str(bin), '-z', '1', tiltseries.evn_path, binned_stack_evn],
                               stdout=subprocess.DEVNULL)
                subprocess.run(['binvol', '-x', str(bin), '-y', str(bin), '-z', '1', tiltseries.odd_path, binned_stack_odd],
                               stdout=subprocess.DEVNULL)
                
                ali_stack_evn = binned_stack_evn
                ali_stack_odd = binned_stack_odd
                print(f'{tiltseries.path}: Binned EVN/ODD to {bin}.')

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
                        '-FULLIMAGE', f'{full_reconstruction_x} {full_reconstruction_y}',
                        '-SUBSETSTART', '0,0',
                        '-AdjustOrigin',
                        '-ActionIfGPUFails', '1,2',
                        '-OFFSET', '0.0',
                        '-SHIFT', f'0.0,{z_shift}',
                        '-UseGPU', '0'],
                        stdout=subprocess.DEVNULL)

        if bin != 1:        
            os.remove(binned_stack)
        
        print(f'{tiltseries.path}: Finished reconstruction.')
        
        if do_EVN_ODD and tiltseries.is_split:
            full_rec_evn = tiltseries.path.with_name(f'{tiltseries.path.stem}_full_rec_EVN.mrc')
            full_rec_odd = tiltseries.path.with_name(f'{tiltseries.path.stem}_full_rec_ODD.mrc')
            
            subprocess.run(['tilt']
                           + (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []) +
                           ['-InputProjections', ali_stack_evn,
                            '-OutputFile', full_rec_evn,
                            '-IMAGEBINNED', str(bin),
                            '-XAXISTILT', str(x_axis_tilt),
                            '-TILTFILE', f'{list(tiltseries.path.parent.glob("*.tlt"))[0]}',
                            '-THICKNESS', str(thickness),
                            '-RADIAL', '0.35,0.035',
                            '-FalloffIsTrueSigma', '1',
                            '-SCALE', '0.0,0.05',
                            '-PERPENDICULAR',
                            '-MODE', '2',
                            '-FULLIMAGE', f'{full_reconstruction_x} {full_reconstruction_y}',
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
                            '-TILTFILE', f'{list(tiltseries.path.parent.glob("*.tlt"))[0]}',
                            '-THICKNESS', str(thickness),
                            '-RADIAL', '0.35,0.035',
                            '-FalloffIsTrueSigma', '1',
                            '-SCALE', '0.0,0.05',
                            '-PERPENDICULAR',
                            '-MODE', '2',
                            '-FULLIMAGE', f'{full_reconstruction_x} {full_reconstruction_y}',
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
        
        if trim:
            # Trim: Read in dimensions of full_rec (as YZX) to avoid rounding differences due to binning
            with mrcfile.mmap(full_rec, mode = 'r') as mrc:
                full_rec_dim = mrc.data.shape
            
            final_rec = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}.mrc')
    
            tr =subprocess.run(['trimvol',
                                '-x', f'1,{full_rec_dim[2]}',
                                '-y', f'1,{full_rec_dim[0]}',
                                '-z', f'1,{full_rec_dim[1]}',
                                '-f', '-rx'] +
                               (['-sx', f'1,{full_rec_dim[2]}',
                                 '-sy', f'1,{full_rec_dim[0]}',
                                 '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}'] if convert_to_byte else []) +
                               [full_rec, final_rec],
                               stdout=subprocess.DEVNULL)
            
            if tr.returncode != 0:
                print(f'{tiltseries.path}: Trimming failed, keeping full_rec file.')
                if do_EVN_ODD and tiltseries.is_split:
                    return Tomogram(full_rec).with_split_files(full_rec_evn, full_rec_odd)
                else:
                    return Tomogram(full_rec)
            
            if do_EVN_ODD and tiltseries.is_split:
                final_rec_evn = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}_EVN.mrc')
                final_rec_odd = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}_ODD.mrc')
                
                subprocess.run(['trimvol',
                                '-x', f'1,{full_rec_dim[2]}',
                                '-y', f'1,{full_rec_dim[0]}',
                                '-z', f'1,{full_rec_dim[1]}',
                                '-f', '-rx'] +
                               (['-sx', f'1,{full_rec_dim[2]}',
                                 '-sy', f'1,{full_rec_dim[0]}',
                                 '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}'] if convert_to_byte else []) +
                               [full_rec_evn, final_rec_evn],
                                stdout=subprocess.DEVNULL)
                
                subprocess.run(['trimvol',
                                '-x', f'1,{full_rec_dim[2]}',
                                '-y', f'1,{full_rec_dim[0]}',
                                '-z', f'1,{full_rec_dim[1]}',
                                '-f', '-rx'] +
                               (['-sx', f'1,{full_rec_dim[2]}',
                                 '-sy', f'1,{full_rec_dim[0]}',
                                 '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}'] if convert_to_byte else []) +
                               [full_rec_odd, final_rec_odd],
                                stdout=subprocess.DEVNULL)
                
                print(f'{tiltseries.path}: Finished trimming.')
                os.remove(full_rec)
                os.remove(full_rec_evn)
                os.remove(full_rec_odd)
                return Tomogram(final_rec).with_split_files(final_rec_evn, final_rec_odd)
            
            os.remove(full_rec)
            return Tomogram(final_rec)
            
        return Tomogram(full_rec)

def find_Tomogram_halves(tomo: Tomogram, split_dir: Path = None):
    ''' Check whether tomogram has EVN/ODD halves. Optionally, you can pass a directory where the split reconstructions are.'''
    
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

def convert_input_to_Tomogram(input_files:[]):
    ''' Takes list of input files or folders from Click. Returns list of Tomogram objects with or without split reconstructions. '''
    input_tomo = list()
    
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            input_tomo.append(Tomogram(Path(input_file)))
        elif input_file.is_dir():
            input_tomo += ([Tomogram(Path(file))for file in glob(path.join(input_file, '*_rec_bin_[0-9].mrc'))])
            # Do not include full_rec, even_rec and odd_rec
            input_tomo += ([Tomogram(Path(Path(file))) for file in list(set(glob(path.join(input_file, '*_rec.mrc')))-set(glob(path.join(input_file,'*even_rec.mrc')))-set(glob(path.join(input_file,'*_odd_rec.mrc')))-set(glob(path.join(input_file,'*_full_rec.mrc'))))])
            
    for tomo in input_tomo:
        tomo = find_Tomogram_halves(tomo)
        if tomo.is_split:
            print(f'Found reconstruction {tomo.path} with EVN and ODD stacks.')
        else:
            tomo = tomo
            print(f'Found reconstruction {tomo.path}.')
            
    return input_tomo