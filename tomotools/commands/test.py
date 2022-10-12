import click

from tomotools.utils.click_utils import processor
import click

from tomotools.utils.click_utils import processor


@click.command()
@processor
def print_files(files):
    """Just a helper function for myself to be able to see which files are yielded"""
    for file in files:
        print(f'A file was yielded: {file}')
        yield file
