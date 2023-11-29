import csv
import os
import shutil
import subprocess
from glob import glob
from operator import itemgetter
from os import path
from pathlib import Path
from typing import List, Optional

import mrcfile
import pandas as pd

from tomotools.utils import mdocfile, util
from tomotools.utils.micrograph import Micrograph


class TiltSeries:
    """Class for TiltSeries."""

    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        self.path: Path = path
        self.mdoc: Path = Path(f"{path}.mdoc")
        self.is_split: bool = False
        self.evn_path: Optional[Path] = None
        self.odd_path: Optional[Path] = None

    def with_split_files(self, evn_file: Path, odd_file: Path) -> "TiltSeries":
        """Create TiltSeries with EVN/ODD by giving their paths."""
        if not evn_file.is_file():
            raise FileNotFoundError(f"File not found: {evn_file}")
        if not odd_file.is_file():
            raise FileNotFoundError(f"File not found: {odd_file}")
        self.evn_path = evn_file
        self.odd_path = odd_file
        self.is_split = True
        return self

    def with_split_dir(self, dir: Path) -> "TiltSeries":
        """Create TiltSeries with EVN/ODD by giving their parent directory."""
        if not dir.is_dir():
            raise NotADirectoryError(f"{dir} is not a directory!")
        stem = self.path.stem
        suffix = self.path.suffix
        evn_file = dir.joinpath(f"{stem}_EVN{suffix}")
        odd_file = dir.joinpath(f"{stem}_ODD{suffix}")
        return self.with_split_files(evn_file, odd_file)

    def with_mdoc(self, file: Path):
        """Explicitely use this mdoc file."""
        self.mdoc: Path = file
        return self

    def delete_files(self, delete_mdoc=True):
        """Delete all files associated with TiltSeries.

        Deletion of mdoc optional.
        """
        for file in [
            self.path,
            self.evn_path,
            self.odd_path,
            self.mdoc if delete_mdoc else None,
        ]:
            if file is not None and file.is_file():
                file.unlink()

    def defocus_file(self):
        """Return path of defocus file from ctfplotter."""
        if path.exists(self.path.with_name(f'{self.path.stem}_ctfplotter.txt')):
            return self.path.with_name(f'{self.path.stem}_ctfplotter.txt')
        elif path.exists(self.path.with_name(f'{self.path.stem}.defocus')):
            return self.path.with_name(f'{self.path.stem}.defocus')
        else:
            return None

    @staticmethod
    def _update_mrc_header_from_mdoc(path: Path, mdoc: dict):
        with mrcfile.mmap(path, "r+") as mrc:
            # Copy the first 10 titles into the newly created mrc
            mrc.update_header_from_data()
            mrc.update_header_stats()
            for i in range(10):
                title = mdoc["titles"][i].encode() if i < len(mdoc["titles"]) else b""
                mrc.header["label"][i] = title
            mrc.header["nlabl"] = len(mdoc["titles"])
            mrc.voxel_size = mdoc["sections"][0]["PixelSpacing"]

    @staticmethod
    def _update_mdoc_from_mrc_header(path: Path, mdoc: dict):
        with mrcfile.mmap(path, "r+") as mrc:
            # Copy over some global information from the first section into the mdoc
            mdoc["PixelSpacing"] = mdoc["sections"][0]["PixelSpacing"]
            mdoc["ImageFile"] = path.name
            mdoc["ImageSize"] = [mrc.header["nx"].item(), mrc.header["ny"].item()]
            mdoc["DataMode"] = mrc.header["mode"].item()

    @staticmethod
    def from_micrographs(
        micrographs: List[Micrograph],
        ts_path: Path,
        orig_mdoc_path: Optional[Path] = None,
        reorder=False,
        overwrite_titles: Optional[List[str]] = None,
    ) -> "TiltSeries":
        """Create TiltSeries from Micrographs, aka run newstack."""
        # TODO: Possibly remove overwrite_titles
        # TODO: Reduce complexity C901.
        if ts_path.exists():
            raise FileExistsError(f"File at {ts_path} already exists!")
        if reorder:
            micrographs = sorted(
                micrographs, key=lambda micrograph: micrograph.tilt_angle
            )

        # First, take care of the MDOC files
        if all(micrograph.mdoc for micrograph in micrographs):
            # If all movies have their own associated mdoc, merge the mdoc files
            stack_mdoc = {"titles": [], "sections": [], "framesets": []}
            for micrograph in micrographs:
                mdoc = micrograph.mdoc
                stack_mdoc["titles"] = mdoc["titles"]
                stack_mdoc["sections"].append(mdoc["framesets"][0])
                # Copy global vars, so again only the last values are kept
                for key, value in mdoc.items():
                    if key not in ("framesets", "titles", "sections"):
                        stack_mdoc[key] = value

            # Merging the titles is too difficult, just keep last one.
            if overwrite_titles is not None:
                # Update titles and append frameset as new section
                stack_mdoc["titles"] = overwrite_titles

        elif orig_mdoc_path is not None:
            stack_mdoc = mdocfile.read(orig_mdoc_path)
            if reorder:
                stack_mdoc["sections"] = sorted(
                    stack_mdoc["sections"], key=itemgetter("TiltAngle")
                )

        else:
            raise FileNotFoundError(
                "No original MDOC was provided and the movies don't have MDOCs!"
            )

        # Now, create the TiltSeries files
        micrograph_paths = [str(micrograph.path) for micrograph in micrographs]
        subprocess.run(["newstack"] + micrograph_paths + [ts_path, "-quiet"])

        # Remove MRC header and MDOC, remove unnecessary entries
        TiltSeries._update_mrc_header_from_mdoc(ts_path, stack_mdoc)
        TiltSeries._update_mdoc_from_mrc_header(ts_path, stack_mdoc)
        for section in stack_mdoc["sections"]:
            for key in ("SubFramePath", "NumSubFrames", "FrameDosesAndNumber"):
                if key in section:
                    del section[key]
        mdocfile.write(stack_mdoc, str(ts_path) + '.mdoc')

        if all(micrograph.is_split for micrograph in micrographs):
            micrograph_evn_paths = [str(micrograph.evn_path)
                                    for micrograph in micrographs]
            micrograph_odd_paths = [str(micrograph.odd_path)
                                    for micrograph in micrographs]
            ts_evn = ts_path.with_name(ts_path.stem + '_even.mrc')
            ts_odd = ts_path.with_name(ts_path.stem + '_odd.mrc')
            subprocess.run(['newstack'] + micrograph_evn_paths + [ts_evn, '-quiet'])
            subprocess.run(['newstack'] + micrograph_odd_paths + [ts_odd, '-quiet'])

            TiltSeries._update_mrc_header_from_mdoc(ts_evn, stack_mdoc)
            TiltSeries._update_mrc_header_from_mdoc(ts_odd, stack_mdoc)
            return TiltSeries(ts_path).with_split_files(ts_evn, ts_odd)
        else:
            return TiltSeries(ts_path)


def aretomo_executable() -> Optional[str]:
    """Return AreTomo executable.

    Path can be set with one of the following ways (in order of priority):
    1. Setting the ARETOMO_EXECUTABLE variable to the full path of the executable
    2. Putting the appropriate executable into the PATH and renaming it to "aretomo"
    """
    if "ARETOMO_EXECUTABLE" in os.environ:
        aretomo_exe = os.environ["ARETOMO_EXECUTABLE"]
        if path.isfile(aretomo_exe):
            return aretomo_exe
        else:
            raise FileNotFoundError(
                f'Variable for AreTomo is set to "{aretomo_exe}", but file is missing.'
            )
    return shutil.which("AreTomo")


def align_with_areTomo(
    ts: TiltSeries, local: bool, previous: bool, do_evn_odd: bool, gpu: str
):
    """Takes a TiltSeries as input and runs AreTomo on it.

    Optional: do local alignment.

    If previous is True, respect previous alignment in folder.

    If do_evn_odd is passed, also perform alignment on half-stacks.

    Will apply the pixel size from the input stack to the output stack.
    """
    ali_stack = ts.path.with_name(f"{ts.path.stem}_ali.mrc")
    aln_file = ts.path.with_suffix(".aln")
    orig_mdoc = ts.mdoc

    if gpu is None:
        gpu_id = [int(i) for i in range(0,util.num_gpus())]

    else:
        # Turn GPU list into list of integers
        gpu_id = gpu.split(",")
        gpu_id = [int(gpu) for gpu in gpu_id]

    with mrcfile.mmap(ts.path) as mrc:
        angpix = float(mrc.voxel_size.x)

    tlt_file = ts.path.with_suffix('.tlt')

    if not path.isfile(tlt_file):
        subprocess.run(['extracttilts', ts.path, tlt_file],
                       stdout=subprocess.DEVNULL)

    if previous:
        if not path.isfile(aln_file):
            raise FileNotFoundError(
                f'{ts.path}: --previous was passed, but no alignment at {aln_file}.')

        subprocess.run([aretomo_executable(),
                        '-InMrc', ts.path,
                        '-OutMrc', ali_stack,
                        '-AngFile', tlt_file,
                        '-AlnFile', aln_file,
                        '-VolZ', '0'],
                       stdout=subprocess.DEVNULL)

    if not previous:
        mdoc = mdocfile.read(ts.mdoc)
        full_dimensions = mdoc['ImageSize']
        patch_x, patch_y = [str(round(full_dimensions[0] / 1000)),
                            str(round(full_dimensions[1] / 1000))]
        alignZ = str(round(1500 / angpix))

        pretilt = -1 * round(mdocfile.get_start_tilt(mdoc))

        subprocess.run([aretomo_executable(),
                        '-InMrc', ts.path,
                        '-OutMrc', ali_stack,
                        '-AngFile', tlt_file,
                        '-VolZ', '0',
                        '-TiltCor', f'0 {pretilt}',
                        '-AlignZ', alignZ] +
                       (['-Gpu'] + [str(i) for i in gpu_id]) +
                       (['-Patch', patch_x, patch_y] if local else []),
                       stdout=subprocess.DEVNULL)

    with mrcfile.mmap(ali_stack, mode="r+") as mrc:
        mrc.voxel_size = str(angpix)
        mrc.update_header_stats()

    print(f'Done aligning {ts.path.stem} with AreTomo.')

    if not path.isfile(ali_stack.with_suffix('.tlt')):

        aln_to_tlt(aln_file)

    if do_evn_odd and ts.is_split:
        ali_stack_evn = ts.evn_path.with_name(f"{ts.path.stem}_ali_EVN.mrc")
        ali_stack_odd = ts.odd_path.with_name(f"{ts.path.stem}_ali_ODD.mrc")
        subprocess.run(
            [
                aretomo_executable(),
                "-InMrc",
                ts.evn_path,
                "-OutMrc",
                ali_stack_evn,
                "-AngFile",
                tlt_file,
                "-AlnFile",
                aln_file,
                "-VolZ",
                "0",
            ],
            stdout=subprocess.DEVNULL,
        )

        subprocess.run(
            [
                aretomo_executable(),
                "-InMrc",
                ts.odd_path,
                "-OutMrc",
                ali_stack_odd,
                "-AngFile",
                tlt_file,
                "-AlnFile",
                aln_file,
                "-VolZ",
                "0",
            ],
            stdout=subprocess.DEVNULL,
        )
        with mrcfile.mmap(ali_stack_evn, mode="r+") as mrc:
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()

        with mrcfile.mmap(ali_stack_odd, mode="r+") as mrc:
            mrc.voxel_size = str(angpix)
            mrc.update_header_stats()

        try:
            os.remove(ali_stack_evn.with_name(f"{ali_stack_evn.stem}.tlt"))
            os.remove(ali_stack_odd.with_name(f"{ali_stack_odd.stem}.tlt"))
        finally:
            print(f"Done aligning ENV and ODD stacks for {ts.path.stem} with AreTomo.")
            return (
                TiltSeries(ali_stack)
                .with_split_files(ali_stack_evn, ali_stack_odd)
                .with_mdoc(orig_mdoc)
            )

    return TiltSeries(ali_stack).with_mdoc(orig_mdoc)


def dose_filter(ts: TiltSeries, do_evn_odd: bool) -> TiltSeries:
    """Runs mtffilter on the given TiltSeries object.

    Uses the doses in the associated mdoc file.
    Will take into account EVN/ODD stacks if do_evn_odd is passed.
    mdoc needs to contain only ExposureDose, as PriorRecordDose is deduced by mtffilter
    based on the DateTime entry, see mtffilter -help, section "-dtype"
    """
    mdoc = mdocfile.read(ts.mdoc)

    if any(section["ExposureDose"] == 0 for section in mdoc["sections"]):
        print(f"{ts.mdoc} has no ExposureDose set. Skipping dose-filtration.")
        return ts
    else:
        orig_mdoc = ts.mdoc
        filtered_stack = ts.path.with_name(f"{ts.path.stem}_filtered.mrc")
        subprocess.run(
            ["mtffilter", "-dtype", "4", "-dfile", ts.mdoc, ts.path, filtered_stack],
            stdout=subprocess.DEVNULL,
        )

        if ts.is_split and do_evn_odd:
            filtered_evn = ts.path.with_name(f"{ts.path.stem}_filtered_EVN.mrc")
            filtered_odd = ts.path.with_name(f"{ts.path.stem}_filtered_ODD.mrc")

            subprocess.run(
                [
                    "mtffilter",
                    "-dtype",
                    "4",
                    "-dfile",
                    ts.mdoc,
                    ts.evn_path,
                    filtered_evn,
                ],
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    "mtffilter",
                    "-dtype",
                    "4",
                    "-dfile",
                    ts.mdoc,
                    ts.odd_path,
                    filtered_odd,
                ],
                stdout=subprocess.DEVNULL,
            )

            print(f"Done dose-filtering {ts.path} and EVN/ODD stacks.")
            return (
                TiltSeries(filtered_stack)
                .with_split_files(filtered_evn, filtered_odd)
                .with_mdoc(orig_mdoc)
            )

        print(f"Done dose-filtering {ts.path}.")
        return TiltSeries(filtered_stack).with_mdoc(orig_mdoc)


def align_with_imod(ts: TiltSeries, previous: bool, do_evn_odd: bool):
    """Aligns given TiltSeries with imod.

    If previous is passed, use .xf and .tlt file from previous alignment
    and just calculate a new stack, if desired with EVN/ODD.

    "De-novo" batch alignment still needs to be implemented...
    """
    orig_mdoc = ts.mdoc

    if previous:
        # Generate new stack with alignment files
        if not path.isfile(ts.path.with_suffix('.xf')):
            raise FileNotFoundError(
                f'--previous passed, but file {ts.path.with_suffix(".xf")} not found! ')

        ali_stack = ts.path.with_name(f'{ts.path.stem}_ali.mrc')

        # Copy the imod-generated tlt-file to _ali.tlt
        shutil.copyfile(ts.path.with_suffix('.tlt'), ali_stack.with_suffix('.tlt'))

        subprocess.run(['newstack',
                        '-InputFile', ts.path,
                        '-OutputFile', ali_stack,
                        '-TransformFile', ts.path.with_suffix('.xf'),
                        '-TaperAtFill', '1,1',
                        '-AdjustOrigin'],
                       stdout=subprocess.DEVNULL)

        if do_evn_odd:
            ali_stack_evn = ts.evn_path.with_name(f'{ts.path.stem}_ali_even.mrc')
            ali_stack_odd = ts.odd_path.with_name(f'{ts.path.stem}_ali_odd.mrc')

            subprocess.run(['newstack',
                            '-InputFile', ts.evn_path,
                            '-OutputFile', ali_stack_evn,
                            '-TransformFile', ts.path.with_suffix('.xf'),
                            '-TaperAtFill', '1,1',
                            '-AdjustOrigin'],
                           stdout=subprocess.DEVNULL)

            subprocess.run(['newstack',
                            '-InputFile', ts.odd_path,
                            '-OutputFile', ali_stack_odd,
                            '-TransformFile', ts.path.with_suffix('.xf'),
                            '-TaperAtFill', '1,1',
                            '-AdjustOrigin'],
                           stdout=subprocess.DEVNULL)
            print(f'Aligned {ts.path} and associated EVN/ODD stacks with imod.')
            return TiltSeries(ali_stack).with_split_files(ali_stack_evn, ali_stack_odd).with_mdoc(orig_mdoc) #noqa: E501

        print(f'Finished aligning {ts.path} with imod.')
        return TiltSeries(ali_stack).with_mdoc(orig_mdoc)

    elif not previous:
        # TODO: implement batch alignment with imod adoc here!
        raise NotImplementedError("Only --previous is supported for imod so far.")


def aln_to_tlt(aln_file: Path):
    """Generate imod-compatible tlt file from AreTomo-generated aln file."""
    tilts = []

    with open(aln_file) as f:
        reader = csv.reader(f, delimiter=" ")
        for row in reader:
            if row[0].startswith("#"):
                pass
            else:
                row_cleaned = [entry for i, entry in enumerate(row) if entry != ""]
                (sec, rot, gmag, tx, ty, smean, sfit, scale, base, tilt) = row_cleaned
                tilts.append(tilt)

    tlt_out = aln_file.with_name(f"{aln_file.stem}_ali.tlt")

    with open(tlt_out, mode="w+") as f:
        f.write("\n".join(tilts))

    return tlt_out


def run_ctfplotter(ts: TiltSeries, overwrite: bool):
    """Run imod ctfplotter on given TiltSeries object.

    Returns path to defocus file.
    """
    if ts.defocus_file() is None or overwrite:
        with mrcfile.mmap(ts.path) as mrc:
            nmpix = str(float(mrc.voxel_size.x) / 10)
            header = str(mrc.header)
            header = header.split('Tilt axis angle = ', 1)
            axis_angle = header[1][0:4]

        mdoc = mdocfile.read(ts.mdoc)
        expected_defocus = str(abs(mdoc['sections'][0]['TargetDefocus']) * 1000)

        kV = 300
        cs = 2.7

        with open(path.join(ts.path.parent, 'ctfplotter.log'), 'a') as out:
            subprocess.run(['ctfplotter',
                            '-InputStack', ts.path,
                            '-angleFn', ts.path.with_suffix('.tlt'),
                            '-defFn', ts.path.with_name(f'{ts.path.stem}.defocus'),
                            '-pixelSize', nmpix,
                            '-crop', '0.3',
                            '-volt', str(kV),
                            '-cs', str(cs),
                            '-am', str(0.07),
                            '-degPhase', str(0),
                            '-AxisAngle', axis_angle,
                            '-expDef', expected_defocus,
                            '-autoFit', '3,1'],
                           stdout=out)

    return ts.path.with_name(f'{ts.path.stem}.defocus')

def parse_ctfplotter(file: Path):
    """Takes path to ctfplotter output. Returns pandas dataframe."""
    df_file = pd.DataFrame({'view_start': [],
                            'view_end': [],
                            'tilt_start': [],
                            'tilt_end': [],
                            'df_1_nm': [],
                            'df_2_nm': [],
                            'astig_ang': []}, dtype = int)

    with open(file) as f:
        reader = csv.reader(f, delimiter = '\t')
        for row in reader:
            if row[1] == '0':
                pass
            else:
                df_temp = pd.DataFrame({'view_start': [row[0]],
                                        'view_end': [row[1]],
                                        'tilt_start': [row[2]],
                                        'tilt_end': [row[3]],
                                        'df_1_nm': [row[4]],
                                        'df_2_nm': [row[5]],
                                        'astig_ang': [row[6]]})
                df_file = pd.concat([df_file,df_temp])

    return df_file

def write_ctfplotter(df: pd.DataFrame(), file: Path):
    """Writes Pandas dataframe as ctfplotter file."""
    # Somehow this header is present in ctfplotter files, so also add here.
    header = pd.DataFrame(['1', '0', '0.0', '0.0', '0.0', '3']).T

    temp_header = header.to_csv(sep="\t", header = False, index=False)
    temp = df.to_csv(sep="\t", header = False, index=False)

    with open(file, 'w+') as f:
        f.write(temp_header + temp + "\n")

    return file

def parse_darkimgs(ts: TiltSeries):
    """Parses AreTomo-generated _DarkImgs.txt.

    Returns list of excluded tilts (Zero-Indexed)

    If _DarkImgs is not found, check in the .aln file (as of version 1.3).
    """
    dark_tilts = []

    dark_txt = ts.path.with_name(f'{ts.path.stem}_DarkImgs.txt')
    aln_file = ts.path.with_suffix('.aln')

    if path.isfile(dark_txt):
        with open(dark_txt) as txt:
            for line in txt:
                if line.startswith('#'):
                    pass
                else:
                    line = line.strip()
                    dark_tilts.append(int(line))

    else:
        with open(aln_file) as f:
            reader = csv.reader(f, delimiter=' ')
            for row in reader:

                if row[1].startswith('Local'):
                    break
                elif row[1].startswith('DarkFrame'):
                    row_cleaned = [entry for i, entry in enumerate(row) if entry != '']
                    (no, title, equal, view, view2, ang) = row_cleaned
                    dark_tilts.append(int(view))
                else:
                    pass

    return dark_tilts


def convert_input_to_TiltSeries(input_files:[]):
    """Takes list of input files or folders from Click.

    Returns list of TiltSeries objects with or without split frames.
    If a folder is given, identify it by corresponding mdoc file.
    """
    return_list = []

    # Append all files with mdoc (weird heuristic, but it works)
    # except those generated from allviews and cutviews, which are generated by imod
    for input_file in input_files:
        input_file = Path(input_file)
        if input_file.is_file():
            if (not input_file.name.endswith('.st') or
                     input_file.name.endswith('.mrc')):
                continue
            if (input_file.name.endswith('_EVN.mrc') or
                input_file.name.endswith('_ODD.mrc') or
                input_file.name.endswith('_even.mrc') or
                input_file.name.endswith('_odd.mrc')):
                continue

            return_list.append(TiltSeries(Path(input_file)))

        elif input_file.is_dir():
            return_list += ([TiltSeries(Path(Path(file).with_suffix('')))
                             for file in list(set(glob(path.join(input_file, '*.mdoc')))- #noqa: E501
                                              set(glob(path.join(input_file,'*allviews*.mdoc')))-
                                              set(glob(path.join(input_file,'*cutviews*.mdoc')))
                                              )])

    for file in return_list:
        if (path.isfile(file.path.with_name(f'{file.path.stem}_EVN.mrc')) and
            path.isfile(file.path.with_name(f'{file.path.stem}_ODD.mrc'))):
            file = file.with_split_files(file.path.with_name(f'{file.path.stem}_EVN.mrc'), #noqa: E501
                                         file.path.with_name(f'{file.path.stem}_ODD.mrc'))

        elif (path.isfile(file.path.with_name(f'{file.path.stem}_even.mrc')) and
              path.isfile(file.path.with_name(f'{file.path.stem}_odd.mrc'))):
            file = file.with_split_files(file.path.with_name(f'{file.path.stem}_even.mrc'), #noqa: E501
                                         file.path.with_name(f'{file.path.stem}_odd.mrc'))

        if file.is_split:
            print(f'Found TiltSeries {file.path} with EVN and ODD stacks.')
        else:
            print(f'Found TiltSeries {file.path}.')

    return return_list
