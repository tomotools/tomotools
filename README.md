# tomotools
Scripts to make cryo-electron tomography a bit easier

### Currently supported subcommands:

- **batch-prepare-tiltseries**: takes data directories from SerialEM including frames, mdocs, anchor files, .., aligns the tilt series using MotionCor2, reorders if desired. Supports PACEtomo output files. 
- **blend-montages**: blends SerialEM montages, writes results to separate folder.
- **create-movie**: Create a movie from a series of image files. 
- **cryocare-extract**
- **cryocare-predict**
- **cryocare-train**
- **merge-dboxes**: Very beta, merges Dynamo DBoxes
- **nff-to-amiramesh**
- **reconstruct**: performs batch reconstruction using imod and/or AreTomo

Full details:
> tomotools --help  
> tomotools [subcommand] --help

If you're using an sbgrid environment, make sure to set the following in your .sbgrid.conf file:

> PYTHON_X=3.8.8 (anything > 3.8 works)
> PRIISM_X=disable (replaces imod-native header command with an old version)
> ARETOMO_X=1.2.5_cu11.2 (or whatever CUDA version your GPUs support)
