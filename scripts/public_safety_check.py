"""Public safety gate: block a push that would publish personal data or secrets.

Scans (1) every tracked file at HEAD and (2) every commit being pushed (added lines,
file names and commit messages), so something added in one commit and deleted in the
next is still caught. Exits 1 on any finding.

Generic patterns live here. Personal terms (your name, family, clients, habit names)
live OUTSIDE the repo, in <git-dir>/public_safety_terms.txt (one term per line,
'#' comments allowed), so this file never contains them. Name-like terms are allowed
in LICENSE only.

    python scripts/public_safety_check.py                  # scan tracked files
    python scripts/public_safety_check.py --range main..HEAD
    python scripts/public_safety_check.py --pre-push origin URL < refs   # git pre-push hook
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ZERO_SHA = "0" * 40
MAX_BYTES = 2_000_000
TERM_ALLOWED_FILES = {"LICENSE"}

BLOCKED_PATHS = (
    "knowledge/", "data/taskforge/", "data/family_progress.json", "data/family_routines.json",
    "data/marketing_leads_db.json", "data/fitness/", "data/whatsapp_session", "data/chromadb/",
    "evals/private/", "pruebas/", "tasks.txt", ".env", "observability/.env", "mcp_servers.json",
    "memory_store.json", "token.json", "credentials.json",
)
# Placeholders that are allowed to exist publicly inside blocked folders.
ALLOWED_PATHS = {".env.example", "knowledge/README.md", "knowledge/prs/.gitkeep", "data/documents/.gitkeep"}
ALLOWED_EMPTY_JSON = "[]"

PATTERNS: dict[str, re.Pattern] = {
    "phone number": re.compile(r"(?<![\w.])(?:\+?57[ -]?)?3\d{2}[ -]?\d{3}[ -]?\d{4}(?![\w])"),
    "personal email": re.compile(r"[\w.+-]+@(?:gmail|hotmail|outlook|live|yahoo|icloud|protonmail)\.[a-z.]+", re.I),
    "local user path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<)[\w.-]+", re.I),
    "OpenAI/Anthropic key": re.compile(r"\bsk-(?:ant-|proj-|lf-)?[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    "Telegram bot token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}


@dataclass(frozen=True)
class Finding:
    where: str
    category: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.where}: {self.category}: {self.excerpt}"


def git(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=True)
    return out.stdout


def mask(text: str) -> str:
    """Show enough to locate a finding without echoing a full secret."""
    text = text.strip()
    return text if len(text) <= 8 else f"{text[:4]}…{text[-2:]}"


def load_terms(repo: Path, terms_file: Path | None = None) -> list[str]:
    path = terms_file or Path(git("rev-parse", "--absolute-git-dir", cwd=repo).strip()) / "public_safety_terms.txt"
    if not path.exists():
        return []
    lines = (ln.strip() for ln in path.read_text(encoding="utf-8").splitlines())
    return [ln for ln in lines if ln and not ln.startswith("#")]


def _term_pattern(terms: list[str]) -> re.Pattern | None:
    if not terms:
        return None
    alts = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.I)


def scan_text(text: str, where: str, term_re: re.Pattern | None, path: str) -> list[Finding]:
    findings = []
    for n, line in enumerate(text.splitlines(), start=1):
        for category, pattern in PATTERNS.items():
            for m in pattern.finditer(line):
                findings.append(Finding(f"{where}:{n}", category, mask(m.group())))
        if term_re and Path(path).name not in TERM_ALLOWED_FILES:
            for m in term_re.finditer(line):
                findings.append(Finding(f"{where}:{n}", "personal term", mask(m.group())))
    return findings


def blocked(path: str, content: str | None = None) -> bool:
    if path in ALLOWED_PATHS:
        return False
    if path.startswith("data/taskforge/") and content is not None and content.strip() == ALLOWED_EMPTY_JSON:
        return False  # empty placeholders are fine
    return any(path == p.rstrip("/") or path.startswith(p) for p in BLOCKED_PATHS)


def scan_tree(repo: Path, term_re: re.Pattern | None) -> list[Finding]:
    findings = []
    for path in git("ls-files", cwd=repo).splitlines():
        file = repo / path
        if not file.is_file() or file.stat().st_size > MAX_BYTES:
            continue
        data = file.read_bytes()
        if b"\0" in data[:4096]:
            continue  # binary
        text = data.decode("utf-8", errors="replace")
        if blocked(path, text):
            findings.append(Finding(path, "blocked path", "must never be public"))
        findings += scan_text(text, path, term_re, path)
        if term_re and term_re.search(path):
            findings.append(Finding(path, "personal term in file name", path))
    return findings


def scan_commits(repo: Path, rev_args: list[str], term_re: re.Pattern | None) -> list[Finding]:
    """Added lines, file names and messages of every commit in the range."""
    log = git("log", "-p", "--no-color", "--format=@@COMMIT %h%n%B", *rev_args, "--", cwd=repo)
    findings, commit, path = [], "?", ""
    for line in log.splitlines():
        if line.startswith("@@COMMIT "):
            commit, path = line.split()[1], "(message)"
            continue
        if line.startswith("+++ b/"):
            path = line[6:]
            if blocked(path):
                findings.append(Finding(f"{commit}:{path}", "blocked path in history", "must never be public"))
            continue
        if line.startswith(("diff --git", "--- ", "index ", "@@ ", "new file", "deleted file", "similarity", "rename ")):
            continue
        if path == "(message)" or (line.startswith("+") and not line.startswith("+++")):
            text = line[1:] if line.startswith("+") else line
            findings += [Finding(f"{commit}:{path}", f.category, f.excerpt)
                         for f in scan_text(text, "", term_re, path)]
    return findings


def pre_push_revs(stdin_text: str) -> list[list[str]]:
    """Translate git's pre-push stdin into rev-list arguments for the commits being pushed."""
    revs = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO_SHA:
            continue  # malformed or branch deletion
        local_sha, remote_sha = parts[1], parts[3]
        revs.append([f"{remote_sha}..{local_sha}"] if remote_sha != ZERO_SHA else [local_sha, "--not", "--remotes"])
    return revs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block publishing personal data or secrets.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--range", help="also scan the commits in this range, e.g. main..HEAD")
    parser.add_argument("--terms", type=Path, help="personal terms file (default: <git-dir>/public_safety_terms.txt)")
    parser.add_argument("--pre-push", nargs="*", metavar="ARG", help="run as git pre-push hook (reads refs on stdin)")
    args = parser.parse_args(argv)

    repo = Path(git("rev-parse", "--show-toplevel", cwd=args.repo).strip())
    terms = load_terms(repo, args.terms)
    term_re = _term_pattern(terms)
    findings = scan_tree(repo, term_re)
    rev_sets = pre_push_revs(sys.stdin.read()) if args.pre_push is not None else []
    if args.range:
        rev_sets.append([args.range])
    for revs in rev_sets:
        findings += scan_commits(repo, revs, term_re)

    if not terms:
        print("WARNING: no personal terms file; only generic patterns were checked.", file=sys.stderr)
    if findings:
        print(f"PUBLIC SAFETY CHECK FAILED: {len(findings)} finding(s)", file=sys.stderr)
        for f in dict.fromkeys(findings):
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"Public safety check passed ({len(terms)} personal terms, {len(rev_sets)} commit range(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
