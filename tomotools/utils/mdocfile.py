from pathlib import Path


def _convert_value_field(field: str):
    if " " in field:
        # If there's a space in the field, it might either be a string containing spaces or a tuple of ints/floats
        fields_split = [_convert_value_field(f) for f in field.split()]
        # check if all fields were successfully converted to int or float
        if all(map(lambda v: isinstance(v, int) or isinstance(v, float), fields_split)):
            return fields_split
        else:
            # otherwise it must have been a string
            return field
    else:
        try:
            return int(field)
        except ValueError:
            pass
        try:
            return float(field)
        except ValueError:
            pass
        # No conversion possible
        return field


def find_relative_path(working_dir: Path, abs_path: Path):
    while not working_dir.joinpath(abs_path).is_file():
        try:
            # Cut off first part
            abs_path = Path(*abs_path.parts[1:])
        except IndexError:
            return None
    # print(f'Found subframe path: "{join(working_dir, abs_path)}')
    return working_dir.joinpath(abs_path)


def read(file: Path):
    mdoc = dict()
    mdoc["path"] = file
    mdoc["titles"] = list()
    mdoc["sections"] = list()
    mdoc["framesets"] = list()
    # The currently edited dict, at the beginning this is the mdoc itself (as in, the global metadata)
    # When a section (ZValue) is described, current_section will be set to the dict belonging to that section
    current_section = mdoc
    with open(file) as f:
        for line in f:
            line = line.strip()
            # field, value = line.split(' = ')
            if line.startswith("[T ="):  # Title
                mdoc["titles"].append(line[4:-1])
            elif line.startswith("[ZValue ="):  # Section
                current_section = dict()
                mdoc["sections"].append(current_section)
            elif line.startswith("[FrameSet ="):  # Section
                current_section = dict()
                mdoc["framesets"].append(current_section)
            elif len(line) == 0:
                continue
            else:
                try:
                    key, value = line.split(" = ", maxsplit=1)
                    current_section[key] = _convert_value_field(value)
                except ValueError:
                    print(f'Parsing error, invalid line: "{line}"')
    return mdoc


def _write_key_value(file, key, value):
    if isinstance(value, list):
        file.write(f'{key} = {" ".join([str(v) for v in value])}\n')
    else:
        file.write(f"{key} = {str(value)}\n")


def write(mdoc, path):
    with open(path, "w") as file:
        # First write global vars, then titles, ZValues and FrameSets
        for key, value in mdoc.items():
            if key in ("titles", "sections", "framesets"):
                continue
            _write_key_value(file, key, value)

        for title in mdoc["titles"]:
            file.write(f"\n\n[T = {title}]")

        file.write("\n")
        for i, section in enumerate(mdoc["sections"]):
            file.write(f"\n[ZValue = {i}]\n")
            for key, value in section.items():
                _write_key_value(file, key, value)

        for i, frameset in enumerate(mdoc["framesets"]):
            file.write(f"[FrameSet = {i}]\n")
            for key, value in frameset.items():
                _write_key_value(file, key, value)
