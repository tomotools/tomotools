import mrcfile
import numpy as np
from pathlib import Path
from typing import Optional

from tomotools.utils.tiltseries import TiltSeries, get_defocus 

class Tomogram:
    def __init__(self, path: Path):
        self.path: Path = path        
        self.is_split: bool = False
        self.evn_path: Optional[Path] = None
        self.odd_path: Optional[Path] = None
        
    @property
    def angpix(self):
        with mrcfile.open(self.path) as mrc:
            angpix = float(mrc.voxel_size.x)
        return angpix
    
    @property
    def dimensionsZYX(self):
        with mrcfile.open(self.path) as mrc:
            z,y,x = mrc.data.shape
        return z,y,x
    
    @property
    def volume(self):
        with mrcfile.open(self.path) as mrc:
            volume = mrc.data
        return volume
    
    @property
    def EVN_path(self):
        pass

    @property    
    def ODD_path(self):
        pass

    @property
    def with_split_volumes(self):
        pass

    @property()    
    def central_defocus(self):
        def_list = get_defocus(self.path)
        return def_list[np.floor(len(def_list))]
    
    @staticmethod()
    def from_tiltseries(tiltseries: TiltSeries, excludefile: Optional[Path]):
        pass