"""Convert WarpTools tilt-series metadata (xml) back to imod .xf / .tlt files.

This is the inverse of ``WarpTools ts_import_alignments`` (WarpLib
``TiltSeries.ImportAlignments``). For each tilt, Warp stores

    AxisAngle  = atan2(-A21, A11)
    AxisOffset = R^T . (-DX, -DY) * alignment_angpix      (Angstrom)

where ``A11 A12 A21 A22 DX DY`` is the imod .xf line and R the 2x2 rotation
matrix. Only the direction of the xf matrix survives the import, so a
per-tilt magnification solved by tiltalign cannot be recovered (typically a
<0.2% deviation from the original .xf). Warp's <Angles> always carry the
opposite sign of imod's .tlt convention.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_ELEMENTS = ("Angles", "AxisAngle", "AxisOffsetX", "AxisOffsetY")
TLT_MATCH_TOLERANCE = 0.5


def _parse_list(root: ET.Element, tag: str) -> list[str] | None:
    node = root.find(tag)
    if node is None or node.text is None:
        return None
    return node.text.strip().split("\n")


def parse_tiltseries_xml(path: Path) -> dict:
    """Read the per-tilt fields needed for an imod export from a Warp xml."""
    root = ET.parse(path).getroot()

    data = {}
    for tag in REQUIRED_ELEMENTS:
        values = _parse_list(root, tag)
        if values is None:
            raise ValueError(f"<{tag}> not found (or empty) in {path}")
        data[tag] = [float(v) for v in values]

    ntilts = len(data["Angles"])
    for tag, values in data.items():
        if len(values) != ntilts:
            raise ValueError(f"<{tag}> has {len(values)} values, expected {ntilts}")

    use_tilt_raw = _parse_list(root, "UseTilt")
    if use_tilt_raw is None:
        use_tilt = [True] * ntilts
    else:
        use_tilt = [v.strip() == "True" for v in use_tilt_raw]
        if len(use_tilt) != ntilts:
            raise ValueError(f"<UseTilt> has {len(use_tilt)} values, expected {ntilts}")

    return {
        "angles": data["Angles"],
        "axis_angle": data["AxisAngle"],
        "axis_offset_x": data["AxisOffsetX"],
        "axis_offset_y": data["AxisOffsetY"],
        "use_tilt": use_tilt,
    }


def _read_settings_param(settings_path: Path, name: str) -> str:
    for param in ET.parse(settings_path).getroot().iter("Param"):
        if param.get("Name") == name:
            return param.get("Value")
    raise ValueError(f"Parameter {name} not found in {settings_path}")


def read_settings_pixel_size(settings_path: Path) -> float:
    """Return the PixelSize (Angstrom/px) from a WarpTools .settings file."""
    return float(_read_settings_param(settings_path, "PixelSize"))


def find_processing_dir(settings_path: Path) -> Path:
    """Return the directory holding the tilt-series xml files of a Warp project."""
    folder = _read_settings_param(settings_path, "ProcessingFolder")
    return (settings_path.parent / folder).resolve()


def compute_xf_lines(
    axis_angles_deg: list[float],
    offset_x_angstrom: list[float],
    offset_y_angstrom: list[float],
    angpix: float,
) -> list[str]:
    """Compute imod .xf lines from Warp's per-tilt axis angle and offsets.

    With phi = AxisAngle: A11 = cos(phi), A12 = sin(phi), A21 = -sin(phi),
    A22 = cos(phi); (DX, DY) = -A . (AxisOffsetX, AxisOffsetY) / angpix.
    """
    lines = []
    for phi_deg, ox, oy in zip(
        axis_angles_deg, offset_x_angstrom, offset_y_angstrom, strict=True
    ):
        phi = math.radians(phi_deg)
        a11, a12 = math.cos(phi), math.sin(phi)
        a21, a22 = -math.sin(phi), math.cos(phi)
        sx, sy = ox / angpix, oy / angpix
        dx = -(a11 * sx + a12 * sy)
        dy = -(a21 * sx + a22 * sy)
        lines.append(
            f"{a11:12.7f}{a12:12.7f}{a21:12.7f}{a22:12.7f}{dx:12.3f}{dy:12.3f}"
        )
    return lines


def compute_tlt_lines(warp_angles_deg: list[float]) -> list[str]:
    """Convert Warp tilt angles to imod .tlt lines (sign is always inverted)."""
    return [f"{-angle:.2f}" for angle in warp_angles_deg]


def _read_numbers(path: Path) -> list[list[float]]:
    return [
        [float(v) for v in line.split()]
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def _backup(path: Path) -> bool:
    """Rename file.xf to file.xfbackup unless that exists. True if renamed."""
    backup = path.with_suffix(path.suffix + "backup")
    if backup.exists():
        return False
    path.rename(backup)
    return True


def export_alignment_to_imod(
    xml_path: Path, ts_dir: Path, root_name: str, angpix: float
) -> str:
    """Replace <root_name>.xf/.tlt in ts_dir with the alignment stored in a Warp xml.

    The existing files are renamed to .xfbackup/.tltbackup first (an already
    existing backup is kept, so the very first original is never lost). The
    existing files also determine which tilts are written: all tilts of the xml,
    or only those with UseTilt=True if the imod files exclude the other views.
    Raises ValueError (without changing any file) if the xml does not fit.
    Returns a short status message.
    """
    xf_path = ts_dir / f"{root_name}.xf"
    tlt_path = ts_dir / f"{root_name}.tlt"
    for existing in (xf_path, tlt_path):
        if not existing.is_file():
            raise ValueError(f"{existing} not found")

    data = parse_tiltseries_xml(xml_path)
    ntilts = len(data["angles"])
    nused = sum(data["use_tilt"])
    n_existing = len(_read_numbers(xf_path))

    if n_existing == ntilts:
        indices = list(range(ntilts))
    elif n_existing == nused:
        indices = [i for i in range(ntilts) if data["use_tilt"][i]]
    else:
        raise ValueError(
            f"{xf_path.name} has {n_existing} lines, but the xml has {ntilts} tilts "
            f"({nused} used)"
        )

    new_tlt = compute_tlt_lines([data["angles"][i] for i in indices])
    old_tlt = [row[0] for row in _read_numbers(tlt_path)]
    if len(old_tlt) != len(new_tlt) or any(
        abs(float(new) - old) > TLT_MATCH_TOLERANCE
        for new, old in zip(new_tlt, old_tlt, strict=True)
    ):
        raise ValueError(
            f"tilt angles in {xml_path.name} do not match {tlt_path.name}; "
            "wrong tomogram pairing?"
        )

    new_xf = compute_xf_lines(
        [data["axis_angle"][i] for i in indices],
        [data["axis_offset_x"][i] for i in indices],
        [data["axis_offset_y"][i] for i in indices],
        angpix,
    )

    newly_backed_up = [_backup(xf_path), _backup(tlt_path)]
    xf_path.write_text("\n".join(new_xf) + "\n")
    tlt_path.write_text("\n".join(new_tlt) + "\n")

    status = f"wrote {len(indices)} tilts"
    if not all(newly_backed_up):
        status += " (existing backup kept)"
    return status
