from pathlib import Path
from typing import Optional

from tomotools.utils import mdocfile


class Movie:
    def __init__(self, path: Path, tilt_angle: float = 0.0):
        if not path.is_file():
            raise FileNotFoundError(f"File {path} does not exist!")
        self.path: Path = path
        self.tilt_angle: float = tilt_angle
        self.mdoc_path: Path = Path(f"{path}.mdoc")
        self.mdoc: Optional[dict] = (
            mdocfile.read(self.mdoc_path) if self.mdoc_path.is_file() else None
        )

    @property
    def is_mrc(self):
        return self.path.suffix == ".mrc"

    @property
    def is_tiff(self):
        return self.path.suffix == ".tiff" or self.path.suffix == ".tif"
