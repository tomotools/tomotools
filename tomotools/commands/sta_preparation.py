import os
import click

from pathlib import Path

from tomotools.utils.tiltseries import TiltSeries, align_with_areTomo, run_ctfplotter

@click.command()
@click.argument('input_files', nargs=-1)
def run_ctfplotter(input_files):
    pass

