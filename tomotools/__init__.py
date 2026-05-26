"""Wrapper for tomotools."""

from importlib.metadata import PackageNotFoundError, version

import click

from .commands import commands


def _get_version():
    try:
        return version("tomotools")
    except PackageNotFoundError:
        return "unknown"

@click.group()
def tomotools():
    """Scripts for cryo-ET data processing."""
    click.echo(f"Tomotools version {_get_version()} \n")


for command in commands:
    tomotools.add_command(command)
