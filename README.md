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
  - Example: ```tomotools blend-montages MMM*.mrc montages-blended```
- **batch-prepare-tiltseries**: Prepare tiltseries for reconstruction.
  - Takes data directory from SerialEM as input and writes the final stacks to the target directory.
  - Frames are aligned using MotionCor2 and reordered if desired. Supports GainRef conversion from dm4 to mrc and the SerialEM-generated defects.txt.
  - Example: ```tomotools batch-prepare-tiltseries --mcbin 1 --gainref frames/GainRef.dm4 *.mrc ts-aligned```
- **reconstruct**: Perform batch reconstruction using AreTomo and imod.
  - Takes tiltseries and their associated mdoc files as input, automatically identified associated EVN/ODD stacks. Finds alignment using AreTomo, then applies it to EVN/ODD stacks. Reconstruction is done using imod's ```tilt```.
  - Example: ```tomotools reconstruct --move --bin 4 --sirt 12 --do-evn-odd *.mrc```

### Denoising & Deconvolution
- **cryocare-extract**: Extract cryoCARE training data from EVN/ODD reconstructions.
- **cryocare-train**: Wrapper for cryoCARE training.
- **cryocare-predict**: Wrapper for cryoCARE prediction.
- **deconv**: Python implementation of Dimitry Tegunov's _tom_deconv.m_ script.

### Subtomogram Averaging
- **tomotools2relion**: Takes a list of tiltseries or a file listing them and prepares everything for Relion4 import. Currently only works with AreTomo, ignores global alignment.
- **tomotools2warp**: Takes a list of tiltseries or a file listing them and prepares everything for Warp processing. Currently only works with imod.
- **project-particles**: Takes a Relion or Warp-generated .star file with (pseudo-)subtomograms. Performs projection along Z (optionally only central coordinates), generates files for Relion 2D classification (>3.1 style).
- **fit-ctf**: Run imod ctfplotter on a set of tiltseries and save results to their folder.
- **merge-dboxes**: Very beta, merges Dynamo DBoxes.

### Other
- **create-movie**: Create a movie from a series of image files.
- **nff-to-amiramesh**
- **update**: Automatically pulls the most recent version from GitHub and runs ```pip install --upgrade``` on it.

## Installation
We suggest installing tomotools into its own conda / mamba environment.

### Install via:
```
conda create -n tomotools python=3.8 cudatoolkit=11.0 cudnn=8.0 -c conda-forge
conda activate tomotools
pip install 'git+https://github.com/MoritzWM/tomotools.git'
```
With tomotools installed into a conda environment, you can then start tomotools with:
```
conda activate tomotools
tomotools --help
```
### Notes on sbgrid:
If you're using an sbgrid environment, make sure to set the following in your ```.sbgrid.conf``` file:

```
PYTHON_X=3.8.8 (anything > 3.8 works)  
```

### Feedback, Bug Reports and Contributions are always welcome!
