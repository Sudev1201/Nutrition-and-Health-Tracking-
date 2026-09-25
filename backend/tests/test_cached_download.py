"""The ETL's download cache never keeps a partial file.

`cached_download` trusts any file already at its path, so a download cut off
halfway used to leave a truncated source that every later run loaded. A short
IFCT CSV loads without complaint, just with fewer foods. No network here: the
stream is a fake.
"""

import contextlib

import httpx
import pytest

from etl import common

URL = "https://example.invalid/ifct_compositions.csv"
WHOLE = b"code,name\nA001,Amaranth seed\nA002,Bajra\n"


class _Response:
    def __init__(self, chunks: list[bytes], *, fail_after: int | None = None) -> None:
        self._chunks = chunks
        self._fail_after = fail_after

    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self):
        for n, chunk in enumerate(self._chunks):
            if n == self._fail_after:
                raise httpx.ReadError("the connection dropped")
            yield chunk


def _serve(monkeypatch, response: _Response) -> list[str]:
    """Answer every download with `response`; returns the URLs requested."""
    requested: list[str] = []

    @contextlib.contextmanager
    def stream(method, url, **kwargs):
        requested.append(url)
        yield response

    monkeypatch.setattr(common.httpx, "stream", stream)
    return requested


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "CACHE_DIR", tmp_path)
    return tmp_path


def test_a_download_cut_off_midway_leaves_nothing_behind(cache, monkeypatch):
    _serve(monkeypatch, _Response([b"code,name\n", b"A001,Amaranth seed\n"], fail_after=1))

    with pytest.raises(httpx.ReadError):
        common.cached_download(URL, "ifct_compositions.csv")

    assert not (cache / "ifct_compositions.csv").exists()
    assert list(cache.iterdir()) == []


def test_the_next_run_downloads_again_instead_of_trusting_a_fragment(cache, monkeypatch):
    _serve(monkeypatch, _Response([b"code,name\n", b"A001,Amaranth seed\n"], fail_after=1))
    with pytest.raises(httpx.ReadError):
        common.cached_download(URL, "ifct_compositions.csv")

    requested = _serve(monkeypatch, _Response([WHOLE]))
    path = common.cached_download(URL, "ifct_compositions.csv")

    assert requested == [URL]
    assert path == cache / "ifct_compositions.csv"
    assert path.read_bytes() == WHOLE


def test_a_part_file_left_by_a_killed_run_is_replaced(cache, monkeypatch):
    """A process killed mid-download never reaches its cleanup, so the next run
    finds the .part file. It is never trusted, and a finished download replaces it."""
    (cache / "ifct_compositions.csv.part").write_bytes(b"code,na")
    _serve(monkeypatch, _Response([WHOLE]))

    path = common.cached_download(URL, "ifct_compositions.csv")

    assert path.read_bytes() == WHOLE
    assert sorted(entry.name for entry in cache.iterdir()) == ["ifct_compositions.csv"]


def test_a_finished_download_is_reused_without_the_network(cache, monkeypatch):
    (cache / "ifct_compositions.csv").write_bytes(WHOLE)
    requested = _serve(monkeypatch, _Response([b"something else"]))

    path = common.cached_download(URL, "ifct_compositions.csv")

    assert requested == []
    assert path.read_bytes() == WHOLE
