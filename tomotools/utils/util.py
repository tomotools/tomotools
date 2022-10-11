import subprocess


def _list_append_replace(l: list, index: int, item):
    if 0 <= index < len(l):
        # Can replace
        l[index] = item
    elif index == len(l):
        # Append
        l.append(item)
    else:
        raise IndexError('Can only replace items and append one item, not multiple')

def num_gpus():
    name = subprocess.Popen(['nvidia-smi','--query-gpu=name','--format=csv,noheader'], stdout=subprocess.PIPE)
    num = subprocess.check_output(['wc','-l'], stdin=name.stdout)
    name.wait()
    return int(num)

def gpuinfo():
    def indent_level(line: str):
        indent_level = 0
        while line[indent_level * 4:indent_level * 4 + 4] == '    ':
            indent_level += 1
        return indent_level

    lines = subprocess.run(['nvidia-smi', '-q'], capture_output=True).stdout.decode('utf-8').splitlines()
    parsed = dict()
    # ..denoting the indentation levels # TODO properly comment
    active_dicts = [parsed]
    for line in lines:
        # Skip empty lines
        if len(line.strip()) == 0:
            continue
        elif len(line) > 42 and line[42] == ':':
            # If line is a key : value pair
            # there is a colon at position 42, denoting a key : value pair
            # let's just hope that's always the case
            active_dicts[indent_level(line)][line[:42].strip()] = line[43:].strip()
        else:
            # Section heading
            heading = line.strip()
            level = indent_level(line)
            d = dict()
            active_dicts[level][heading] = d
            _list_append_replace(active_dicts, level + 1, d)
    return parsed
