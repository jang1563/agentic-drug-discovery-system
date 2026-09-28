"""Load the clinical-trial decision benchmark splits.

By default the splits are pulled from the Hugging Face Hub (the published, versioned artifact). A local
Parquet directory can be used instead for offline runs. Only ``pyarrow`` is required for the local path;
``huggingface_hub`` is an optional extra used for the Hub path.
"""
import os
import pyarrow.parquet as pq

REPO_ID = "jang1563/clinical-trial-decision-benchmark"
DEFAULT_REVISION = "f2ce03ed9aa3ff1db69003f82eb7f9247580b5fa"
SPLITS = ("train", "test", "full")
PROVENANCE_FILE = "provenance/provenance.parquet"
DECISIVE_LABELS = ("advance", "stop")


def _rows_from_parquet(path):
    tbl = pq.read_table(path)
    cols = tbl.column_names
    data = tbl.to_pydict()
    n = tbl.num_rows
    return [{c: data[c][i] for c in cols} for i in range(n)]


def load_records(split="test", local_dir=None, revision=DEFAULT_REVISION):
    """Return one record dict per trial from a pinned Hub revision or local directory."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    if local_dir:
        path = os.path.join(local_dir, f"{split}.parquet")
    else:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as e:
            raise ImportError("pip install 'ctdbench[hf]' to load from the Hub, or pass local_dir=") from e
        path = hf_hub_download(
            repo_id=REPO_ID,
            filename=f"data/{split}.parquet",
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
):
    """Return ``{nct_id: label}`` for the confidently-labelled trials (abstained rows dropped).

    ``verify`` has only 6 test rows, so a single row moves 3-class balanced accuracy by several
    points. By default the gold set is therefore restricted to the decisive ``advance`` / ``stop``
    labels, as the dataset card recommends; pass ``decisive_only=False`` to keep ``verify``.
    """
    gold = {}
    for r in load_records(split, local_dir=local_dir, revision=revision):
        lab = r.get(label_field)
        if r.get("abstained") is True or lab in (None, "", "null"):
            continue
        if decisive_only and lab not in DECISIVE_LABELS:
            continue
        gold[r[id_field]] = lab
    return gold


def load_provenance(local_dir=None, revision=DEFAULT_REVISION):
    """Return ``{nct_id: {"label_source": ..., "regulatory_signal": ...}}`` for all trials.

    From v1.1 these columns live in ``provenance/provenance.parquet`` and are not part of the
    scoring tables, because ``label_source`` encodes the labeling rule and recovers the label
    almost exactly. They document how each label was derived and must not be given to a model.
    For the v1.0 revision, which still carried the columns inside the data tables, the values are
    read from ``full.parquet`` instead.
    """
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
