import os
import mrcfile
import subprocess

from pathlib import Path
from typing import Optional

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
        stem = self.path.stem
        suffix = self.path.suffix
        evn_file = dir.joinpath(f'{stem}_EVN{suffix}')
        odd_file = dir.joinpath(f'{stem}_ODD{suffix}')
        return self.with_split_files(evn_file, odd_file)
    
    @property
    def angpix(self):
        with mrcfile.mmap(self.path,mode = 'r') as mrc:
            self.angpix = float(mrc.voxel_size.x)

    @property
    def dimZYX(self):
        with mrcfile.mmap(self.path,mode = 'r') as mrc:
            self.dimZYX = mrc.data.shape
    
    @staticmethod
    def from_tiltseries(tiltseries: TiltSeries, bin: int = 1, sirt: int = 5, thickness: Optional[int] = None, x_axis_tilt: int = 0, 
                        z_shift: int = 0, do_EVN_ODD: bool = False, trim: bool = True) -> 'Tomogram':
        
        ali_stack = tiltseries.path
        
        
            # Read pixelsize and image dimensions from brief header in case the stack was binned.
        with mrcfile.mmap(tiltseries.path, mode = 'r') as mrc:
            pix_xy = float(mrc.voxel_size.x)
            stack_dimensions = mrc.data.shape 
        
        if thickness is None:    
            # Define default thickness as function of pixel size -> always reconstruct 1 um if no better number is given
            thickness = str(round(6000 / pix_xy))        

        # Get dimensions of aligned stack - assumption is that tilt is around the y axis        
        [full_reconstruction_y,full_reconstruction_x] = stack_dimensions[1:3]

        
        # Bring stack to desired binning level
        if bin != 1:
            binned_stack = tiltseries.path.with_name(f'{tiltseries.path.stem}_bin_{bin}.mrc')
            subprocess.run(['binvol', '-x', str(bin), '-y', str(bin), '-z', '1', tiltseries.path, binned_stack],
                           stdout=subprocess.DEVNULL)
            print(f'{tiltseries.path}: Binned to {bin}.')
            ali_stack = binned_stack
            
            # TODO: add binning / reconstruction for split!
            # if do_EVN_ODD:
            #     if tiltseries.is_split:
            #         ali_evn = tiltseries.evn_path
            #         ali_odd = tiltseries.odd_path
                    

                    
                    
            #     else:
            #         print(f'{tiltseries.path}: EVN / ODD stacks not found and thus cannot be reconstructed.')

        # Perform imod WBP
        full_rec = tiltseries.path.with_name(f'{tiltseries.path.stem}_full_rec.mrc')
        
        subprocess.run(['tilt']
                       + (['-FakeSIRTiterations', str(sirt)] if sirt > 0 else []) +
                       ['-InputProjections', ali_stack,
                        '-OutputFile', full_rec,
                        '-IMAGEBINNED', str(bin),
                        '-XAXISTILT', str(x_axis_tilt),
                        '-TILTFILE', f'{list(tiltseries.path.parent.glob("*_ali.tlt"))[0]}',
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

        os.remove(binned_stack)

        print(f'{tiltseries.path}: Finished reconstruction.')
        
        if trim:
            # Trim: Read in dimensions of full_rec (as YZX) to avoid rounding differences due to binning
            with mrcfile.mmap(full_rec, mode = 'r') as mrc:
                full_rec_dim = mrc.data.shape
            
            final_rec = tiltseries.path.with_name(f'{tiltseries.path.stem}_rec_bin_{bin}.mrc')
    
            tr = subprocess.run(['trimvol',
                            '-x', f'1,{full_rec_dim[2]}',
                            '-y', f'1,{full_rec_dim[0]}',
                            '-z', f'1,{full_rec_dim[1]}',
                            '-sx', f'1,{full_rec_dim[2]}',
                            '-sy', f'1,{full_rec_dim[0]}',
                            '-sz', f'{int(full_rec_dim[1]) / 3:.0f},{int(full_rec_dim[1]) * 2 / 3:.0f}',
                            '-f', '-rx',
                            full_rec, final_rec],
                            stdout=subprocess.DEVNULL)
    
            if tr.returncode != 0:
                print(f'{tiltseries}: Trimming failed, keeping full_rec file.')
                return Tomogram(full_rec)
            else:
                print(f'{tiltseries}: Finished trimming.')
                os.remove(full_rec)
                return Tomogram(final_rec)
        
        return Tomogram(full_rec)
