# tomotools
Scripts to make cryo-electron tomography a bit easier

## Usage

```
tomotools --help
tomotools [subcommand] --help
```

## Currently supported subcommands:

### Preprocessing & Reconstruction:
- **batch-prepare-tiltseries**: takes data directories from SerialEM including frames, mdocs, anchor files, etc. Aligns the movies series using MotionCor2, reorders if desired. Supports GainRef conversion from dm4 and the SerialEM-generated defects.txt file. Can output EVN/ODD stacks.
- **blend-montages**: blends SerialEM montages, writes results to separate folder.
- **reconstruct**: performs batch reconstruction using AreTomo.

### Denoising & Deconvolution
- **cryocare-extract**: Extract subvolumes for cryoCARE.
- **cryocare-train**: Wrapper for cryoCARE training.
- **cryocare-predict**: Wrapper for cryoCARE prediction.
- **deconv**: Python implementation of Dimitry Tegunov's _tom_deconv.m_ script.

### Subtomogram Averaging
- **merge-dboxes**: Very beta, merges Dynamo DBoxes.

### Other
- **create-movie**: Create a movie from a series of image files.
- **nff-to-amiramesh**
- **update**: Automatically pulls the most recent version from GitHub and runs pip install --upgrade on it.

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
PRIISM_X=disable (replaces imod-native header command with an old version)
ARETOMO_X=1.2.5_cu11.2 (or whatever CUDA version your GPUs support)
```

### Feedback, Bug Reports and Contributions are always welcome!
