# PACEtomo how-to
## A step-by-step guide for PACEtomo prep and acquisition.
> For PACEtomo v1.4.2, protocol version 231019
> Benedikt Wimmer, Medalia Lab, UZH
> Check the official documentation at https://github.com/eisfabian/PACEtomo

## A) Alignments
> I prefer to do all alignments on a carbon-coated mostly empty grid, i.e. without the Pt coating usually applied before FIB milling. I just have a clipped empty grid around which you can use many times.

1. Load carbon grid.
2. Go to eucentric height, perform all alignments as described in the general tilt-series protocol (section B). **Preferably use the NanoProbe mode** for record / trial / focus parameters in SerialEM.
3. In the *Low Dose* panel, make sure to set the focus offset to 0.
4. **Set the tilt axis offset for your target magnification** at *Tasks > Eucentricity > Offset*.
  - If you have not yet done so, measure it using the measure_offset.py script provided by PACEtomo. 
  - The output from the script is always relative to the set offset, so perform a few cycles of measure - set offset - measure - set offset until it converges on a value (± 0.1 µm). Write down the value for future use.
  - Make sure that *Center beam shift on tilt axis* is checked.
5. After all other alignments have been done, do the *Coma-vs-IS* alignment (*Focus > Coma vs. Image Shift*). 
   - This alignment sometimes fails because the beam hits a hole after being shifted. In this case, try a few different beam shift distances, I usually start with 10 µm. 
   - Closing SerialEM might delete this alignment, so make sure to keep it open.

## B) Map Lamellae and Add Targets

I use the following folder layout to keep my files in order:
```
your-data-folder/per-grid-folder/
./frames/
./LMM.mrc
./MMM_XX.mrc
./lamellaXX_tgt_001.mrc
etc.
```
1. Load the grid with your FIB lamellae.
  - Should be loaded with the milling direction perpendicular to the tilt axis, i.e. **cutout facing towards you** when loading. The better the loading, the better the acquisition.
2. **Find you lamella positions**. Either acquire an LMM (described in the tilt series protocol, section A), or find the lamella positions manually on the FloScreen. Either way, center the lamella manually on the FloScreen at the View magnification and add a *Navigator item* using the *Add Stage Position* button.
3. **Acquire MMM montages** for the lamellae, as described in the tilt series protocol, section B). Usually, a 3 x 3 montage at 65 00x can cover the entire lamella, if you keep "Move Stage" off and instead acquire with beam shift. Make sure to perform the *Rough Eucentricity* routine for each lamella when running *Acquire at Items*.
4. **Set frames directory.** To prevent chaos with the working directory of SerialEM, make sure to select the folder to which frames are saved before you run any of the target selection scripts.
   - Per convention, I save frames in the ```./frames``` subdirectory of the grid-specific data folder.
   - Save frames as LZW-compressed tiff with tiltAngle_Date_time as the name. On our K2, this adds up to < 1 GB per tiltseries, so indeed quite space-efficient!
   - Make sure to check "Save non-gain normalized" here.
   - Copy the gain reference file (the largest .dm4 file in C:/ProgramData/Gatan/Reference Images) and keep it with your frames. **Without it, your micrographs are useless.**
5. If you want, you can **pre-select targets for acquisition** on each lamella MMM:
   - Use *Add Points* in the Navigator panel. *Add Points* keeps the selection active until you click *Stop Adding*. 
   - All points added in one round will be considered a *group* internally in SerialEM and also by PACEtomo. 
   - **Make sure to select all targets which should be acquired in one run as one group.**
6. **A few considerations on how to distribute your targets into PACEtomo runs**:
  - The first position you select will also be used to track the sample movement. If you loose tracking here, it will be lost on all positions in this run. **Make sure to select a nice high-contrast feature here!**
  - On our first-generation Titan Krios, the maximum reliable beam shift seems to be ± 10 µm each in x and y from the tracking position.
  - Thus, to balance the risk of losing tracking and of exceeding the reliable beam shift, it might make sense to set up multiple PACEtomo runs per lamella, each with a smaller area and 5 - 10 targets.
7. **Check target selection script.** Select the first point of the group you added on the montage or just the montage item itself. *Go to XYZ*. Open the *PACEtomo_selectTargets.py* script. Make sure the following parameters are set:
```
targetByShift = False
targetPattern = False
alignToP = False
drawBeam = True
beamDiameter = 0
maxTilt = 69
useSearch = False
```
8. **Run the script and follow the prompts.**
  - I suggest using a root name which identified the lamella/montage (eg. montage01_areaA).
  - At the end of the run, you will get a window representing your target positions.
  - You can gain check all the relative beam shifts, see a list of the targets, export the tomogram positions as jpg with the context in place, skip some of them, ...
  - **Leave the window open for now!**
9. **Measure geometry**. To estimate how your areas of interest move during tilting, PACEtomo needs to know about the lamella orientation. There are two parameters, the *pre-rotation* and the *pre-tilt*.
  - *Pre-rotation* is a per-grid value and is 0° if the milling direction is perfectly perpendicular to the tilt axis. CW rotation is positive, CCW is negative.
  - *Pre-tilt* describes the tilt of the lamella (typically ± 8° - 12°).
  - Both can be determined using *PACEtomo_measureGeometry.py*:
    - With the target window still open, middle-click in the center to create a new point. 
    - **Make sure it falls on a decent region so that the defocus can accurately be estimated!** 
    - Add about 5 points (min. 3) in this way and click *Measure Geometry*. 
    - Check that the output values are reasonable and input them into the corresponding fields.
    - Then, set the starting tilt as the closest number divisible by 3 to -1 * pre-tilt (e.g. pre-tilt 8° -> starting tilt -9°).
    - Press *Save* to copy to targets file and close the window.
10. Repeat this procedure **for each group of target points** in your montages. The pre-rotation should be the same for all lamellae on the grid and the pre-tilt should be the same for all points on one lamella. PACEtomo will create a txt file containing all points and their relative positions and anchor maps. It will also automatically the the *Acquire* parameter in *Navigator*.

## C) Start Acquisition
1. Once *PACEtomo_selectTargets.py* was used to select all targets of interest, you are ready for acquisition. In the Navigator, you should see all acquisition location, but only the first point for each run should have the "Acquisition" checkmark (and the corresponding txt file in the notes section).
2. Make sure that *Realign to Item* works well. I have sometimes encountered a bug where it won't properly work unless you delete all maps (LMM and MMM) from then navigator - in this case, make sure to keep a backup "full" navigator via *Navigator > Save As*.
3. Quickly check that the beam is centered, dose rate and exposure time give you the desired dose and center the ZLP.
4. Open the *PACEtomo.py* script and check the following settings:
```
startTilt	= 0		# should be close to pre-tilt * -1 and divisible by step, eg. startTilt = 9 if pretilt = -9 (or -8...-10)
[...]
delayIS		= 0.5		# delay [s] between applying image shift and Record
delayTilt	= 1 		# delay [s] after stage tilt
[...]
# Geometry settings
pretilt		= 0		# put a "consensus" pre-tilt here and specify the precise values during target selection.
rotation	= 0		# put a "consensus" pre-rotation here and specify the precise values during target selection.
[...]
beamTiltComp	= True		# use beam tilt compensation (uses coma vs image shift calibrations)
[...]
previewAli	= True		# adds initial dose, but makes sure start tilt image is on target (uses view image and aligns to buffer P if alignToP == True)
```
You can also set a defocus range using ```minDefocus```, ```maxDefocus``` and ```stepDefocus```. If your lamella is very thick or the tracking feature is a bit vague, increase ```trackExpTime``` and ```trackDefocus``` so that accurate tracking is ensured!
5. Save the script. Go to *Navigator > Acquire at Items*. Select *Final Data*, and under action to run select the PACEtomo script. You can activate some microscope management features, such as checking for dewar refills and running automated buffer cycles, but everything else including *Realign to Item*, *Eucentricity* and *Autofocus* are anyway included in the script.
6. **Start the acquisition** and lean back!
7. **If anything goes wrong**, hit *Stop*.
  - You can re-run the *PACEtomo_selectTargets.py* script, which should find a *runfile*. You can then manage the acquisition, such as skipping certain areas etc.
  - To continue, just re-run the *PACEtomo.py* script, which should prompt you that it found *recovery files* to proceed with the acquisition.
  - If the stage was not moved between stopping and continuing, you do not need to re-track.
8. **Close and move your files.** You need the PACEtomo ```*_ts_***.mrc```, ```*_ts_***.mrc.mdoc```, the folder containing the frames and importantly the gain reference file. If SerialEM is configured correctly, it should also save the gain reference as ```*_CountRef.dm4``` into the frames folder, along with a ```*_defects.txt```file. You can now use ```tomotools batch-prepare-tiltseries --gainref *_CountRef.dm4 *.mrc ts-aligned``` to align the frames, correct them for gain and defect and write out reordered stacks to the ```ts-aligned``` directory.