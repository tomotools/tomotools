"""Wrapper for tomotools."""

from importlib.metadata import PackageNotFoundError, version

import click

from tomotools.commands.denoising_deconvolution import (
    deconv,
)
from tomotools.commands.helpers import restore_frames, update
from tomotools.commands.movies import create_movie
from tomotools.commands.preprocessing_reconstruction import (
    blend_montages,
    fix_header_angle,
    preprocess,
    reconstruct,
)
from tomotools.commands.serialem import semnavigator
from tomotools.commands.sta_preparation import (
    fit_ctf,
    imod2tomotwin,
    imod2warp,
    reconstruct_3dctf,
)


def _get_version():
    try:
        return version("tomotools")
    except PackageNotFoundError:
        return "unknown"


@click.group()
def tomotools():
    """Scripts for cryo-ET data processing."""
    click.echo(f"Tomotools version {_get_version()} \n")


tomotools.add_command(blend_montages)
tomotools.add_command(preprocess)
tomotools.add_command(reconstruct)
tomotools.add_command(deconv)
tomotools.add_command(imod2warp)
tomotools.add_command(imod2tomotwin)
tomotools.add_command(fit_ctf)
tomotools.add_command(reconstruct_3dctf)
tomotools.add_command(semnavigator)
tomotools.add_command(create_movie)
tomotools.add_command(fix_header_angle)
tomotools.add_command(restore_frames)
tomotools.add_command(update)
