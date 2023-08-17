import numpy as np


def tom_ctf1d(length, pixelsize, voltage, cs, defocus, amplitude, phaseshift, bfactor):
    """A Python port of tom_ctf1d.m
    Input length of ctf, pixelsize in m, voltage in V, cs in m, defocus in m, amplitude contrast, phaseshift in rad, bfactor
    """

    ny = 1 / pixelsize
    lam = 12.2643247 / np.sqrt(voltage * (1.0 + voltage * 0.978466e-6)) * 1e-10
    lam2 = lam * 2

    points = np.arange(0, length)
    points = points / (2 * length) * ny
    k2 = np.power(points, 2)
    term1 = np.power(lam, 3) * cs * np.power(k2, 2)

    w = np.pi / 2 * (term1 + lam2 * defocus * k2) - phaseshift

    acurve = np.cos(w) * amplitude
    pcurve = -1 * np.sqrt(1 - np.power(amplitude, 2)) * np.sin(w)
    bfactor = np.exp(-1 * bfactor * k2 * 0.25)

    ctf = (pcurve + acurve) * bfactor

    return ctf


def wiener(
    angpix, defocus, snrfalloff, deconvstrength, hpnyquist, phaseflipped, phaseshift
):
    """Calculates Wiener filter for tom_deconv
    Input: angpix, defocus in um (underfocus = positive value), highpass limit as fraction of Nyquist, phaseflipped Y/N, phaseshift in Deg
    """

    highpass = np.linspace(0, 1, 2048)
    highpass = np.minimum(1, highpass / hpnyquist) * np.pi
    highpass = 1 - np.cos(highpass)

    snr = (
        np.exp(np.linspace(0, -1, 2048) * snrfalloff * 100 / angpix)
        * np.power(10, 3 * deconvstrength)
        * highpass
    )

    ctf = tom_ctf1d(
        2048,
        angpix * 1e-10,
        300e3,
        2.7e-3,
        -1 * defocus * 1e-6,
        0.07,
        phaseshift / 180 * np.pi,
        0,
    )

    if phaseflipped:
        ctf = np.abs(ctf)

    wiener = np.divide(ctf, (np.power(ctf, 2) + 1 / snr))

    return wiener
