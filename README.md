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
