"""The metadata probe must expose a column that encodes the label and stay near floor otherwise."""
import os

import pyarrow as pa
import pyarrow.parquet as pq

from ctdbench import load_gold, load_provenance, probe_columns


def _write(tmp_path):
    rows = []
    for i in range(80):
        label = ("advance", "stop")[i % 2] if i % 10 else "verify"
        rows.append({
            "nct_id": f"NCT{i:08d}",
            "condition": f"cond{i % 7}",
            "label": label,
            "leaky": f"rule-{label}",
            "phase": ("PHASE1", "PHASE2", "PHASE3")[i % 3],
            "primary_completion_date": f"{2000 + i % 20}-01-01",
            "enrollment": 10 + (i * 37) % 500,
            "split": "train" if i < 56 else "test",
            "abstained": False,
        })
    os.makedirs(os.path.join(tmp_path, "data"))
    for split in ("train", "test"):
        part = [r for r in rows if r["split"] == split]
        pq.write_table(pa.Table.from_pylist(part), os.path.join(tmp_path, f"{split}.parquet"))
    pq.write_table(pa.Table.from_pylist(rows), os.path.join(tmp_path, "full.parquet"))
    return rows


def test_probe_flags_a_label_encoding_column(tmp_path):
    _write(tmp_path)
    from ctdbench import load_records
    train = load_records("train", local_dir=str(tmp_path))
    test = load_records("test", local_dir=str(tmp_path))
    report = probe_columns(train, test, permutations=200)
    by = {c["column"]: c for c in report["columns"]}
    assert report["columns"][0]["column"] == "leaky"
    assert by["leaky"]["balanced_accuracy_decisive"] == 1.0
    assert by["leaky"]["permutation_p_decisive"] < 0.01
    assert by["split"]["balanced_accuracy_decisive"] == 0.5
    assert "label" not in by and "abstained" not in by


def test_load_gold_defaults_to_decisive_labels(tmp_path):
    _write(tmp_path)
    decisive = load_gold("test", local_dir=str(tmp_path))
    everything = load_gold("test", local_dir=str(tmp_path), decisive_only=False)
    assert set(decisive.values()) == {"advance", "stop"}
    assert "verify" in set(everything.values())
    assert len(everything) > len(decisive)


def test_load_provenance_prefers_the_provenance_file(tmp_path):
    rows = _write(tmp_path)
    os.makedirs(os.path.join(tmp_path, "provenance"))
    prov = [{"nct_id": r["nct_id"], "split": r["split"], "label_source": "S1", "regulatory_signal": None}
            for r in rows]
    pq.write_table(pa.Table.from_pylist(prov), os.path.join(tmp_path, "provenance", "provenance.parquet"))
    out = load_provenance(local_dir=str(tmp_path))
    assert len(out) == len(rows)
    assert out[rows[0]["nct_id"]] == {"label_source": "S1", "regulatory_signal": None}
