"""Phase 14: lake dataset identity, atomic manifests, verify, snapshot and restore (ADR-070)."""

import io
import json
import tarfile

import pandas as pd
import pytest

from marketscope_research import provenance
from marketscope_research.lake import store
from marketscope_research.lake.parse import Entry

GROUPS = [["pinnacle"], ["draftkings"]]


def entries(shift=0.0):
    return [Entry("pinnacle", 100, 100, "2026-10-10T08:00:00.000Z", 1.91 + shift, True, 500.0, 1),
            Entry("pinnacle", 100, 101, "2026-10-10T08:00:00.000Z", 1.91, True, 500.0, 2)]


def markets():
    return pd.DataFrame({"market_id": [100, 100], "market_type": "spreads", "handicap": -3.0,
                         "outcome_id": [100, 101], "outcome_name": ["1", "2"]})


def build(root, fixture="f1", shift=0.0):
    cat = store.write_markets(markets(), root)
    store.write_fixture(fixture, entries(shift), root)
    facts = store.fixture_facts(fixture, root)
    store.record_fixture({"fixture_id": fixture, "event_id": "e", "kickoff": "2026-10-11T17:00:00.000Z",
                          "home": "H", "away": "A", **facts, "request_groups": json.dumps(GROUPS),
                          "books_missing": "draftkings", "catalog_sha256": cat}, root)
    return store.read_manifest(root)


def test_dataset_id_depends_on_content_not_build_time(tmp_path):
    a = build(tmp_path / "a")
    b = build(tmp_path / "b")
    assert store.dataset_id(a) == store.dataset_id(b)
    c = build(tmp_path / "c", shift=0.01)
    assert store.dataset_id(c) != store.dataset_id(a)
    assert store.dataset_id(a.iloc[::-1]) == store.dataset_id(a)  # manifest row order does not matter


def test_catalog_hash_ignores_row_order_and_keeps_a_copy(tmp_path):
    m = markets()
    assert store.catalog_sha256(m) == store.catalog_sha256(m.iloc[::-1])
    sha = store.write_markets(m, tmp_path)
    assert (tmp_path / "catalogs" / f"{sha}.parquet").exists()


def test_manifest_write_is_atomic(tmp_path, monkeypatch):
    build(tmp_path)
    before = store.read_manifest(tmp_path)

    def crash(self, path, *a, **k):
        with open(path, "wb") as fh:
            fh.write(b"half a file")
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", crash)
    with pytest.raises(OSError):
        store.record_fixture({"fixture_id": "f2", "rows": 1}, tmp_path)
    monkeypatch.undo()
    assert store.read_manifest(tmp_path)[["fixture_id", "file_sha256"]].equals(before[["fixture_id", "file_sha256"]])


def test_an_interrupted_build_is_visible_and_resumes_to_the_same_id(tmp_path):
    full = build(tmp_path / "full")
    root = tmp_path / "cut"
    store.write_markets(markets(), root)
    store.write_fixture("f1", entries(), root)  # killed before the manifest was written
    assert store.verify(root) == ["unrecorded file fixture=f1.parquet"]
    resumed = build(root)
    assert store.verify(root) == [] and store.dataset_id(resumed) == store.dataset_id(full)


def test_verify_catches_a_changed_file(tmp_path):
    build(tmp_path)
    store.write_fixture("f1", entries(shift=0.5), tmp_path)  # rewritten without recording
    assert store.verify(tmp_path) == ["file changed for f1"]


def test_snapshot_and_restore_round_trip(tmp_path):
    m = build(tmp_path / "lake")
    archive = store.snapshot(tmp_path / "snap", tmp_path / "lake")
    assert archive.name == f"{store.dataset_id(m)}.tar"
    assert store.restore(archive, tmp_path / "restored") == store.dataset_id(m)


def test_restore_refuses_a_tampered_archive(tmp_path):
    build(tmp_path / "lake")
    archive = store.snapshot(tmp_path / "snap", tmp_path / "lake")
    bad = tmp_path / "bad.tar"
    with tarfile.open(archive) as src, tarfile.open(bad, "w") as dst:
        for member in src.getmembers():
            data = src.extractfile(member).read()
            if member.name.startswith("entries/"):
                data = data[:-8] + b"tampered"
            member.size = len(data)
            dst.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match="differs"):
        store.restore(bad, tmp_path / "restored")


def test_snapshot_refuses_a_lake_that_does_not_verify(tmp_path):
    build(tmp_path)
    (tmp_path / "entries" / "fixture=f1.parquet").unlink()
    with pytest.raises(ValueError, match="does not verify"):
        store.snapshot(tmp_path / "snap", tmp_path)


def test_upgrade_fills_v2_fields_for_older_fixtures(tmp_path):
    store.write_markets(markets(), tmp_path)
    store.write_fixture("old", entries(), tmp_path)
    old = pd.DataFrame([{"fixture_id": "old", "event_id": "e", "kickoff": "2026-10-11T17:00:00.000Z", "home": "H",
                         "away": "A", "rows": 2, "books": "pinnacle", "version": 1, "built_at": "2026-10-21"}])
    old.to_parquet(tmp_path / "manifest.parquet", index=False)  # a v1 manifest
    assert store.upgrade_manifest(GROUPS, tmp_path) == 1
    m = store.read_manifest(tmp_path)
    assert m["transform_version"].iloc[0] == 1 and m["books_missing"].iloc[0] == "draftkings"
    assert m["file_sha256"].iloc[0] == store.sha256_file(tmp_path / "entries" / "fixture=old.parquet")
    assert store.verify(tmp_path) == [] and store.upgrade_manifest(GROUPS, tmp_path) == 0


def test_run_record_and_frame_hash(tmp_path, monkeypatch):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert provenance.frame_sha256(df) == provenance.frame_sha256(df.iloc[::-1])
    assert provenance.frame_sha256(df) != provenance.frame_sha256(df.assign(a=[1, 3]))
    params = tmp_path / "p.json"
    params.write_text("{}")
    rec = provenance.run_record("demo", [{"kind": "db", "sha256": provenance.frame_sha256(df)}], [params],
                                ["ghost rule"])
    assert len(rec["git_commit"]) == 40 and isinstance(rec["git_dirty"], bool)
    assert rec["params"]["p.json"] == store.sha256_file(params) and rec["packages"]["pandas"]
    out = provenance.write_run_record(tmp_path / "report.md", rec)
    assert out.name == "report.run.json" and json.loads(out.read_text())["study"] == "demo"


def test_streamed_batches_write_the_same_bytes_as_one_list(tmp_path, monkeypatch):
    many = [Entry("pinnacle" if i % 2 else "draftkings", 100 + i % 3, 100 + i % 2,
                  f"2026-10-10T08:{i % 60:02d}:00.000Z", 1.5 + i / 100, True, None, i) for i in range(23)]
    store.write_fixture("one", many, tmp_path / "a")
    monkeypatch.setattr(store, "BATCH_ROWS", 4)
    store.write_fixture("one", iter(many), tmp_path / "b")
    a, b = (store.sha256_file(tmp_path / d / "entries" / "fixture=one.parquet") for d in "ab")
    assert a == b
    assert store.write_fixture("empty", iter([]), tmp_path / "c") == 0


def test_generated_outputs_do_not_make_the_tree_dirty(tmp_path, monkeypatch):
    out = {"status": " M research/reports/x.md\n M apps/web/lib/generated/y.json\n M docs/DECISIONS.md\n",
           "code": " M research/src/a.py\n"}

    def fake(cmd, text=True):
        return "abc\n" if "rev-parse" in cmd else out[mode]

    monkeypatch.setattr(provenance.subprocess, "check_output", fake)
    mode = "status"
    assert provenance.git_state() == ("abc", False)
    mode = "code"
    assert provenance.git_state() == ("abc", True)
