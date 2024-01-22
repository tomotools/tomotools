"""Wrapper for tomotools."""

import click

from .commands import commands


@click.group()
def tomotools():
    """Scripts for cryo-ET data processing."""
    click.echo("Tomotools version 0.3.1 \n")


for command in commands:
    tomotools.add_command(command)
