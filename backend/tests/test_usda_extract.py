"""The USDA archive is extracted whole or not at all.

`_usda_csv_paths` skips extraction once the release directory exists, so an
extraction cut off halfway used to leave a directory of missing and empty CSVs
that every later run loaded as the release. No network here: `cached_download`
is replaced, and the archive is a small zip built in the test's own directory.
"""

import zipfile

import pytest

from etl import run_all

RELEASE = run_all.USDA_CSV_DIRNAME
# In the order `_usda_csv_paths` returns them, and the order they are zipped.
FILES = {
    "food.csv": b'"fdc_id","description"\n"321358","Hummus, commercial"\n',
    "nutrient.csv": b'"id","name","unit_name"\n"1178","Vitamin B-12","UG"\n',
    "food_nutrient.csv": b'"id","fdc_id","nutrient_id","amount"\n"1","321358","1178","0.25"\n',
}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """`_usda_csv_paths` extracts beside the zip `cached_download` hands it, so a
    zip in tmp_path keeps the whole extraction there."""
    monkeypatch.setattr(run_all, "cached_download", lambda url, filename: tmp_path / filename)
    return tmp_path


def _archive(cache, *, damaged: bool = False) -> None:
    """Write the release as usda_foundation_food.zip, stored uncompressed.

    `damaged` changes a byte of food_nutrient.csv, the last member, after its
    checksum was recorded. Extraction then writes the first two files and fails
    on the third, as it would on a full disk or a corrupt download.
    """
    path = cache / "usda_foundation_food.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        for name, data in FILES.items():
            archive.writestr(f"{RELEASE}/{name}", data)
    if damaged:
        raw = path.read_bytes()
        assert raw.count(b'"0.25"') == 1
        path.write_bytes(raw.replace(b'"0.25"', b'"9.25"'))


def test_an_extraction_cut_off_midway_leaves_no_release_directory(cache):
    _archive(cache, damaged=True)

    with pytest.raises(zipfile.BadZipFile):
        run_all._usda_csv_paths()

    assert not (cache / "usda_foundation_food" / RELEASE).exists()
    assert sorted(entry.name for entry in cache.iterdir()) == ["usda_foundation_food.zip"]


def test_the_next_run_extracts_again_instead_of_trusting_a_fragment(cache):
    _archive(cache, damaged=True)
    with pytest.raises(zipfile.BadZipFile):
        run_all._usda_csv_paths()

    _archive(cache)
    paths = run_all._usda_csv_paths()

    assert paths == tuple(cache / "usda_foundation_food" / RELEASE / name for name in FILES)
    assert [path.read_bytes() for path in paths] == list(FILES.values())


def test_a_part_directory_left_by_a_killed_run_is_replaced(cache):
    """A process killed mid-extraction never reaches its cleanup, so the next run
    finds the .part directory. It is never trusted, and a finished extraction
    replaces it."""
    fragment = cache / "usda_foundation_food.part" / RELEASE
    fragment.mkdir(parents=True)
    (fragment / "food.csv").write_bytes(b'"fdc_id","descr')
    _archive(cache)

    paths = run_all._usda_csv_paths()

    assert [path.read_bytes() for path in paths] == list(FILES.values())
    assert sorted(entry.name for entry in cache.iterdir()) == [
        "usda_foundation_food",
        "usda_foundation_food.zip",
    ]


def test_a_finished_extraction_is_reused_without_opening_the_archive(cache):
    _archive(cache)
    run_all._usda_csv_paths()
    (cache / "usda_foundation_food.zip").write_bytes(b"not a zip")

    paths = run_all._usda_csv_paths()

    assert [path.read_bytes() for path in paths] == list(FILES.values())
