"""Load the clinical-trial decision benchmark splits.

By default the splits are pulled from the Hugging Face Hub (the published, versioned artifact). A local
Parquet directory can be used instead for offline runs. Only ``pyarrow`` is required for the local path;
``huggingface_hub`` is an optional extra used for the Hub path.
"""
import os
import pyarrow.parquet as pq

REPO_ID = "jang1563/clinical-trial-decision-benchmark"
DEFAULT_REVISION = "a3869c1bf76f99b3873e1f23c09796c3f6c757b5"
SPLITS = ("train", "test", "full")
CONFIGS = {"default": "data", "v2": "v2"}
PROVENANCE_FILE = "provenance/provenance.parquet"
V2_PROVENANCE_FILE = "v2/provenance.parquet"
V2_EVENTS_FILE = "v2/events.parquet"
DECISIVE_LABELS = ("advance", "stop")


def _rows_from_parquet(path):
    tbl = pq.read_table(path)
    cols = tbl.column_names
    data = tbl.to_pydict()
    n = tbl.num_rows
    return [{c: data[c][i] for c in cols} for i in range(n)]


def load_records(split="test", local_dir=None, revision=DEFAULT_REVISION, config="default"):
    """Return one record dict per trial from a pinned Hub revision or local directory.

    ``config`` selects the gold: ``"default"`` is the v1.1 source-derived label set (``data/``),
    ``"v2"`` the event-anchored label set (``v2/``, drug trials with phase 1–3; other trials are
    abstained). A ``local_dir`` is read as-is, whatever config it holds.
    """
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    if config not in CONFIGS:
        raise ValueError(f"config must be one of {tuple(CONFIGS)}, got {config!r}")
    if local_dir:
        path = os.path.join(local_dir, f"{split}.parquet")
    else:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as e:
            raise ImportError("pip install 'ctdbench[hf]' to load from the Hub, or pass local_dir=") from e
        path = hf_hub_download(
            repo_id=REPO_ID,
            filename=f"{CONFIGS[config]}/{split}.parquet",
            repo_type="dataset",
            revision=revision,
        )
    return _rows_from_parquet(path)


def load_gold(
    split="test",
    local_dir=None,
    id_field="nct_id",
    label_field="label",
    revision=DEFAULT_REVISION,
    decisive_only=True,
    config="default",
):
    """Return ``{nct_id: label}`` for the confidently-labelled trials (abstained rows dropped).

    ``verify`` has only 6 test rows, so a single row moves 3-class balanced accuracy by several
    points. By default the gold set is therefore restricted to the decisive ``advance`` / ``stop``
    labels, as the dataset card recommends; pass ``decisive_only=False`` to keep ``verify``.
    """
    gold = {}
    for r in load_records(split, local_dir=local_dir, revision=revision, config=config):
        lab = r.get(label_field)
        if r.get("abstained") is True or lab in (None, "", "null"):
            continue
        if decisive_only and lab not in DECISIVE_LABELS:
            continue
        gold[r[id_field]] = lab
    return gold


def load_events(local_dir=None, revision=DEFAULT_REVISION):
    """Return ``{nct_id: {signal columns}}`` from the v2 ``events`` config (E1–E6 signal values)."""
    if local_dir:
        path = os.path.join(local_dir, "events.parquet")
    else:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(repo_id=REPO_ID, filename=V2_EVENTS_FILE, repo_type="dataset", revision=revision)
    return {r["nct_id"]: r for r in _rows_from_parquet(path)}


def load_provenance(local_dir=None, revision=DEFAULT_REVISION, config="default"):
    """Return ``{nct_id: {"label_source": ..., "regulatory_signal": ...}}`` for all trials.

    From v1.1 these columns live in ``provenance/provenance.parquet`` and are not part of the
    scoring tables, because ``label_source`` encodes the labeling rule and recovers the label
    almost exactly. They document how each label was derived and must not be given to a model.
    For the v1.0 revision, which still carried the columns inside the data tables, the values are
    read from ``full.parquet`` instead.
    """
    if config == "v2":
        if local_dir:
            path = os.path.join(local_dir, "provenance.parquet")
        else:
            from huggingface_hub import hf_hub_download

            path = hf_hub_download(repo_id=REPO_ID, filename=V2_PROVENANCE_FILE, repo_type="dataset", revision=revision)
        return {r["nct_id"]: r for r in _rows_from_parquet(path)}
    if local_dir:
        path = os.path.join(local_dir, PROVENANCE_FILE)
        if not os.path.exists(path):
            path = None
    else:
        from huggingface_hub import hf_hub_download

        try:
            path = hf_hub_download(
                repo_id=REPO_ID, filename=PROVENANCE_FILE, repo_type="dataset", revision=revision
            )
        except Exception:  # noqa: BLE001 - v1.0 revisions have no provenance file
            path = None
    if path:
        rows = _rows_from_parquet(path)
    else:
        rows = load_records("full", local_dir=local_dir, revision=revision)
        if rows and "label_source" not in rows[0]:
            raise ValueError("no provenance file and no provenance columns at this revision")
    return {
        r["nct_id"]: {
            "label_source": r.get("label_source"),
            "regulatory_signal": r.get("regulatory_signal"),
        }
        for r in rows
    }
