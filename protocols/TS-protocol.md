# Tilt Series Acquisition

> Benedikt Wimmer, Medalia Lab, UZH - Version 240911

### This Protocol covers:

A) Mapping all grids in Autoloader at low magnification with SerialEM.
B) Direct Alignments of the Titan Krios scope.
C) Automated square mapping.
D) Set-up of Tilt Series acquisition including frame alignment with SEMCCD.

## Acquisition Parameters

This protocol uses the following parameter sets in SerialEM, but adapt according to your needs. Some good magnification / spot size / illuminated area settings for our Titan Krios G1 / K2 system are given in the end of the protocol.

All images should be acquired in counting mode. 

| Parameter Set         | Search    | View    | Record      | Focus         | Trial         | Preview       |
|-----------------------|-----------|---------|-------------|---------------|---------------|---------------|
| Use                   |For Atlas |For MMM |             |               |               |               |
|                       |           |         |             |               |               |               |
| Magnification         | 175x      | 4,800x  | 64,000x     | 64,000x       | 64,000x       | 64,000x       |
| C2 Aperture           | 70        | 50      | 50          | 50            | 50            | 50            |
| Spot Size             | 7         | 7       | 7 nP        | 7 nP          | 7 nP          | 7 nP          |
| Illuminated Area [µm] |           | 40      | 1.75        | 1.75          | 1.75          | 1.75          |
| Objective Aperture    | out       | 100     | 100         | 100           | 100           | 100           |
|                       |           |         |             |               |               |               |
| GIF Slit Width [eV]   | 50        | 20      | 20          | 20            | 20            | 20            |
| Flux on sample [e/px/s]         | 20        | 25      | 8 - 10      | 8 - 10        | 8 - 10        | 8 - 10        |
| Defocus [µm]          | -160      | -80     | -4          | -4            | -4            | -4            |
| Exposure Time [s]     | 1         | 1       | **calibrate** | 50% of Record | 50% of Record | 30% of Record |
| Image binned          | 2         | 1       | 1           | 4             | 2             | 2             |

## A) Automated Mapping of Entire Grids.

1. **Load samples.** Dock NanoCab, initialize Autoloader if needed. Click "Edit Slot State", define for all cassette positions (click 1x for occupied, 2x for empty). Run inventory for at least all occupied positions and one empty position.
2. **Prepare Settings**. Switch Turbo pump to "always on". Without grid on column, quickly set the microscope settings, save to FEG register.
3. **Set up session.** Start SerialEM, load your settings or create new ones with parameters above. Make sure *Low Dose* is active. Acquire *Search* to see whether sample is there. 
4. *Open Navigator* and Select *Navigator > Montaging & Grids > Set-up Full Montage.* Use the following settings:
```
Magnification 175x
Bin 2
Overlap 10%
Use Search parameters
Use Continuous mode
Move Stage
```
- Save as LMM.mrc to grid-specific folder or screening folder.

5. **Start acquisition.** The grid overview can either be done for all grids at once **(option 1)** or for each grid individually **(option 2)**. Use the first to get a general overview of your samples, use the second to guide acquisition of a specific grid.
   1. **Map all grids:** In SerialEM, go so *Script > Edit* to edit script *mapgrids* (currently at Pos. 2, or download from SerialEM script repository). Start script. This takes 10 - 15 min per grid.
      - **Check results** by going through maps in Navigator. In *Montage Controls*, select bin 2 for overview and check *treat as a very sloppy montage* if stitching is not satisfactory. For each grid you'll continue with, start a new folder and Navigator file, otherwise it is very messy!
   2. **Atlas to guide acquisition:** Load your grid. In SerialEM, make sure that *Tasks > Eucentricity > Rough use Search if LM* is checked. Run *Eucentric Rough*. Then, in the *Montage Control* panel on the left, select *Start.* 
      - After acquisition, select the map and check *Rotate when load* in Navigator to match rotation in SA mode.
6. **Clean-up.** Switch Turbo pump to "auto off". Save Navigator.

## B) Microscope Alignments

> A good primer can be found in Christos Savvas Lecture at MRC-LMB:\
> https://youtu.be/9AMSabcTN24
> A good introduction to the terminology is in Grant Jensens YouTube lecture:\
> https://youtu.be/hc2s4uSbpyI

```
MX / MY stand for Multifunction X / Y keys.
DM is Digital Micrograph.
```
Alignments start with **no objective lens.**
1. **Prepare gain reference (after cryo-cycle or K2 restart)**:
   - Go to empty square on the grid. Insert FloScreen. Go to record magnification.
   - **Make sure that K2 is in linear mode**
   - Adapt your imaging settings to reach a high flux of approx. 500 counts/px/s (bottom right corner of DM). E.g. for 81kx, C2 50, Spot size 2, illuminated area ca. 2 µm, nanoprobe mode works, but larger C2 aperture may help. 
   - Click *Camera > Prepare Gain Reference*. If *Camera* is not visible, go to *Help > User Mode > Power User*. Accept default settings. 
   - A view is started which shows the read counts. Adjust illuminated area, until these are around 500 (within 1%). Click ok to prepare linear mode reference.
   - **After this, click yes to prepare a counting mode reference. Do not dismiss the warning message!**
   - First, go back to usual record settings (C2, Spot, IA). Check settings on screen before continuing. 
   - Now, acquire counting mode gain reference. After acquisition is done, check gain reference looks good (does not contain any fringes etc.).
2. **Tune Energy Filter (monthly or if unstable)**.
   - Make sure K2 is in linear mode. Insert FloScreen. Make sure that you are in an empty area (no carbon, no sample). Go to high-beam settings from Step 1.
   - Press *Normalize all lenses* (= L2), press *eucentric focus*. Adjust beam shift if needed with track ball. 
   - Check magnetic field compensator (next to door). Values should be close to zero (< 0.01). Otherwise, reset it. 
   - Adjust illuminated area so beam is parallel (can be checked in *beam settings*) and counts are around 500 e/px/s.
   - On the left side, select *Tune GIF*. Perform a *full tune*. 
   - Make sure all steps are completed, otherwise perform them individually using the *quick tune* setting. 
   - Often, *Distortion tuning* will give an error message. Select *undo* and perform *XY Magnification* tuning instead. 
   - After tuning is completed, center the ZLP. DM can hold on to calibrations for different magnifications, so it might be useful to repeat this at *View* magnification.
3. Bring back the desired imaging parameters. Go to a carbon region where you don't want to acquire data. Use *Tasks > Eucentric rough* to go to eucentric height. Go to very low defocus (eg. autofocus to -2 µm). **Insert the Screen**, select *Record* settings, make sure that **continuous update** is checked.
4. **[If beam is very weak]** Adjust gun tilt and shift. Under *Direct Alignments*, adjust gun tilt and gun shift with MX and MY keys. Optimize for a high electron flux (high exposure dose or screen current, low exposure time).
5. **[If beam behaves weird during focusing]** Align C2 aperture. First, go to *Beam settings > Flip-out Menu > Free Ctrl. > C3 off*. Go to crossover point (beam as small as possible). **This has to be done on the FloScreen!** Center beam using trackball. Expand beam (turn "Intensity" knob clockwise). If beam is not centered, activate *C2 adjustments*, move to center with MX and MY. Check several times. Inactivate *C2 adjustments*, go back to *TEM mode*.
6. **[If re-doing C2 alignment]** Adjust C2 stigmator. Go to Spot size that will be used for data collection (e.g. 7 nP). Go to record magnification (e.g. 64,000 x). Check whether spot is circular. Otherwise, go to *Stigmator > C2*, modify using MX and MY.
7. **Direct Alignments (beginning of session)**. Go to record settings (spot size and illumination mode, focus, magnification, EFTEM mode). Make sure you're at eucentric height. Focus on the carbon with a very low defocus (e.g. -2 µm). 
   - If SerialEM is not available, you can focus manually: Open DM and activate the Live View. Display Live FFT. *Mind the exposure rate!* Focus on the Carbon area (First zero of the Thon rings should be at the edges.).
   - *Direct Alignments* can now be performed on the FloScreen. The workflow is top to bottom. Use MX and MY keys. Start after gun tilt / shift.
    - For *Pivot Points*, preferentially use MX (fine adjustments) to reduce motion of the beam as much as possible.
    - For *Beam shift*, center the beam on GIF (green circle on Screen view).
    - *C2 aperture* can be skipped here if already done above.
    - *Condenser center TEM* aligns the C3 aperture but can be skipped for most purposes.
    - *Rotation Center* is a critical prerequisite for good coma-free alignment. Assuming that you are using the nanoprobe mode of the microscope, try to reduce motion of the beam on the FloScreen as much as possible with MX and MY. 
    - Once done, save settings as *FEG register* and apply them as *Record*/*Tracking*/*Focus* settings in the SerialEM low-dose panel.
8. **Coma-Free adjustments (daily).** The easiest way to do Coma-Free alignment is in SerialEM. Make sure that the *Record* setting is giving an image. Go to a nice carbon area. Then use *Focus/Tune > Coma-free Alignment by CTF*. If selecting *Process > Live FFT / Side-by-Side*, you can check the CTF fit.
   - For manual coma-free alignment, open DM. Start Live View and Live FFT. On the microscope PC, under *Direct Adjustments*, select Coma-free alignments. Check that the alternating FFTs overlap, otherwise use MX until they do. Go back and forth between X and Y.
9. **Center Objective Aperture (daily).** Insert screen. Insert Objective aperture. Go to diffraction mode, you should see a bright spot with some Thon rings around it if you're on Carbon. You might need to change the sensitivity of the FloScreen camera. By clicking the FloScreen window and scrolling, you can adjust brightness and contrast, until you can clearly see the outline of the aperture as a black circle around the beam. Select *Adjust Objective aperture* and use MX and MY to center the aperture around the beam.
10. **Objective Lens astigmatism (daily).** Again, the easiest way to do this is in SerialEM. Check that *Preview* yields a good image of a carbon area. Select *Focus/Tune > Correct Astigmatism by CTF*. If it is greyed out, activate by first going to *Calibration > Focus & Tuning > Astigmatism by CTF*. Once run, it adjusts the Objective lens stigmator by the values it specifies.
    - To adapt this manually, go to DM, acquire a dose fractionated image with a long exposure (e.g. 10s in 0.1s increments) at a very high magnification (eg. 270,000x). Use *Image Processing / Measure Drift / Remove Drift* to correct for motion. Then, add exposures using *Volume > Project Z*. Look at the power spectrum through *Process > FFT*. Rings should be exactly concentric and round.
11. **Save settings** to a *FEG Register*. Save settings in SerialEM, copy to *Focus* and *Trial*, and uncheck *continuous update*.

## C) Prepare maps of grid squares

1. **Check beam.** Make sure you are close to eucentric height, especially if you did not acquire the LMM at eucentricity. Check that the alignment for the *View* mode is good by inserting screen. If needed, adjust beam shift:
  - Check *Set additional beam shift*. Shift beam via Trackball. Uncheck *additional beam shift*. Save settings.
2. **Match Atlas shift.** If LMM acquired earlier should be used to guide MMM acquisition, check *Rotate when Load* in Navigator and double-click the map item.
  - Add an easily recognizable point (broken carbon, ice contamination etc.) in the LMM using *Add Marker*. On this alignment point, select *Go to XYZ*.
  - Use the Screen to find back the same position at *View* settings. Acquire *View* in SerialEM.
  - Check that the alignment point is visible. Add marker in View. Use *Navigator > Shift to marker* to match alignment point in LMM and View.
3. **Align View to Record magnification:** Go to a nice and bright square. Go to eucentric height, focus. 
   - Select a well-visible item, e.g. an ice contamination.
   - Center it in a preview shot. Reset Image Shift.
   - Take a view image and drag feature to the center using the right mouse button. In the low-dose menu, select *Set offset for View*.
   - **!! Do not touch this alignment after acquiring your MMMs, it seems to screw up the *Realign to Item* function !!**
4. **Select positions**. Open the LMM. Select the center of square of interest and click *Add Marker* in Navigator for all squares that should be acquired.
5. **Set up montage**. In Navigator, select point. Check "Acquire". Check "New File at Item". Dialog opens, select Montage. Settings:
```
Magnification 4800x
Bin 1
6 x 6 (for 200 mesh)
Overlap 20%
Move Stage
Use View parameters
For FIB lamellae:
3 x 3
Shift Beam instead of moving stage
```
- Save as MMM_01.mrc in **grid-specific Folder.** Activate A / F for all points. Save Navigator.
6. **Start acquisition**. Go to *Navigator > Acquire at Items*. Do *Rough eucentricity* at each point. This takes ca. 10 min per square or 2 min per FIB lamella.

## D) Acquire Tilt Series

> This assumes that all alignments have been performed and square mosaics were acquired. If no mosaics were acquired, do C) step 1 - 3 and add positions for all desired tilt series manually.

1. **Select rough positions**. Go through grid montages acquired in the first step. Select good positions by clicking on them and using *add marker* in Navigator.
2. **Set up acquisition**. Go to Digital Micrograph in an empty hole at eucentricity and acquisition magnification. *Center ZLP* (make sure beam is unblanked!).
   - If Dose calibration cannot be performed in SerialEM: Measure electron flux in DM live view (should be between 8 - 10 e/px/s on carbon / < 20 in hole) and calculate exposure for Record mode. For 140e/A total dose in 41 tilts, this is ca. 3.4 e/A/tilt.
   - If Dose calibration is performed in SerialEM (preferable option): In empty hole, acquire preview image. Select *Tasks > Calibrate Electron Dose*. Enter C2 aperture. Then, in *Camera Setup*, choose exposure time and illuminated area to match ca. 3.4 e/A in Record mode. If big changes are needed, prefer **spot size** change!
3. **Set up camera parameters**. Go to *Camera & Script > Setup*. Make sure all acquisitions are in gain-corrected counting mode!
   - Set exposure times as desired (recommendations in table at top)
   - Set *Record* to unbinned, full frame. Exposure can be changed to yield the desired dose per tilt (usually ca. 0.6 - 1.4 s). 
   - Check *Dose Fractionation* mode (only for *Record*), and choose frame time so there is 6 - 15 frames, preferably an even number. 
     - For a K2, frame time must be a multiple of 0.025 s (0.05 - 0.2 s tested, usually 0.1s). 
   - Check *Align Frames*, select SEMCCD and *4K Default set*. Check *Use GPU*. This aligns frames on-the-fly.
   - **Do not store individual frames!**
4. **Define tilt series**. In Navigator, select point and *Go To XYZ*. Acquire preview, drag image to match selected ROI. If using fiducial markers, the ROI should contain at least 5 - 10 gold particles.
   - For the first image: Select *File > Open New*. Save as batch.mrc in grid folder. Select *Save A*. In Navigator, select *New Map*. 
   - Now, acquire a View. Select *File > Open New*, save as batch-anchor.mrc. In Navigator, select *New Map*. Select no in first pop-up (always save), select yes in second pop-up (save now). Select yes for backlash-correction. In Navigator, select map and check *For anchor state*. 
   - For all further images: Take preview. *Save A (to file 1)> New Map*. In Navigator: *Anchor Map*.
5. **Last checks**. Go to empty hole, repeat dose calibration. Go to carbon, check that beam is nicely centered in record. Save *FEG register* and *SerialEM settings*. Check magnetic field compensation, align ZLP in DM. Check that Turbo Pump is off. Check that *Realign to Item* works.
6. **Start acquisition**. In Navigator, check *Tilt Series* for the first item. Select *Single frame*, save as TS_01.mrc in grid folder. Set-up tilt series. Important considerations are:
   - The tilt range: usually, we use -60:60 in 3 deg increments (41 tilts total). 
   - The tilt scheme: a *bidirectional* scheme from -30 deg for a fast and stable acquisition or a *dose-symmetric* scheme from 0 deg for highest-resolution data, but with more risk of tracking errors and longer acquisition times. 
   - Limit the image shift to ~3 µm at the start. Keep exposure constant. 
   - Set the target defocus as desired (e.g. ca. 4 µm for 64,000x). Do autofocus every step, repeat if error is > 0.2 µm. 
   - Select *Refine Eucentricity* and *Autofocus*. 
   - Select *Wait for Drift to Settle*, set up drift correction between tracking images, wait for < 3 A drift, 10 s between shots, max. 120 s. 
   - Repeat Record if > 5% are lost, do not *Stop and Ask*, track before Autofocus.
7. For further items, only select *Tilt Series* in Navigator, the same settings will be used automatically. Save Navigator.
8. Select *Navigator > Acquire at items*. Do *Realign to item* and *Rough Eucentricity* (not necessary if positions have been picked from MMM with correct Z height) at each. Select *Manage Microscope* to do buffer cycles and wait for LN2 refill. *Close Column Valves* in the end. I usually wait for the first record before I leave.
9. **Clean-up**. Save & Close Navigator. Use *File > Close*. Close SerialEM. Move grid folder to transfer folder and wait for items to copy.

## Working Parameters on Our System
> These record parameters work well on our 1st-generation Titan Krios with K2 detector.

| Magnification         | 64,000x   | 81,000x   | 105,000x  | 
|-----------------------|-----------|-----------|-----------|
| Pixel Size [A]        | 2.21      | 1.755     | 1.372     |
| Tomogram Area [nm]    | 820 x 850 | 650 x 670 | 510 x 525 |
| Spot Size             | 7 nP      | 7 nP      | 7 nP      |
| Illuminated Area [µm] | 1.75      | 0.9       | 0.75      |
| Exposure Time [s]     | 1.2       | 0.6       | 0.5       |
| Exposure Time [s]     | 1.2       | 0.6       | 0.5       |
