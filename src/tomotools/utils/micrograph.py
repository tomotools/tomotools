import os
import shutil
import subprocess
from os.path import isfile, join
from pathlib import Path


from tomotools.utils import mdocfile, util
from tomotools.utils.movie import Movie


class Micrograph:
    """Class for Micrographs."""

    def __init__(self, path: Path, tilt_angle: float = 0.0):
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        self.path: Path = path
        self.mdoc_path: Path = Path(str(path) + ".mdoc")
        self.mdoc = mdocfile.read(self.mdoc_path) if self.mdoc_path.is_file() else None
        self.tilt_angle: float = tilt_angle
        self.is_split: bool = False
        self.evn_path: Path | None = None
        self.odd_path: Path | None = None

    def with_split_files(self, evn_file: Path, odd_file: Path) -> "Micrograph":
        """Create Micrograph with associated EVN ODD stacks, giving their paths."""
        if not evn_file.is_file():
            raise FileNotFoundError(f"File not found: {evn_file}")
        if not odd_file.is_file():
            raise FileNotFoundError(f"File not found: {odd_file}")
        self.evn_path = evn_file
        self.odd_path = odd_file
        self.is_split = True
        return self

    def with_split_dir(self, dir: Path) -> "Micrograph":
        """Create Micrograph with associated EVN ODD stacks, giving their parent dir."""
        if not dir.is_dir():
            raise NotADirectoryError(f"{dir} is not a directory!")
        stem = self.path.stem
        suffix = self.path.suffix
        evn_file = dir.joinpath(f"{stem}_EVN{suffix}")
        odd_file = dir.joinpath(f"{stem}_ODD{suffix}")
        return self.with_split_files(evn_file, odd_file)

    @staticmethod
    def from_movies(
        movies: list[Movie],
        output_dir: Path,
        splitsum: bool = False,
        binning: int = 1,
        group: int = 2,
        patch: bool = False,
        patch_x: int = 5,
        patch_y: int = 7,
        mcrot: int | None = None,
        mcflip: int | None = None,
        override_gainref: Path | None = None,
        gpu: str | None = None,
    ) -> "list[Micrograph]":
        """Create micrograph from a list of movies using MotionCor."""
        tempdir = output_dir.joinpath("motioncor2_temp")
        tempdir.mkdir(parents=True)

        # Find gain reference
        # 1. Use override_gainref if given
        # 2. Otherwise, check mdoc for gain reference
        if override_gainref is not None:
            override_gainref = Path(override_gainref)
        elif override_gainref is None and movies[0].mdoc is not None:
            # Check if there is a subframe mdoc and if it contains a gain reference path
            gain_refs = {
                movie.mdoc["framesets"][0].get("GainReference", None)
                for movie in movies
                if movie.mdoc is not None
            }
            gain_refs.discard(None)
            if len(gain_refs) > 1:
                raise Exception("Found multiple gain references, only one is supported")
            elif len(gain_refs) == 1:
                # The gain ref should be in the same folder as the input file(s)
                # Check if it's there.
                override_gainref = Path(gain_refs.pop())
                override_gainref = movies[0].path.parent / override_gainref  # pyright: ignore[reportOperatorIssue]
                if not override_gainref.is_file():  # pyright: ignore[reportOptionalMemberAccess]
                    raise FileNotFoundError(
                        f"Couldn't find gain reference at {override_gainref}, aborting"
                    )

        # Convert gain reference to mrc if needed
        if override_gainref is None:
            gain_ref_mrc = None
            print("No gainref is given or found, continuing without gain correction.")
        else:
            gain_ref_mrc = _ensure_gainref_mrc(override_gainref, output_dir)
            if not gain_ref_mrc.is_file():
                raise FileNotFoundError(
                    f"The GainRef file {gain_ref_mrc} doesn't exist!"
                )
            print(f"Using gainref file {gain_ref_mrc}")

        # Build and run MotionCor command
        command = [
            motioncor_executable(),
            "-FtBin",
            str(binning),
        ]

        if gpu is None:
            command += (
                ["-Gpu"] + [str(i) for i in range(util.num_gpus())]
                if util.num_gpus() > 0
                else []
            )
        else:
            command += ["-Gpu", gpu]

        if splitsum:
            command += ["-SplitSum", "1"]

        if gain_ref_mrc is not None:
            command += ["-Gain", gain_ref_mrc.absolute()]

        if mcrot is not None and mcflip is not None:
            command += ["-RotGain", str(mcrot), "-FlipGain", str(mcflip)]

        if (
            override_gainref is not None
            and override_gainref.suffix == ".dm4"
            and check_defects(override_gainref) is not None
        ):
            defects_tif_path = defects_tif(override_gainref, tempdir, movies[0].path)
            if defects_tif_path is None:
                raise FileNotFoundError("Defects file could not be created.")
            command += [
                "-DefectMap",
                defects_tif_path.absolute(),
            ]

        # Patch alignment takes two groupings, for global and local alignments.
        # Default are 1 and 4.
        if patch:
            command += [
                "-Patch",
                str(patch_x),
                str(patch_y),
                "-Group",
                f"{group} {4 * group}",
            ]
        else:
            command += ["-Group", str(group)]

        # Now, correct every movie separately, since -Serial 1 causes issues
        for movie in movies:
            in_flag = "-InMrc" if movie.is_mrc else "-InTiff"
            out_path = output_dir / movie.path.with_suffix(".mrc").name
            command += [in_flag, movie.path.absolute(), "-OutMrc", out_path]

            with (
                open(output_dir / "motioncor2.log", "a") as out,
                open(output_dir / "motioncor2.err", "a") as err,
            ):
                subprocess.run(command, cwd=tempdir, stdout=out, stderr=err)

        # If present, copy the mdoc files to the output dir
        # Rename from .tif.mdoc to .mrc.mdoc
        # GainReference field can is removed and the pixel spacing adjusted
        for movie in movies:
            if movie.mdoc is not None:
                # Sanity check: there should be only one frameset
                if not (
                    isinstance(movie.mdoc["framesets"], list)
                    and len(movie.mdoc["framesets"]) == 1
                ):
                    raise Exception(
                        "Unexpected MDOC format: can only handle 1 frameset per mdoc"
                    )
                # Adjust pixel size and binning
                movie.mdoc["framesets"][0]["PixelSpacing"] *= binning
                movie.mdoc["framesets"][0]["Binning"] *= binning
                # Delete GainReference entry
                if "GainReference" in movie.mdoc["framesets"][0]:
                    del movie.mdoc["framesets"][0]["GainReference"]
                mdocfile.write(
                    movie.mdoc,
                    output_dir.joinpath(Path(movie.mdoc_path.stem).stem + ".mrc.mdoc"),
                )
        shutil.rmtree(tempdir)

        print("Checking MotionCor output files")

        if gain_ref_mrc is not None:
            with open(join(output_dir, "motioncor2.log")) as log:
                if any(line.startswith("Warning: Gain ref not found.") for line in log):
                    raise Exception(
                        "Gain reference was specified, but not applied by MotionCor."
                    )

        if os.path.isdir(output_dir.joinpath("motioncor2_gain")):
            shutil.rmtree(output_dir.joinpath("motioncor2_gain"))

        output_micrographs = [
            Micrograph(
                path=output_dir.joinpath(movie.path.with_suffix(".mrc").name),
                tilt_angle=movie.tilt_angle,
            )
            for movie in movies
        ]
        if splitsum:
            output_micrographs = [
                mic.with_split_dir(output_dir) for mic in output_micrographs
            ]
        return output_micrographs


def motioncor_executable() -> str | None:
    """Return MotionCor2/3 executable.

    Path can be set with one of the following ways (in order of priority):
    1. Setting the MOTIONCOR_EXECUTABLE variable to the full path of the executable.
    2. Putting "MotionCor3" in PATH.
    3. Putting "MotionCor2" in PATH.

    """
    if "MOTIONCOR_EXECUTABLE" in os.environ:
        mc_exe = os.environ["MOTIONCOR_EXECUTABLE"]
        if isfile(mc_exe):
            return mc_exe
        else:
            raise FileNotFoundError(
                f'MOTIONCOR_EXECUTABLE is set to "{mc_exe}", but file is missing.'
            )

    elif shutil.which("MotionCor3") is not None:
        return shutil.which("MotionCor3")
    elif shutil.which("MotionCor2") is not None:
        return shutil.which("MotionCor2")
    else:
        raise FileNotFoundError("MotionCor not found. Check README.md for setup info.")


def _ensure_gainref_mrc(gain_ref: Path, output_dir: Path) -> Path:
    temp_gain = output_dir / "motioncor2_gain"
    temp_gain.mkdir()
    gain_out = temp_gain / (gain_ref.with_suffix(".mrc").name)
    print(f"Found gain reference {gain_ref}, converting to {gain_out}")
    match gain_ref.suffix:
        case ".mrc":
            gain_out = gain_ref
        case ".dm4":
            subprocess.run(["dm2mrc", gain_ref, gain_out], stdout=subprocess.DEVNULL)
        case ".tif" | ".tiff" | ".gain":
            subprocess.run(["tif2mrc", gain_ref, gain_out], stdout=subprocess.DEVNULL)
        case _:
            raise AttributeError(
                "Gain reference can only be in .tif(f) or .dm4 format!"
            )
    return gain_out


def sem2mc2(RotationAndFlip: int = 0):
    """Read RotationAndFlip for MotionCor2.

    Converts SerialEM property RotationAndFlip into MC2 -RotGain / -FlipGain values.

    RotationAndFlip is defined as n+m where n*90° is CCW rotation and
    m is 0 for no flip and 4 for flip around Y (=vertical axis).
    For MotionCor2: Rotation = n*90deg CCW,
    Flip 1 = flip around horizontal (X) axis, Flip 2 = flip around vertical (Y) axis

    Returns a List with first item as rotation and second item as flip.

    https://bio3d.colorado.edu/SerialEM/betaHlp/html/about_properties.htm#per_camera_properties
    """
    conv = {
        0: [0, 0],
        1: [1, 0],
        2: [2, 0],
        3: [3, 0],
        4: [0, 1],
        5: [1, 2],
        6: [2, 2],
        7: [3, 2],
    }

    return conv[RotationAndFlip]


def check_defects(gainref: Path) -> Path | None:
    """Checks for a SerialEM-created defects file and -if found- returns file name."""
    defects_temp = []

    defects_temp.extend(gainref.parent.glob("defects*.txt"))

    if len(defects_temp) == 1:
        return defects_temp[0]

    elif len(defects_temp) > 1:
        print("Multiple defect files are found. Skipping defects correction.")
        return None

    else:
        return None


def defects_tif(gainref: Path, tempdir: Path, template: Path) -> Path | None:
    """Create Defect Map for MC2 from defects.txt.

    Input SerialEM gain reference, example frame and temporary directory.
    Requires a template file with the dimensions of the frames to be corrected.

    Returns path of the defects.tif
    """
    defects_txt: Path | None = check_defects(gainref)
    if defects_txt is None:
        return None
    defects_tif = Path(tempdir) / defects_txt.with_suffix(".tif")

    subprocess.run(["clip", "defect", "-D", defects_txt, template, defects_tif])
    print(f"Found and converted defects file {defects_tif}")
    return defects_tif
