import os
from pathlib import Path

import click

from .commands import commands


@click.group(chain=True)
@click.option('-o', '--output-dir', 'output_dir', type=click.Path(dir_okay=True, file_okay=False))
@click.pass_context
def tomotools(ctx, output_dir: os.PathLike):
    click.echo('Tomotools version 0.3')
    ctx.ensure_object(dict)
    ctx.obj['OUTPUT_DIR'] = output_dir
    click.echo(f'Working in {output_dir}')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


# https://github.com/pallets/click/tree/main/examples/imagepipe
@tomotools.result_callback()
def process_commands(processors, output_dir):
    """This result callback is invoked with an iterable of all the chained
    subcommands.  As in this example each subcommand returns a function
    we can chain them together to feed one into the other, similar to how
    a pipe on unix works.
    """
    # Start with an empty iterable.
    stream = ()
    # Pipe it through all stream processors.
    for processor in processors:
        stream = processor(stream)
    # Evaluate the stream and throw away the items.
    for _ in stream:
        pass


for command in commands:
    tomotools.add_command(command)
