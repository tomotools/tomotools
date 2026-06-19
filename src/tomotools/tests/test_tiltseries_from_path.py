"""Tests for TiltSeries.from_path and related methods."""

from pathlib import Path

import pytest

from tomotools.utils.tiltseries import TiltSeries


@pytest.fixture
def ts_dir_with_mdocs(tmp_path: Path):
    """Create a directory with MRC files and corresponding MDOC files."""
    ts1_mrc = tmp_path / "TS_01.mrc"
    ts1_mdoc = tmp_path / "TS_01.mrc.mdoc"
    ts2_mrc = tmp_path / "TS_02.st"
    ts2_mdoc = tmp_path / "TS_02.st.mdoc"

    ts1_mrc.touch()
    ts1_mdoc.touch()
    ts2_mrc.touch()
    ts2_mdoc.touch()

    return tmp_path, [ts1_mrc, ts2_mrc]


@pytest.fixture
def ts_dir_with_excluded_mdocs(tmp_path: Path):
    """Create a directory with files that should be excluded (allviews, cutviews)."""
    # These should be yielded
    regular_mrc = tmp_path / "TS_01.mrc"
    regular_mdoc = tmp_path / "TS_01.mrc.mdoc"
    regular_mrc.touch()
    regular_mdoc.touch()

    # These should be skipped
    (tmp_path / "TS_01_allviews0.mrc.mdoc").touch()
    (tmp_path / "TS_01_cutviews0.mrc.mdoc").touch()

    return tmp_path, [regular_mrc]


def test_from_path_directory_yields_all_mdocs(ts_dir_with_mdocs):
    """from_path on a directory yields TiltSeries for all .mdoc files."""
    directory, expected_paths = ts_dir_with_mdocs

    result = list(TiltSeries.from_path(directory))

    assert len(result) == 2
    assert all(isinstance(ts, TiltSeries) for ts in result)
    result_paths = {ts.path for ts in result}
    assert result_paths == set(expected_paths)


def test_from_path_directory_excludes_allviews_cutviews(ts_dir_with_excluded_mdocs):
    """from_path on a directory skips allviews and cutviews .mdoc files."""
    directory, expected_paths = ts_dir_with_excluded_mdocs

    result = list(TiltSeries.from_path(directory))

    assert len(result) == 1
    assert result[0].path == expected_paths[0]


def test_from_path_directory_empty(tmp_path):
    """from_path on an empty directory yields nothing."""
    result = list(TiltSeries.from_path(tmp_path))
    assert len(result) == 0


def test_from_path_mrc_file(tmp_path):
    """from_path on an .mrc file yields a single TiltSeries."""
    mrc = tmp_path / "TS_01.mrc"
    mrc.touch()

    result = list(TiltSeries.from_path(mrc))

    assert len(result) == 1
    assert result[0].path == mrc


def test_from_path_st_file(tmp_path):
    """from_path on a .st file yields a single TiltSeries."""
    st = tmp_path / "TS_01.st"
    st.touch()

    result = list(TiltSeries.from_path(st))

    assert len(result) == 1
    assert result[0].path == st


def test_from_path_mdoc_file_resolves_to_base(tmp_path):
    """from_path on a .mdoc file resolves to the base file and yields TiltSeries."""
    mrc = tmp_path / "TS_01.mrc"
    mdoc = tmp_path / "TS_01.mrc.mdoc"
    mrc.touch()
    mdoc.touch()

    result = list(TiltSeries.from_path(mdoc))

    assert len(result) == 1
    assert result[0].path == mrc


def test_from_path_text_file_lists_paths(tmp_path):
    """from_path on a text file with path listings yields TiltSeries for each."""
    mrc1 = tmp_path / "series_01.mrc"
    mrc2 = tmp_path / "series_02.mrc"
    mrc1.touch()
    mrc2.touch()

    # Create a text file listing the paths
    listing = tmp_path / "series_list.txt"
    listing.write_text(f"{mrc1}\n{mrc2}\n")

    result = list(TiltSeries.from_path(listing))

    assert len(result) == 2
    result_paths = {ts.path for ts in result}
    assert result_paths == {mrc1, mrc2}


def test_from_path_text_file_ignores_blank_lines(tmp_path):
    """from_path on text file skips blank lines."""
    mrc = tmp_path / "series.mrc"
    mrc.touch()

    listing = tmp_path / "listing.txt"
    listing.write_text(f"\n{mrc}\n\n  \n")

    result = list(TiltSeries.from_path(listing))

    assert len(result) == 1
    assert result[0].path == mrc


def test_from_path_nonexistent_path():
    """from_path on a nonexistent path raises FileNotFoundError."""
    nonexistent = Path("/nonexistent/path/file.mrc")

    # The from_path method itself doesn't validate; it delegates to _from_file or _from_dir
    # which will raise when accessed. Let's check that calling list() triggers the error.
    with pytest.raises(FileNotFoundError):
        list(TiltSeries.from_path(nonexistent))


def test_from_dir_not_a_directory(tmp_path):
    """_from_dir on a non-directory raises NotADirectoryError."""
    file_path = tmp_path / "file.mrc"
    file_path.touch()

    with pytest.raises(NotADirectoryError):
        list(TiltSeries._from_dir(file_path))


def test_from_file_missing_file():
    """_from_file on a missing file raises FileNotFoundError."""
    missing = Path("/tmp/nonexistent_12345.mrc")

    with pytest.raises(FileNotFoundError):
        list(TiltSeries._from_file(missing))


def test_from_file_unknown_suffix_as_textfile(tmp_path):
    """_from_file on unknown suffix treats it as a text file listing paths."""
    mrc = tmp_path / "TS_01.mrc"
    mrc.touch()

    # Create a file with unknown suffix that lists paths
    listing = tmp_path / "series.custom"
    listing.write_text(f"{mrc}\n")

    result = list(TiltSeries._from_file(listing))

    assert len(result) == 1
    assert result[0].path == mrc


def test_from_path_nested_text_file(tmp_path):
    """from_path on text file can reference other text files (recursive)."""
    mrc = tmp_path / "TS_01.mrc"
    mrc.touch()

    # Create a secondary listing
    secondary = tmp_path / "secondary.txt"
    secondary.write_text(f"{mrc}\n")

    # Create a primary listing that references the secondary
    primary = tmp_path / "primary.txt"
    primary.write_text(f"{secondary}\n")

    result = list(TiltSeries.from_path(primary))

    assert len(result) == 1
    assert result[0].path == mrc


def test_from_path_mdoc_without_corresponding_mrc(tmp_path):
    """from_path on .mdoc without corresponding .mrc file raises FileNotFoundError."""
    mdoc = tmp_path / "TS_01.mrc.mdoc"
    mdoc.touch()
    # No corresponding .mrc file

    with pytest.raises(FileNotFoundError):
        list(TiltSeries.from_path(mdoc))
