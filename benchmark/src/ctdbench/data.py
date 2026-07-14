"""Load the clinical-trial decision benchmark splits.

By default the splits are pulled from the Hugging Face Hub (the published, versioned artifact). A local
Parquet directory can be used instead for offline runs. Only ``pyarrow`` is required for the local path;
``huggingface_hub`` is an optional extra used for the Hub path.
"""
import os
import pyarrow.parquet as pq

REPO_ID = "jang1563/clinical-trial-decision-benchmark"
DEFAULT_REVISION = "bfc610ae643c7adbb01994115bce470222c25e8f"
SPLITS = ("train", "test", "full")


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
):
    """Return ``{nct_id: label}`` for the confidently-labelled trials only (abstained rows dropped)."""
    gold = {}
    for r in load_records(split, local_dir=local_dir, revision=revision):
        lab = r.get(label_field)
        if r.get("abstained") is True or lab in (None, "", "null"):
            continue
        gold[r[id_field]] = lab
    return gold
