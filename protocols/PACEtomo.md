# PACEtomo how-to
> version 220831

1. Load Carbon Grid
2. Do all alignments. Preferably use nP mode for Rec/Foc/Tra etc. Set Focus offset to 0!
3. Also do Coma-vs-IS alignment (do not close SerialEM after!)
4. Measure tilt axis offset using measure_offset.py at desired mag etc. -> set it under Tasks -> Eucentricity -> Offset, check again, until it converges (microscope + mag parameter, does not need to be done everytime if you already know it for your mag!)
5. Load FIBbed grid
6. Acquire MMM 3x3 at 4800x w/ IS -> move stage off. 
7. Use measure_geometry on one or several lamellae to get good values for your grid for both tilt and rotation. 
8. Drive to lamella center, go to eucentric, select points using script. 
9. Run w/ geometry set.
