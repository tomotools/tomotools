from pathlib import Path

import click

from tomotools.utils import warp_xml


@click.command()
@click.option(
    "--settings",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="WarpTools tilt-series settings file. Default: WARP_DIR/ts.settings.",
)
@click.option(
    "--prefix",
    type=str,
    default="",
    help="Only process xml files starting with this prefix. The prefix is removed "
    "to find the imod folder (as used for imod2warp --prefix).",
)
@click.option(
    "--alignment-angpix",
    type=float,
    help="Pixel size of the stack the alignment refers to (the value given to "
    "ts_import_alignments). Default: PixelSize from the settings file.",
)
@click.argument(
    "warp_dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.argument(
    "imod_dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def warp2imod(
    settings: Path | None,
    prefix: str,
    alignment_angpix: float | None,
    warp_dir: Path,
    imod_dir: Path,
):
    """Write WarpTools alignments back to imod .xf/.tlt files.

    Takes a WarpTools project (WARP_DIR) and a folder containing one folder per
    imod-aligned tomogram (IMOD_DIR). For every tilt-series xml, the existing
    <name>.xf and <name>.tlt in IMOD_DIR/<name>/ are renamed to .xfbackup and
    .tltbackup, and replaced with the alignment and tilt angles stored in Warp.

    This is the reverse of ts_import_alignments. Per-tilt magnification solved by
    imod cannot be recovered, so the new .xf may deviate slightly (<0.2%) from the
    original one.
    """
    settings = settings or warp_dir / "ts.settings"
    if not settings.is_file():
        raise click.ClickException(f"Settings file {settings} not found.")
    if alignment_angpix is None:
        alignment_angpix = warp_xml.read_settings_pixel_size(settings)
    if alignment_angpix <= 0:
        raise click.ClickException("Pixel size must be positive.")

    xml_dir = warp_xml.find_processing_dir(settings)
    xml_files = sorted(
        xml for xml in xml_dir.glob("*.xml") if xml.stem.startswith(prefix)
    )
    if not xml_files:
        raise click.ClickException(
            f"No xml files starting with '{prefix}' found in {xml_dir}."
        )
    click.echo(f"Using alignment pixel size of {alignment_angpix} A/px.")

    n_done = 0
    for xml_file in xml_files:
        name = xml_file.stem.removeprefix(prefix)
        ts_dir = imod_dir / name
        if not ts_dir.is_dir():
            click.echo(
                f"{xml_file.name}: folder {ts_dir} not found, skipping.", err=True
            )
            continue
        try:
            status = warp_xml.export_alignment_to_imod(
                xml_file, ts_dir, name, alignment_angpix
            )
        except ValueError as e:
            click.echo(f"{xml_file.name}: {e}, skipping.", err=True)
            continue
        click.echo(f"{name}: {status}.")
        n_done += 1

    click.echo(f"Converted {n_done} of {len(xml_files)} tilt series.")
