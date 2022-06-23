import click


@click.command()
@click.argument('input_file', type=click.File())
@click.argument('output_file', type=click.File())
def nff_to_amiramesh(input_file, output_file):
    pass


class Contour:
    def __init__(self, coords: list, unit: str):
        self.coords = coords
        self.unit = unit


class NFF:
    """http://paulbourke.net/dataformats/nff/nff1.html"""

    def __init__(self, path, red, green, blue, Kd, Ks, Shine, T, index_of_refraction, contours):
        self.path = path
        self.red = red
        self.green = green
        self.blue = blue,
        self.Kd = Kd
        self.Ks = Ks
        self.Shine = Shine
        self.T = T
        self.index_of_refraction = index_of_refraction
        self.contours = contours

    @staticmethod
    def read(path) -> 'NFF':
        path = path
        red, green, blue = None, None, None
        Kd, Ks = None, None
        Shine, T, index_of_refraction = None, None, None
        contours = list()
        with open(path) as file:
            points_to_parse = 0
            for line in file:
                line = line.strip()
                if line.startswith('#'):
                    continue
                if points_to_parse > 0:
                    contours[-1].append([int(p) for p in line.split()])
                    points_to_parse -= 1
                elif line.startswith('f'):
                    split = line.split()
                    if len(split) != 9:
                        raise SyntaxError('Format field has unexpected amount of values')
                    red, green, blue, Kd, Ks, Shine, T, index_of_refraction = split[1:]
                elif line.startswith('p'):
                    split = line.split()
                    if len(split) != 2:
                        raise SyntaxError('Points field has unexpected amount of values')
                    points_to_parse = int(split[1])
                    contours.append(list())
                else:
                    print(f'Didn\'t parse line: {line}')
        return NFF(path, red, green, blue, Kd, Ks, Shine, T, index_of_refraction, contours)


class AmiraMesh:
    pass
