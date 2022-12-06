import click

from tomotools.utils.tiltseries import run_ctfplotter, convert_input_to_TiltSeries

@click.command()
@click.argument('input_files', nargs=-1)
def fit_ctf(input_files):
    """ Performs interactive CTF-Fitting. 
    
    Takes tiltseries or folders containing them as input. Runs imod ctfplotter interactively. Saves results to folder.  
    
    """

    tiltseries = convert_input_to_TiltSeries(input_files)
    
    for ts in tiltseries:
        run_ctfplotter(ts)