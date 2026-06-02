"""Unit tests for the git_signals extractor (collect).

Hermetic: build a throwaway git repo under tmp_path with deterministic
commit dates so churn / last-modified / coupling assertions are stable.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from contract import FileIndex, FileRecord, detect_lang
from extractors.git_signals import collect


def _git(repo, *args, date=None):
    env = None
    if date is not None:
        import os

        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _commit(repo, msg, date):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg, date=date)


def _index_for(repo, rel_paths):
    records = []
    for i, p in enumerate(sorted(rel_paths), start=1):
        records.append(
            FileRecord(id=f"f{i:04d}", path=p, lang=detect_lang(p), loc=0, sizeBytes=0)
        )
    return FileIndex(records)


@pytest.fixture
def git_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git CLI not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")

    a = repo / "a.py"
    b = repo / "b.py"
    c = repo / "c.py"

    # commit 1: a + b together (co-change #1)
    a.write_text("a = 1\n")
    b.write_text("b = 1\n")
    _commit(repo, "init a b", "2020-01-01T00:00:00")

    # commit 2: a + b together again (co-change #2 -> coupling >= 2)
    a.write_text("a = 2\n")
    b.write_text("b = 2\n")
    _commit(repo, "touch a b", "2020-01-02T00:00:00")

    # commit 3: a + c together (co-change a/c only once -> excluded)
    a.write_text("a = 3\n")
    c.write_text("c = 1\n")
    _commit(repo, "touch a c", "2020-01-03T00:00:00")

    # commit 4: a alone (latest touch for a)
    a.write_text("a = 4\n")
    _commit(repo, "touch a", "2020-06-15T12:30:00")

    return repo


def test_churn_counts_commits_per_file(git_repo):
    idx = _index_for(git_repo, ["a.py", "b.py", "c.py"])
    churn, _, _ = collect(git_repo, idx)

    assert churn[idx.id_for_path("a.py")] == 4
    assert churn[idx.id_for_path("b.py")] == 2
    assert churn[idx.id_for_path("c.py")] == 1


def test_last_modified_is_iso_recent_commit(git_repo):
    idx = _index_for(git_repo, ["a.py", "b.py", "c.py"])
    _, last, _ = collect(git_repo, idx)

    a_last = last[idx.id_for_path("a.py")]
    assert "2020-06-15" in a_last  # latest commit touching a
    b_last = last[idx.id_for_path("b.py")]
    assert "2020-01-02" in b_last  # b last touched in commit 2


def test_coupling_keeps_pairs_with_two_co_changes(git_repo):
    idx = _index_for(git_repo, ["a.py", "b.py", "c.py"])
    _, _, coupling = collect(git_repo, idx)

    a_id = idx.id_for_path("a.py")
    b_id = idx.id_for_path("b.py")
    c_id = idx.id_for_path("c.py")

    # a/b co-changed twice -> present with count 2
    ab = [c for c in coupling if {c["a"], c["b"]} == {a_id, b_id}]
    assert len(ab) == 1
    assert ab[0]["coChangeCount"] == 2
    assert ab[0]["a"] < ab[0]["b"]  # a<b by id

    # a/c co-changed once -> excluded
    ac = [c for c in coupling if {c["a"], c["b"]} == {a_id, c_id}]
    assert ac == []


def test_coupling_sorted_by_a_then_b(git_repo):
    idx = _index_for(git_repo, ["a.py", "b.py", "c.py"])
    _, _, coupling = collect(git_repo, idx)
    keys = [(c["a"], c["b"]) for c in coupling]
    assert keys == sorted(keys)


def test_only_files_in_index_included(git_repo):
    # Index omits c.py entirely.
    idx = _index_for(git_repo, ["a.py", "b.py"])
    churn, last, coupling = collect(git_repo, idx)

    assert None not in churn
    assert None not in last
    for edge in coupling:
        assert edge["a"] is not None and edge["b"] is not None


def test_non_git_dir_returns_empty(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "x.py").write_text("x = 1\n")
    idx = _index_for(plain, ["x.py"])
    assert collect(plain, idx) == ({}, {}, [])


def test_determinism(git_repo):
    idx = _index_for(git_repo, ["a.py", "b.py", "c.py"])
    assert collect(git_repo, idx) == collect(git_repo, idx)
