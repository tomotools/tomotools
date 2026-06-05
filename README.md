# tomotools

Scripts to make cryo-electron tomography a bit easier

## Usage

**Full options can be listed via:**

```
tomotools --help
tomotools [subcommand] --help
```

## Currently supported subcommands:

### Preprocessing & Reconstruction:

- **blend-montages**: Blends SerialEM montages, write results to separate folder.
  - Example: `tomotools blend-montages MMM*.mrc montages-blended`
- **preprocess**: Prepare tiltseries for reconstruction.
  - Takes data directory from SerialEM or Tomo5 as input and writes the final stacks to the target directory.
  - Frames are aligned using MotionCor2 and reordered if desired. Supports GainRef conversion from dm4 to mrc and the SerialEM-generated defects.txt.
  - Example: `tomotools preprocess --mcbin 1 --gainref frames/GainRef.dm4 *.mrc ts-aligned`
- **reconstruct**: Perform batch reconstruction using AreTomo or imod.
  - Takes tiltseries and their associated mdoc files as input, automatically identified associated EVN/ODD stacks. Finds alignment using AreTomo, then applies it to EVN/ODD stacks. Alternatively, can move files and then open `etomo`. Reconstruction is done using imod's `tilt`.
  - Example: `tomotools reconstruct --move --bin 4 --sirt 12 --do-evn-odd *.mrc`

### Denoising & Deconvolution

- **deconv**: Python implementation of Dimitry Tegunov's _tom_deconv.m_ script.

### Subtomogram Averaging Preparation

- **imod2warp**: Takes a list of tomogram folder with alignments or a file listing them and prepares everything for Warp or WarpTools.
- **imod2tomotwin**: Takes a list of tomogram directories and reconstructs for TomoTwin picking.
- **fit-ctf**: Run imod ctfplotter on a set of tiltseries and save results to their folder.
- **reconstruct-3dctf**: Perform reconstruction using imods `ctf3d` function.

### Other

- **semnavigator**: Display SerialEM navigator files to find back you tomogram positions
- **create-movie**: Create a movie from a series of image files.
- **update**: Automatically pulls the most recent version from GitHub and runs `pip install --upgrade` on it.
- **restore-frames**: Restore SubFramePath to mdoc of tiltseries preprocessed with tomotools < 0.4.

## Dependencies

`tomotools` depends on commands from MotionCor2 or MotionCor3, IMOD, and AreTomo 1.X or AreTomo2 for full functionality. IMOD should be in PATH.
MotionCor2/3 and AreTomo2/3 can either be in PATH as `MotionCor2` / `MotionCor3` or `AreTomo` / `AreTomo2` respectively, or set using the envar `MOTIONCOR_EXECUTABLE` or `ARETOMO_EXECUTABLE`.

## Installation

We suggest installing tomotools into its own conda / mamba environment.
If you can only access your userspace, consider using [micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html).

```
conda create -n tomotools python=3.12
conda activate tomotools
pip install git+https://github.com/tomotools/tomotools.git
```

With tomotools installed into a conda environment, you can then start tomotools with:

```
conda activate tomotools
tomotools --help
```

### Notes on sbgrid:

If you're using an sbgrid environment, make sure to set the following in your `.sbgrid.conf` file:

```
PYTHON_X=3.8.8 (anything > 3.8 works)
```

Additionally, try `pip --version` to make sure it's correctly working. This is required for `tomotools update`. Else, you can add the following line to your `.bashrc`:

```
alias pip='python -m pip'
```

Likely, you will also need to add your local Python path to `.bashrc`:

```
export PATH="/YOURHOMEFOLDER/.local/bin:$PATH"
```

### Feedback, Bug Reports and Contributions are always welcome!
