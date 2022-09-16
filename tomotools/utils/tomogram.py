import os
import shutil
import subprocess
import warnings
from glob import glob
from os import path
from os.path import splitext, isfile, join, isdir, basename, abspath
from typing import Optional

import mrcfile

from tomotools.utils import mdocfile, util

class Tilt_series:
    def __init__(self, path:str, excludetilt:list()):
        pass
    

class Tomogram:
    def __init__(self, path: str):
        self.path = path
        
    @property
    def angpix(self):
        with mrcfile.open(self) as mrc:
            angpix = float(mrc.voxel_size.x)
        return angpix
    
    @property
    def dimensions(self):
        with mrcfile.open(self) as mrc:
            x,y,z = mrc.data.shape
        return x,y,z
    
    @property
    def with_split_volumes(self):
        return self.path.endswith('.mrc') or self.path.endswith('.mrcs')
        
    @property
    def EVN_path(self, is_split):
        return isfile(self.mdoc_path)

    @property    
    def ODD_path(self, is_split) -> bool:
        return self.path is not None and isfile(self.path) and is_split == self.is_split

    def get_defocus(self):
        pass