import os
from typing import Tuple


class SEMNavigator:
    def __init__(self):
        self.header = dict()
        self.items = list()

    @staticmethod
    def read(path: os.PathLike) -> 'SEMNavigator':
        nav = SEMNavigator()
        with open(path) as file:
            for line in file:
                if line.isspace() or len(line) == 0:
                    continue
                elif line.startswith('['):
                    index = _parse_header(line)
                    nav_item = NavigatorItem(index)
                    line = next(file)
                    while not (line.isspace() or len(line) == 0):
                        key, value = _parse_field(line)
                        nav_item[key] = value
                        try:
                            line = next(file)
                        except StopIteration:
                            break
                    nav.items.append(nav_item)
                else:
                    key, value = _parse_field(line)
                    nav.header[key] = value
            return nav


class NavigatorItem(dict):
    def __repr__(self):
        # Best: return Note
        note = self.get('Note')
        if note is not None:
            return note
        # Second best: return MapFile
        map_file = self.get('MapFile')
        if map_file is not None:
            return map_file.rsplit('\\', maxsplit=1)[-1]
        # Fallback: return id
        return self.id

    def __init__(self, id: str):
        super().__init__()
        self.id = id


def _parse_header(line: str) -> str:
    line = line.strip()[1:-1]
    _, value = _parse_field(line)
    return value


def _parse_field(line: str) -> Tuple[str, str]:
    key, value = line.split(' = ', maxsplit=1)
    return key.strip(), value.strip()
