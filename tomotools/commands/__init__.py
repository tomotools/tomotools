"""Load available subcommands."""
import inspect
import pkgutil

import click

__all__ = []
commands = []

# derived from:
# https://stackoverflow.com/questions/64844219/python-import-all-functions-from-folder

for loader, name in pkgutil.walk_packages(__path__):
    module = loader.find_module(name).load_module(name)

    for f_name, value in inspect.getmembers(
        module, lambda m: isinstance(m, click.core.Command)
    ):
        __all__.append(f_name)
        commands.append(value)
