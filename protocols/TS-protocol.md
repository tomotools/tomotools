# Tilt Series Acquisition

> Benedikt Wimmer, Medalia Lab @ UZH, 2022 - Version 220729

### This Protocol covers:

A) Mapping all grids in Autoloader at low magnification with SerialEM.\
B) Automated square mapping.\
C) Direct Adjustments of Titan Krios scope.\
D) Set-up of Tilt Series acquisition including frame alignment in SEMCCD.

## A) Automated Mapping

> **Usual settings are C2 70, Objective out, Spot size 7, Magnification 175x, GIF slit 30-50eV, flux 8 - 20 e/px/s, defocus -160 um. View parameters: bin 1, counting mode, 1 sec.**

1. **Load samples.** Dock NanoCab, initialize Autoloader if needed. Click "Edit Slot State", define for all cassette positions (click 1x for occupied, 2x for empty). Run inventory for at least all occupied positions and one empty position.
2. **Prepare Settings**. Switch Turbo pump to "always on". Without grid on column, quickly check beam shift, save to FEG register. Load the first grid.
3. **Set up session.** Start SerialEM, load Atlas settings or create new ones with parameters above. Acquire View to see whether sample is there. *Open Navigator* and Select *Navigator -> Montaging & Grids -> Set-up Full Montage.* Use the following settings:

   > Magnification 175x \
   > Bin 2 \
   > Overlap 10% \
   > Use View parameters \
   > Use Continuous mode \
   > Move Stage

   Save as LMM.mrc to grid-specific folder or screening folder.
4. **Start acquisition.** The grid overview can either be done for all grids at once **(option 1)** or for each grid individually **(option 2)**. Use the first to get a general overview of your samples, use the second to guide acquisition of a specific grid.
   1. **Map all grids:** In SerialEM, go so *Script -> Edit* to edit script *mapgrids* (currently at Pos. 2, or download from SerialEM script repository). Copy and paste the blocks to include all grid positions that should be included. Start script. This takes 10 - 15 min per grid. \
      **Check results** by going through maps in Navigator. In *Montage Controls*, select bin 2 for overview and check *treat as a very sloppy montage* if stitching is not satisfactory. For each grid you'll continue with, start a new folder and Navigator file, otherwise it is very messy!
   2. **Atlas to guide acquisition:** In SerialEM, select *Tasks -> Eucentric rough.* Then, in the *Montage Control* panel on the left, select *Start.* After acquisition, select the map and check "Rotate when load" in Navigator to match rotation in SA mode.
5. **Clean-up.** Switch Turbo pump to "auto off". Save Navigator, save Settings. Close Atlas Settings.

## B) Prepare maps of grid squares

> **Usual settings are C2 aperture 50, Objective aperture 100, overview at 4,800x (-80 um defocus), data acquisition at 64,000x, slit width 20 eV, electron flux 8 - 10 e/px/s, spot size 7, illuminated area 2 - 2.5 um. For FIB lamellae, overview at 6,500x or 8,700x can reveal more details.**

1. **Load settings.** Make sure *low dose* is checked. Load *FEG register* for the desired magnification or set the apertures to the right sizes. Check that under *Calibration -> Set Aperture* the right C2 size is set in SerialEM.
2. **Check beam.** Make sure you are close to eucentric height, especially if you did not acquire the LMM at eucentricity. Check that the alignment for the *View* mode is good by inserting screen. If needed, adjust beam shift. Check *Set additional beam shift*. Shift beam via Trackball. Uncheck *additional beam shift*. Save settings. If image looks weird, consider using *Autofocus* once at eucentric height (also check autofocus settings on screen this case).
3. **Match Atlas shift.** If LMM acquired earlier should be used to guide MMM acquisition, check *Rotate when Load* in Navigator and double-click. Add an easily recognizable point (broken carbon, ice contamination etc.) in the LMM using *Add Marker*. On this alignment point, select *Go to XYZ*. Use the Screen to find back the same position at *View* settings. Acquire *View* in SerialEM. Check that the alignment point is visible. Add marker in View. Use Navigator -> Shift to marker to match alignment point in LMM and View.
4. **Select positions**. Open the LMM. Select the center of square of interest and click *Add Marker* in Navigator for all squares that should be acquired.
5. **Set up montage**. In Navigator, select point. Check "Acquire". Check "New File at Item". Dialog opens, select Montage. Settings:

   > Magnification 4800x\
   > Bin 1\
   > 6 x 6 (for 200 mesh)\
   > Overlap 20%\
   > Move Stage\
   > Use View parameters

   Save as MMM_01.mrc in **grid-specific Folder.** Activate A / F for all points. Save Navigator.
6. **Start acquisition**. Go to *Navigator -> Acquire at Items*. Do *Rough eucentricity* at each point. This takes ca. 10 min per square.

## C) Microscope Alignments

> A good primer can be found in Christos Savas Lecture at MRC-LMB:\
> https://youtu.be/9AMSabcTN24
> A good introduction to the terminology is in Grant Jensens YouTube lecture:\
> https://youtu.be/hc2s4uSbpyI

> MX / MY stand for Multifunction X / Y keys.\
> DM is Digital Micrograph.\
> Tutorial starts with **camera is out, screen is in, no objective lens**.

 1. On your Atlas or MMM, find an **empty carbon area**. Check that the C2 aperture is set correctly. Use *Tasks -> Eucentric rough* to go to eucentric height. Focus if needed.
 2. **Adjust gun tilt and shift (usually fine).** Under *Direct Alignments*, adjust gun tilt and gun shift with MX and MY keys. Optimize for a high electron flux (high exposure dose or screen current, low exposure time).
 3. **Align C2 aperture (usually stable).** First, go to *Beam settings -> Flip-out Menu -> Free Ctrl. -> C3 off*. Go to crossover point (beam as small as possible). Center beam using trackball. Expand beam (turn "Intensity" knob clockwise). If beam is not centered, activate *C2 adjustments*, move to center with MX and MY. Check several times. Inactivate *C2 adjustments*, go back to *TEM mode*.
 4. **Adjust C2 stigmator (check daily).** Go to Spot size that will be used for data collection (e.g. 7). Go to record magnification (e.g. 64,000 x). Check whether spot is circular. Otherwise, go to *Stigmator -> C2*, modify using MX and MY.
 5. **Direct Alignments (daily)**. Go to record settings (true spot size, focus, magnification, EFTEM mode). Make sure you're at eucentric height. Focus on the carbon with a very low defocus (e.g. -0.5um). This can either be done using SerialEM or manually.
To focus manually, open DM and activate the Live View and energy filter. Display Live FFT. *Mind the exposure rate!* Focus on the Carbon area (First zero of the Thon rings should be at the edges.).
*Direct Alignments* can now be performed on the screen. The workflow is top to bottom. Use MX and MY keys. Start after gun tilt / shift. For *Pivot Points*, preferentially use MX (fine adjustments) to reduce motion. For *Beam shift*, center the beam on GIF (green circle on Screen view). C2 aperture can be skipped here if already done above. *Condenser center TEM* aligns the C3 aperture. Try to reduce motion as much as possible using MX and MY. *Rotation Center* is a critical prerequisite for good coma-free alignment. Assuming that you are using the normal microprobe mode of the microscope, open the live view in DM and try to reduce motion of the image as much as possible with MX and MY. Once done, save settings as *FEG register*. In nanoprobe mode, reduce the movement of the beam (not the image).
 6. **Coma-Free adjustments (daily)**. The easiest way to do Coma-Free alignment is in SerialEM. Make sure that the "Record" setting is giving an image. Go to a nice carbon area. Then use *Focus/Tune -> Coma-free Alignment by CTF*. If selecting *Process -> Live FFT / Side-by-Side*, you can check the CTF fit. 
 For manual coma-free alignment, open DM. Start Live View and Live FFT. On the microscope PC, under *Direct Adjustments*, select Coma-free alignments. Check that the alternating FFTs overlap, otherwise use MX until they do. Go back and forth between X and Y.
 7. **Center Objective Aperture (daily, usually fine)**. Insert screen. Insert Objective aperture. Go to diffraction mode, you should see a bright spot with some Thon rings around it if you're on Carbon. By clicking the FloScreen window and scrolling, you can adjust brightness and contrast, until you can clearly see the outline of the aperture as a black circle around the beam. Select *Adjust Objective aperture* and use MX and MY to center the aperture around the beam.
 8. **Objective Lens astigmatism (daily - best do at very high mag, e.g. 270,000x)**. Again, the easiest way to do this is in SerialEM. Go to very high magnification (e.g. 270,000x), check that *Preview* yields a good image of a carbon area. Select *Focus/Tune -> Correct Astigmatism by CTF*. If it is greyed out, activate by first going to *Calibration -> Focus & Tuning -> Astigmatism by CTF*. Once run, it adjusts the Objective lens stigmator by the values it specifies. 
 To adapt this manually, go to DM, acquire a dose fractionated image with a long exposure (e.g. 10s in 0.1s increments). Use *Image Processing / Measure Drift / Remove Drift* to correct for motion. Then, add exposures using *Volume -> Project Z*. Look at the power spectrum through *Process -> FFT*. Rings should be exactly concentric and round.
 9. **Save settings** to a *FEG Register*.
 10. **Tune EFTEM (occasionally)**. Insert K2. Go to empty square on the grid. Go to record magnification, C2 150, Spot size 2, illuminated area ca. 10 um. *Normalize all lenses* (= L2), press *eucentric focus*. Adjust beam shift if needed with track ball. Check magnetic field compensator (next to door). Values should be close to zero (< 0.01). Otherwise, reset it. Adjust intensity so beam is parallel (can be checked in *beam settings*). Start live view in linear mode. On the left side, select *Tune GIF*. Perform a *full tune* of the EFTEM. Make sure all steps are completed, otherwise perform them individually using the *quick tune* setting. After tuning is completed, center ZLP. DM can hold on to calibrations for different magnifications, so it might be useful to repeat this at View magnification.
 11. **Prepare gain reference (weekly)**. At settings from step 10, spread the beam a bit (but keep it parallel!). Insert K2 camera. Click *Camera -> Prepare Gain Reference*. If *Camera* is not visible, go to *Help -> User Mode -> Power User*. Accept default settings. A view is started which shows the read counts. Adjust, until these are around 500 (within 1%). Click ok to prepare linear mode reference. After this, click yes to prepare a counting mode reference. Do not dismiss the warning message! First, go back to settings saved in Step 9. Check settings on screen before continuing. Once settings (C2 aperture, objective aperture, spot size, illuminated area) have been applied, confirm message in DM. Bring average count to 1. Prepare gain reference.

## D) Acquire Tilt Series

> This assumes that all alignments have been performed and square mosaics were acquired. If no mosaics were acquired, do B) step 1 - 3 and add positions for all desired tilt series manually.

1. **Select rough positions**. Go through grid montages acquired in the first step. Select good positions by clicking on them and using *add marker* in Navigator. Align View to Record magnification: select a well-visible item, eg. an ice contamination. Center it in a preview shot. Take a view image and drag feature to the center. In the low-dose menu, select "Set offset for view". 
2. **Set up acquisition**. Go to Digital Micrograph in an empty hole at eucentricity and acquisition magnification. *Center ZLP* (make sure beam is unblanked!).
   * If Dose calibration cannot be performed in SerialEM: Measure electron flux in DM live view (should be between 8 - 10 e/px/s on carbon / < 20 in hole) and calculate exposure for Record mode. For 140e/A total dose in 41 tilts, this is ca. 3.4 e/A/tilt.
   * If Dose calibration is performed in SerialEM (preferable option): In empty hole, acquire preview image. Select *Calibration -> Electron Dose*. Enter C2 aperture. Then, in *Camera Setup*, choose exposure time and illuminated area to match ca. 3.4 e/A in Record mode. If big changes are needed, prefer **spot size** change!
3. **Set up camera parameters**. Go to *Camera & Script -> Setup*. Make sure all acquisitions are in gain-corrected counting mode!
 * Set *View* to ca. 1 - 1.5 s exposure, no binning, full frame.
 * Set *Record* to unbinned, full frame. Exposure can be changed to yield the desired dose per tilt (usually ca. 0.6 - 1.4 s).
 * Check *Dose Fractionation* mode (only for *Record*), and choose frame time so there is 6 - 15 frames. For a K2, frame time must be a multiple of 0.025 s (0.05 - 0.2 s tested, usually 0.1s). Check *Align Frames*, select SEMCCD and *4K Default set*. Check *Use GPU*. This align frames on-the-fly.
 * *Do not store individual frames!*
 * *Preview* should be 20 - 30% of *Record* exposure.
 * *Trial* at bin 2, 50% of *Record* exposure.
 * *Focus* at bin 4, 50% of *Record* exposure.
4. **Define tilt series**. In Navigator, select point and *Go To XYZ*. Acquire preview, drag image to match selected ROI. If using fiducial markers, the ROI should contain at least 5 gold particles.
   * For the first image: Select *File -> Open New*. Save as batch.mrc in grid folder. Select *Save A*. In Navigator, select *New Map*. Now, acquire a View. Select *File -> Open New*, save as batch-anchor.mrc. In Navigator, select *New Map*. Select no in first pop-up (always save), select yes in second pop-up (save now). Select yes for backlash-correction. In Navigator, select map and check *For anchor state*.
   * For all further images: Take preview. *Save A (to file 1)-> New Map*. In Navigator: *Anchor Map*.
5. **Last checks**. Go to empty hole, repeat B) 2. Save *FEG register* and *SerialEM settings*. Check magnetic compensation, align ZLP in DM. Check that Turbo Pump is off.
6. **Start acquisition**. In Navigator, check *Tilt Series* for the first item. Select *Single frame*, save as TS_01.mrc in grid folder. Set-up tilt series. Important considerations are:
 * The tilt range: usually, we use -60:60 in 3 deg increments (41 tilts total).
 * The tilt scheme: a *bidirectional* scheme from -30 deg for a fast and stable acquisiton or a *dose-symmetric* scheme from 0 deg for highest-resolution data, but with more tracking errors.
 * Limit the image shift to 0 um at the start. Keep exposure constant.
 * Set the target defocus as desired (e.g. ca. 5 um for 64,000x). Do autofocus every step, repeat if error is > 0.2 um.
 * Select *Refine Eucentricity* and *Autofocus*.
 * Select *Wait for Drift to Settle*, set up drift correction between tracking images, wait for < 3 A drift, 10 s between shots, max. 120 s.
 * Repeat Record if > 5% are lost, do not *Stop and Ask*, track before Autofocus.
7. For further items, only select *Tilt Series* in Navigator, the same settings will be used automatically. Save Navigator.
8. Select *Navigator -> Acquire at items*. Do *Realign to item* and *Rough Eucentricity* (not necessary if positions have been picked from MMM with correct Z height) at each. Select *Manage Microscope* to do buffer cycles and wait for LN2 refill. *Close Column Valves* in the end. I usually wait for the first record before I leave.
7. **Clean-up**. Save & Close Navigator. Use *File -> Close*. Close SerialEM. Move grid folder to transfer folder and wait for items to copy.
