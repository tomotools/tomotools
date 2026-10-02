"""Tests for the WarpTools xml -> imod .xf/.tlt conversion math."""

import math

import pytest

from tomotools.utils.warp_xml import compute_tlt_lines, compute_xf_lines


def warp_forward(xf_row: list[float], angpix: float) -> tuple[float, float, float]:
    """Warp's ts_import_alignments math: xf row -> (AxisAngle, OffsetX, OffsetY)."""
    a11, a12, a21, a22, dx, dy = xf_row
    axis_angle = math.degrees(math.atan2(-a21, a11))
    # Shift = R^T . (-dx, -dy), where R = [[a11, a12], [a21, a22]]
    off_x = (a11 * -dx + a21 * -dy) * angpix
    off_y = (a12 * -dx + a22 * -dy) * angpix
    return axis_angle, off_x, off_y


def parse_row(line: str) -> list[float]:
    return [float(v) for v in line.split()]


def test_real_tilt():
    """First tilt of a real dataset (xf row and the values Warp stored for it)."""
    lines = compute_xf_lines([86.48596], [49.049854], [-127.72356], 2.139)
    expected = [0.0612930, 0.9981202, -0.9981202, 0.0612930, 58.194, 26.548]
    assert parse_row(lines[0]) == pytest.approx(expected, abs=2e-3)


@pytest.mark.parametrize("angpix", [1.0, 2.139, 8.0])
@pytest.mark.parametrize(
    "xf_row",
    [
        [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 1.0, 12.5, -7.25],
        [0.0612930, 0.9981202, -0.9981202, 0.0612930, 58.194, 26.548],
        [-0.7071068, 0.7071068, -0.7071068, -0.7071068, -30.0, 100.0],
    ],
)
def test_roundtrip(xf_row, angpix):
    """Warp's import followed by our export returns the original xf row."""
    angle, off_x, off_y = warp_forward(xf_row, angpix)
    line = compute_xf_lines([angle], [off_x], [off_y], angpix)[0]
    assert parse_row(line) == pytest.approx(xf_row, abs=2e-3)


def test_shift_scales_with_pixel_size():
    """Offsets are in Angstrom, so doubling the pixel size halves the shift in px."""
    row1 = parse_row(compute_xf_lines([30.0], [100.0], [50.0], 1.0)[0])
    row2 = parse_row(compute_xf_lines([30.0], [100.0], [50.0], 2.0)[0])
    assert row2[:4] == pytest.approx(row1[:4])
    assert row2[4:] == pytest.approx([row1[4] / 2, row1[5] / 2], abs=2e-3)


def test_tlt_angles_are_inverted():
    assert compute_tlt_lines([60.0, -57.0, 0.0]) == ["-60.00", "57.00", "-0.00"]
