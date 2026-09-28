"""Offline tests for immutable Hub loading."""
import sys
from types import SimpleNamespace

import pytest

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


def test_v2_config_maps_to_v2_paths(monkeypatch):
    call = {}

    def fake_download(**kwargs):
        call.update(kwargs)
        return "/tmp/v2.parquet"

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fake_download))
    monkeypatch.setattr(data, "_rows_from_parquet", lambda path: [])
    data.load_records("test", config="v2")
    assert call["filename"] == "v2/test.parquet"


def test_v2_events_and_provenance_paths(monkeypatch):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return "/tmp/v2.parquet"

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fake_download))
    monkeypatch.setattr(data, "_rows_from_parquet", lambda path: [])
    data.load_events()
    data.load_provenance(config="v2")
    assert [c["filename"] for c in calls] == ["v2/events.parquet", "v2/provenance.parquet"]
    assert all(c["revision"] == DEFAULT_REVISION for c in calls)


def test_missing_hub_extra_names_the_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    for load in (data.load_records, data.load_events, data.load_provenance):
        with pytest.raises(ImportError, match=r"ctdbench\[hf\]"):
            load()


def test_unknown_config_is_rejected():
    with pytest.raises(ValueError, match="config must be one of"):
        data.load_provenance(config="v3")
