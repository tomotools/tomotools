# tomotools

Scripts to make cryo-electron tomography a bit easier

## Currently supported subcommands

- **batch-prepare-tiltseries**: takes data directories from SerialEM including frames, mdocs, anchor files, .., aligns the tilt series using MotionCor2, reorders if desired. Without frames, it just runs newstack to reorder or copies pre-ordered stacks to the output directory
- **blend-montages**: blends SerialEM montages, writes results to separate folder
- **create-movie**: creates a movie from a series of image files.
- **cryocare-extract**
- **cryocare-predict**
- **cryocare-train**
- **reconstruct**: performs batch reconstruction using imod and/or AreTomo
- **merge-dboxes**: very beta, merges Dynamo DBoxes (Dynamo itself can only merge regular data directories)
- **nff-to-amiramesh**

Full details:
> `tomotools --help`
> `tomotools [subcommand] --help`

## Installation

It's best to install tomotools into a clean virtualenv or conda environment.

### Virtualenv

For virtualenv you need to check that you have a relatively new python version installed, >=3.8 should be fine.

1. Create a python environment: `python3 -m venv venv`
2. Activate the environment: `source venv/bin/activate`
3. Install tomotools: `pip install --upgrade 'git+https://github.com/MoritzWM/tomotools.git@origin/main'`

If this fails, it might be that you are running an old python version (e.g. CentOS 8 uses python 3.6 by default).
Try removing the venv directory and starting over with e.g. `python3.9` instead of `python`

### Conda

1. Create a python environment: `conda create -n tomotools python=3.9`
2. Activate the environment: `conda activate tomotools`
3. Install tomotools: `pip install --upgrade 'git+https://github.com/MoritzWM/tomotools.git@origin/main'`

### SBGrid

If you're using an sbgrid environment, make sure to set the following in your .sbgrid.conf file:
```
> PYTHON_X=3.8.8 (anything > 3.8 works)  
> PRIISM_X=disable (replaces imod-native header command with an old version)  
> ARETOMO_X=1.2.5_cu11.2 (or whatever CUDA version your GPUs support)  
```
## Updating

There is a simple yet experimental auto-updating functionality.
Calling `tomotools update` should update you to the latest version automatically.
Please report back if this doesn't work.

