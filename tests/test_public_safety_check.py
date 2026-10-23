"""Public safety gate against a throwaway git repo (fictional data, built at runtime)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import public_safety_check as psc  # noqa: E402

# Built from pieces so this file itself never matches the patterns it tests.
FAKE_PHONE = "300" + "555" + "0101"
FAKE_GH_TOKEN = "gh" + "p_" + "A1b2C3d4" * 5
FAKE_PATH = "C:" + "\\Users\\" + "someone\\project"
FAKE_EMAIL = "maria.example" + "@" + "gmail.com"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "Test")
    (r / "README.md").write_text("# Demo\n", encoding="utf-8")
    (r / "LICENSE").write_text("Copyright (c) Maria Example\n", encoding="utf-8")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "init")
    terms = Path(_git(r, "rev-parse", "--absolute-git-dir").strip()) / "public_safety_terms.txt"
    terms.write_text("# personal terms\nMaria Example\nAcme Client\n", encoding="utf-8")
    return r


def _commit(repo: Path, name: str, content: str, msg: str = "change") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _run(repo: Path, *extra: str) -> int:
    return psc.main(["--repo", str(repo), *extra])


def test_clean_repo_passes_and_license_may_contain_the_name(repo):
    assert _run(repo) == 0


@pytest.mark.parametrize(("content", "category"), [
    (f"call me at {FAKE_PHONE}\n", "phone number"),
    (f"token = '{FAKE_GH_TOKEN}'\n", "GitHub token"),
    (f"path = r'{FAKE_PATH}'\n", "local user path"),
    (f"contact: {FAKE_EMAIL}\n", "personal email"),
    ("Built for maria example by hand\n", "personal term"),
    ("Proposal for ACME CLIENT\n", "personal term"),
])
def test_tree_findings_block(repo, capsys, content, category):
    _commit(repo, "notes.md", content)
    assert _run(repo) == 1
    assert category in capsys.readouterr().err


def test_blocked_paths(repo, capsys):
    _commit(repo, "knowledge/diario.md", "hola\n")
    assert _run(repo) == 1
    assert "blocked path" in capsys.readouterr().err


def test_empty_taskforge_placeholder_allowed(repo):
    _commit(repo, "data/taskforge/habits.json", "[]\n")
    assert _run(repo) == 0


def test_secret_added_then_removed_is_caught_in_history(repo, capsys):
    base = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "config.py", f"KEY = '{FAKE_GH_TOKEN}'\n")
    _commit(repo, "config.py", "KEY = None\n", msg="remove key")
    assert _run(repo) == 0                       # the final tree is clean...
    assert _run(repo, "--range", f"{base}..HEAD") == 1   # ...but the history is not
    assert "GitHub token" in capsys.readouterr().err


def test_personal_term_in_commit_message(repo, capsys):
    base = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "a.txt", "ok\n", msg="fix for Acme Client")
    assert _run(repo, "--range", f"{base}..HEAD") == 1
    assert "(message)" in capsys.readouterr().err


def test_pre_push_new_branch_scans_unpushed_commits(repo):
    _commit(repo, "b.txt", f"{FAKE_PHONE}\n")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    revs = psc.pre_push_revs(f"refs/heads/feat {sha} refs/heads/feat {psc.ZERO_SHA}\n")
    assert revs == [[sha, "--not", "--remotes"]]
    assert psc.pre_push_revs(f"(delete) {psc.ZERO_SHA} refs/heads/x abc\n") == []


def test_findings_are_masked(repo, capsys):
    _commit(repo, "c.py", f"T = '{FAKE_GH_TOKEN}'\n")
    _run(repo)
    assert FAKE_GH_TOKEN not in capsys.readouterr().err


def test_script_itself_passes_its_own_generic_patterns():
    """The gate ships in the public repo, so it must not trip on its own source."""
    source = Path(psc.__file__).read_text(encoding="utf-8")
    assert psc.scan_text(source, "script", None, "public_safety_check.py") == []


@pytest.mark.parametrize("user", ["<usuario>", "usuario", "user", "YourName"])
def test_placeholder_user_paths_are_allowed(repo, user):
    _commit(repo, "docs.md", "vault = " + "C:" + "/Users/" + user + "/MyVault\n")
    assert _run(repo) == 0


def test_allow_line_in_terms_file_permits_exact_text(repo, capsys):
    terms = Path(_git(repo, "rev-parse", "--absolute-git-dir").strip()) / "public_safety_terms.txt"
    terms.write_text("Acme Client\n!github.com/acme client/demo\n", encoding="utf-8")
    _commit(repo, "README.md", "git clone https://github.com/acme client/demo\n")
    assert _run(repo) == 0
    _commit(repo, "other.md", "Acme Client roadmap\n")
    assert _run(repo) == 1
    assert "personal term" in capsys.readouterr().err


def test_missing_terms_file_still_runs_generic_checks(repo, capsys):
    (Path(_git(repo, "rev-parse", "--absolute-git-dir").strip()) / "public_safety_terms.txt").unlink()
    _commit(repo, "d.txt", f"{FAKE_PHONE}\n")
    assert _run(repo) == 1
    assert "no personal terms file" in capsys.readouterr().err
