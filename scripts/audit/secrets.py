"""Secret scanner — working tree + last N commits of git history.

Secret-scanning audit. Hybrid design:
  - If `gitleaks` is on PATH, delegate to it (battle-tested patterns).
  - Otherwise, fall back to a built-in regex set covering the high-signal
    patterns specific to THIS stack (OpenAI, Anthropic, Groq, Clerk,
    HuggingFace, Langfuse, AWS, GitHub PATs, generic JWT).

Output (stdout):
  - Default (text):     human-readable summary; rows are file:line:provider.
  - --json:             machine-readable JSON for future CI gating.

Exit codes:
  0 — clean (no findings beyond allowlisted patterns).
  1 — findings; merge / push should NOT proceed until triaged.
  2 — tool error (git not available, etc.).

Reports never include the matched secret string itself — only the file,
line number, and a hash. That way `audit-baseline.md` can be committed
without re-leaking the very thing we just detected.

Usage:
    uv run python scripts/audit/secrets.py
    uv run python scripts/audit/secrets.py --json
    uv run python scripts/audit/secrets.py --history 500
    uv run python scripts/audit/secrets.py --no-history
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

# ── Detection patterns ──────────────────────────────────────────────
# Each entry: (name, regex, group_index_for_match).
# Patterns are tuned for the stack — false-positive control is in
# _looks_like_placeholder() below.
PATTERNS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("openai_key", re.compile(r"\b(sk-[A-Za-z0-9_\-]{20,})"), 1),
    ("openai_proj", re.compile(r"\b(sk-proj-[A-Za-z0-9_\-]{20,})"), 1),
    ("anthropic_key", re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{40,})"), 1),
    ("groq_key", re.compile(r"\b(gsk_[A-Za-z0-9]{40,})"), 1),
    ("clerk_secret", re.compile(r"\b(sk_(?:test|live)_[A-Za-z0-9]{30,})"), 1),
    ("clerk_publishable", re.compile(r"\b(pk_(?:test|live)_[A-Za-z0-9]{30,})"), 1),
    ("huggingface_token", re.compile(r"\b(hf_[A-Za-z0-9]{30,})"), 1),
    ("langsmith_key", re.compile(r"\b(lsv2_pt_[A-Za-z0-9]{30,})"), 1),
    ("langfuse_key", re.compile(r"\b((?:sk|pk)-lf-[A-Za-z0-9\-]{30,})"), 1),
    ("aws_access_key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), 1),
    ("github_pat", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,})"), 1),
    (
        "jwt",
        re.compile(r"\b(eyJ[A-Za-z0-9_\-]{20,}\.eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})"),
        1,
    ),
    # context-aware: "<word_ending_in_KEY/TOKEN/SECRET/PASSWORD> = <high_entropy_40+_chars>"
    (
        "generic_secret_assignment",
        re.compile(
            r"\b(?:[A-Z_]+(?:KEY|TOKEN|SECRET|PASSWORD)|password|secret|api[_-]?key)\s*"
            r"[:=]\s*['\"]?([A-Za-z0-9+/=_\-]{40,})['\"]?",
            re.IGNORECASE,
        ),
        1,
    ),
)

# Placeholder/example markers — if a candidate contains any of these, skip.
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "example",
    "placeholder",
    "dummy",
    "your-key-here",
    "your_key_here",
    "xxxxxxxxxx",
    "replace-me",
    "replaceme",
    "<your",
    "REDACTED",
    "ci-build-no-real-tenant",  # ci.yml fake publishable key (old)
    # ci.yml CI build key: pk_test_ + base64("example.clerk.accounts.dev$"). The word
    # "example" sits inside the base64 where the marker above cannot see it, and the
    # scan also reads git history, so allowlisting the literal is the only fix.
    "ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
)

# Paths to skip entirely (relative to repo root or as path components).
SKIP_DIRS: tuple[str, ...] = (
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".uv-cache-local",
    "dist",
    "build",
    ".terraform",
)

# Files to skip (whole-path or by basename suffix).
SKIP_FILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\.env$"),
    re.compile(r"\.lock$"),
    re.compile(r"^uv\.lock$"),
    re.compile(r"^pnpm-lock\.yaml$"),
    re.compile(r"\.pyc$"),
    re.compile(r"\.pem\.example$"),
    re.compile(r"scripts/audit/secrets\.py$"),  # don't match our own regexes!
    re.compile(r"docs/hardening/audit-baseline\.md$"),  # don't re-match prior findings
)


@dataclass(frozen=True)
class Finding:
    """One detected pattern occurrence."""

    source: str  # "worktree" | "history:<sha>"
    file: str
    line: int
    provider: str
    secret_hash: str  # sha256 prefix — never the raw secret


def _looks_like_placeholder(candidate: str) -> bool:
    low = candidate.lower()
    if any(m.lower() in low for m in PLACEHOLDER_MARKERS):
        return True
    # Low-entropy strings (e.g. "00000...000" Langfuse dev encryption-key
    # placeholder, "xxxxxxxx", "aaaaaa") are not real secrets. Real keys
    # have >> 2 unique characters across 40+ chars.
    return len(set(candidate)) <= 2


def _hash_secret(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _should_skip(path: Path) -> bool:
    parts = path.parts
    if any(part in SKIP_DIRS for part in parts):
        return True
    path_str = str(path).replace("\\", "/")
    return any(pat.search(path_str) for pat in SKIP_FILE_PATTERNS)


def _scan_text(text: str, *, source: str, file: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for name, pattern, group_idx in PATTERNS:
            for match in pattern.finditer(line):
                candidate = match.group(group_idx)
                if _looks_like_placeholder(candidate):
                    continue
                findings.append(
                    Finding(
                        source=source,
                        file=file,
                        line=line_no,
                        provider=name,
                        secret_hash=_hash_secret(candidate),
                    )
                )
    return findings


def _git_ls_files(repo_root: Path) -> list[Path]:
    """List tracked files via git ls-files (handles .gitignore correctly)."""
    try:
        out = (
            subprocess.run(
                ["git", "ls-files"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout
            or ""
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"error: git ls-files failed: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    return [repo_root / line for line in out.splitlines() if line.strip()]


def _scan_worktree(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for file_path in _git_ls_files(repo_root):
        rel = file_path.relative_to(repo_root)
        if _should_skip(rel):
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(_scan_text(text, source="worktree", file=str(rel)))
    return findings


def _scan_history(repo_root: Path, max_commits: int) -> list[Finding]:
    """Scan added lines in the last `max_commits` commits."""
    try:
        log = (
            subprocess.run(
                [
                    "git",
                    "log",
                    f"--max-count={max_commits}",
                    "--no-color",
                    "--pretty=format:===COMMIT %H===",
                    "-p",
                    "--unified=0",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout
            or ""
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"warning: git log failed ({e}); history scan skipped", file=sys.stderr)
        return []

    findings: list[Finding] = []
    current_sha: str | None = None
    current_file: str | None = None
    for raw_line in log.splitlines():
        if raw_line.startswith("===COMMIT "):
            current_sha = raw_line.removeprefix("===COMMIT ").rstrip("=").strip()
            current_file = None
            continue
        if raw_line.startswith("+++ b/"):
            current_file = raw_line.removeprefix("+++ b/").strip()
            continue
        # Only scan ADDED lines (start with single +, NOT +++).
        if not raw_line.startswith("+") or raw_line.startswith("+++"):
            continue
        if current_sha is None or current_file is None:
            continue
        # Skip-list applies to history too.
        if _should_skip(Path(current_file)):
            continue
        line_body = raw_line[1:]
        for name, pattern, group_idx in PATTERNS:
            for match in pattern.finditer(line_body):
                candidate = match.group(group_idx)
                if _looks_like_placeholder(candidate):
                    continue
                findings.append(
                    Finding(
                        source=f"history:{current_sha[:10]}",
                        file=current_file,
                        line=0,  # diff line number — diff context not preserved
                        provider=name,
                        secret_hash=_hash_secret(candidate),
                    )
                )
    return findings


def _try_gitleaks(repo_root: Path, scan_history: bool) -> list[Finding] | None:
    """Run gitleaks if installed; return findings or None to signal fallback."""
    if shutil.which("gitleaks") is None:
        return None
    args = [
        "gitleaks",
        "detect",
        "--no-banner",
        "--redact",
        "--report-format",
        "json",
        "--report-path",
        "-",
    ]
    if not scan_history:
        args.append("--no-git")
    try:
        result = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return None
    # gitleaks exits 1 on findings, 0 on clean. Parse stdout regardless.
    raw = result.stdout.strip()
    if not raw or raw == "[]":
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        print("warning: gitleaks returned non-JSON output; falling back to regex", file=sys.stderr)
        return None
    findings: list[Finding] = []
    for item in items:
        findings.append(
            Finding(
                source="gitleaks",
                file=item.get("File", "<unknown>"),
                line=int(item.get("StartLine", 0)),
                provider=item.get("RuleID", "gitleaks"),
                secret_hash=_hash_secret(item.get("Secret", "") or item.get("Match", "")),
            )
        )
    return findings


def _render_text(findings: Iterable[Finding], engine: str) -> str:
    findings = list(findings)
    lines = [f"# Secret audit — engine: {engine}"]
    if not findings:
        lines.append("PASS — no findings.")
        return "\n".join(lines) + "\n"
    lines.append(f"FAIL — {len(findings)} finding(s) (secrets never printed; hashes only):")
    lines.append("")
    lines.append(f"  {'source':<22}{'file':<48}{'line':<6}{'provider':<24}hash")
    lines.append("  " + "-" * 110)
    for f in findings:
        lines.append(f"  {f.source:<22}{f.file[:47]:<48}{f.line:<6}{f.provider:<24}{f.secret_hash}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        type=int,
        default=200,
        help="Scan the last N commits (default 200; 0 = working tree only)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Equivalent to --history 0",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON to stdout instead of text",
    )
    parser.add_argument(
        "--no-gitleaks",
        action="store_true",
        help="Force the built-in regex scanner even if gitleaks is installed",
    )
    args = parser.parse_args(argv)

    # Reconfigure stdout for UTF-8 on Windows — see compare.py for rationale.
    import contextlib

    with contextlib.suppress(AttributeError, OSError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    repo_root = Path(__file__).resolve().parents[2]
    history_n = 0 if args.no_history else args.history
    scan_history = history_n > 0

    # Try gitleaks first (hybrid mode); fall back to regex.
    engine = "gitleaks"
    findings: list[Finding] | None = None
    if not args.no_gitleaks:
        findings = _try_gitleaks(repo_root, scan_history=scan_history)
    if findings is None:
        engine = "regex"
        findings = _scan_worktree(repo_root)
        if scan_history:
            findings += _scan_history(repo_root, history_n)

    if args.json:
        payload = {
            "engine": engine,
            "history_commits_scanned": history_n if engine == "regex" else None,
            "finding_count": len(findings),
            "findings": [asdict(f) for f in findings],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(_render_text(findings, engine))

    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
