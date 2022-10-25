import click

from .commands import commands


@click.group()
def tomotools():
    click.echo('Tomotools version 0.2.1')


for command in commands:
    tomotools.add_command(command)
