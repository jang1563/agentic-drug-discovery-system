"""Offline tests for immutable Hub loading."""
import sys
from types import SimpleNamespace

from ctdbench import DEFAULT_REVISION
from ctdbench import data


def test_hub_load_forwards_pinned_revision(monkeypatch):
    call = {}

    def fake_download(**kwargs):
        call.update(kwargs)
        return "/tmp/test.parquet"

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(hf_hub_download=fake_download),
    )
    monkeypatch.setattr(data, "_rows_from_parquet", lambda path: [{"path": path}])

    rows = data.load_records("test")
    assert rows == [{"path": "/tmp/test.parquet"}]
    assert call == {
        "repo_id": data.REPO_ID,
        "filename": "data/test.parquet",
        "repo_type": "dataset",
        "revision": DEFAULT_REVISION,
    }


def test_hub_load_accepts_explicit_revision(monkeypatch):
    call = {}

    def fake_download(**kwargs):
        call.update(kwargs)
        return "/tmp/train.parquet"

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(hf_hub_download=fake_download),
    )
    monkeypatch.setattr(data, "_rows_from_parquet", lambda path: [])

    data.load_records("train", revision="release-2026-07")
    assert call["revision"] == "release-2026-07"
