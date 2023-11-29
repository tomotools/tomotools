import click
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.path import Path

from tomotools.utils.serialem_navigator import SEMNavigator


@click.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
def semnavigator(path):
    """Open a SerialEM navigator (.nav) file in a small graphical browser."""
    nav = SEMNavigator.read(path)
    fig, ax = plt.subplots()
    all_ptsx, all_ptsy = [], []
    for item in nav.items:
        ptsx_str, ptsy_str = item.get("PtsX"), item.get("PtsY")
        if ptsx_str is None or ptsy_str is None:
            continue
        ptsx = [float(x) for x in ptsx_str.split()]
        ptsy = [float(y) for y in ptsy_str.split()]
        if len(ptsx) != len(ptsy):
            raise AttributeError(f"PtsX and PtsY have unequal length in item {item.id}")
        all_ptsx += ptsx
        all_ptsy += ptsy
        vertices = list(zip(ptsx, ptsy))
        codes = [Path.MOVETO] + [Path.LINETO] * (len(vertices) - 1)
        path = Path(vertices, codes)
        patch = patches.PathPatch(path, facecolor="none", lw=2)
        ax.add_patch(patch)
        ax.text(*vertices[0], item)
    ax.set_xlim(min(all_ptsx) * 1.1, max(all_ptsx) * 1.1)
    ax.set_ylim(min(all_ptsy) * 1.1, max(all_ptsy) * 1.1)
    plt.show()
