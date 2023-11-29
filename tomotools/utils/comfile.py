def get_value(path, key):
    """Get value from comfile at path using key."""
    with open(path) as file:
        for line in file:
            if line.startswith(f"{key}\t"):
                return line.split()[1].strip()
    return None


def modify_value(path, key, value):
    """Set value for key in comfile at path."""
    lines = []
    with open(path) as file:
        lines = file.readlines()
    for n, line in enumerate(lines):
        if line.startswith(f"{key}\t"):
            lines[n] = f"{key}\t{value}\n"
        elif line.startswith(f"{key} "):
            lines[n] = f"{key} {value}\n"
    with open(path, "w") as file:
        file.writelines(lines)
