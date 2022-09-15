# tomotools
Scripts to make cryo-electron tomography a bit easier

## Usage

> tomotools --help  
> tomotools [subcommand] --help

## Currently supported subcommands:

### Preprocessing and reconstruction
### Preprocessing & Reconstruction:
- **batch-prepare-tiltseries**: takes data directories from SerialEM including frames, mdocs, anchor files, .., aligns the tilt series using MotionCor2, reorders if desired. Supports PACEtomo output files. 
- **blend-montages**: blends SerialEM montages, writes results to separate folder.

### Postprocessing
- **reconstruct**: performs batch reconstruction using imod and/or AreTomo

### Denoising & Deconvolution
- **cryocare-extract**: extract subvolumes for cryoCARE
- **cryocare-train**: wrapper for cryoCARE training
- **cryocare-predict**: wrapper for cryoCARE prediction
- **deconv**: Python implementation of Dimitry Tegunov's tom_deconv.m script.

### Subtomogram Averaging
- **merge-dboxes**: Very beta, merges Dynamo DBoxes

### Other
- **create-movie**: Create a movie from a series of image files.
- **nff-to-amiramesh**

## Installation & Feedback

### Install via:
> git clone https://github.com/MoritzWM/tomotools.git  
> cd tomotools  
> pip install -e .

### Notes on sbgrid:
If you're using an sbgrid environment, make sure to set the following in your .sbgrid.conf file:

> PYTHON_X=3.8.8 (anything > 3.8 works)
> PRIISM_X=disable (replaces imod-native header command with an old version)
> ARETOMO_X=1.2.5_cu11.2 (or whatever CUDA version your GPUs support)

### Feedback, Bug Reports and Contributions are always welcome!