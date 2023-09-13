from subprocess import run
import click

@click.command()
@click.option('--branch', default='main', show_default=True, help='The GitHub branch to use')
def update(branch):
    """Auto-update tomotools to the latest version"""
    print('Updating...')
    run(['pip', 'install', '--upgrade', f'git+https://github.com/tomotools/tomotools.git@origin/{branch}'])
    print('Update completed!')
