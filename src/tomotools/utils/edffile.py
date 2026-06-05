from pathlib import Path


def read_edf(path: Path) -> dict[str, str]:
    """Read ebt file and return a dict with the values."""
    values = {}
    with open(path) as file:
        for line in file:
            if line.startswith("#") or not line.strip():
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def get_ebt_datasets(ebt: dict) -> list[str]:
    """Get datasets from ebt dict."""
    datasets = []
    i = 1
    while True:
        key = f"meta.ref.ebt{i}"
        if key in ebt:
            datasets.append(ebt[key])
            i += 1
        else:
            break
    return datasets
