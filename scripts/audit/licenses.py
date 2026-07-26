"""License audit — SBOM-lite for Python (runtime) deps + GPL/AGPL flagging.

License audit. Runs `uvx pip-licenses` against the locked workspace and
classifies each license. Distinguishes runtime vs dev deps using uv:
  - Runtime: `uv export --no-dev --format=requirements-txt`
  - Dev:     packages NOT in the runtime export

Gate semantics (Decision Gate #2 of Batch 1):
  - GPL/AGPL/LGPL in RUNTIME deps = block (exit 1).
  - GPL/AGPL/LGPL in DEV deps     = warn (logged, not blocking).
  - Unknown / "UNKNOWN" license   = warn (not blocking, manual review).

Exit codes:
  0 — clean (no copyleft in runtime).
  1 — copyleft license detected in runtime deps.
  2 — tool error.

Usage:
    uv run python scripts/audit/licenses.py
    uv run python scripts/audit/licenses.py --json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# License classification — coarse but sufficient for the runtime gate.
COPYLEFT_TOKENS: tuple[str, ...] = (
    "GPL",
    "AGPL",
    "LGPL",
    "GNU General Public",
    "GNU Affero",
    "GNU Lesser",
)
PERMISSIVE_TOKENS: tuple[str, ...] = (
    "MIT",
    "BSD",
    "Apache",
    "ISC",
    "Python Software Foundation",
    "MPL",
    "Mozilla Public",
    "Unlicense",
    "Zero-Clause BSD",
)


@dataclass(frozen=True)
class Pkg:
    name: str
    version: str
    license: str
    classification: str  # "permissive" | "copyleft" | "unknown" | "other"
    is_runtime: bool


def _classify(license_str: str) -> str:
    s = (license_str or "").strip()
    if not s or s.lower() in {"unknown", "n/a", "none"}:
        return "unknown"
    for token in COPYLEFT_TOKENS:
        if token.lower() in s.lower():
            return "copyleft"
    for token in PERMISSIVE_TOKENS:
        if token.lower() in s.lower():
            return "permissive"
    return "other"


def _runtime_set() -> set[str]:
    """Set of package names that are runtime (non-dev) deps."""
    uv = shutil.which("uv")
    if uv is None:
        return set()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tmp_path = Path(tf.name)
    try:
        result = subprocess.run(
            [
                uv,
                "export",
                "--no-dev",
                "--format",
                "requirements-txt",
                "--no-hashes",
                "--output-file",
                str(tmp_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return set()
        names: set[str] = set()
        for line in tmp_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # name==version or name @ url
            name = line.split("==")[0].split(" @")[0].split(">=")[0].split("<")[0]
            names.add(name.strip().lower().replace("_", "-"))
        return names
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink()


def _run_pip_licenses() -> tuple[list[dict[str, str]], str | None]:
    """`uvx pip-licenses --python <venv>` ISN'T enough — uvx isolates the tool
    from our deps, so it sees only its own ephemeral env. Use `uv run --with`
    instead: it activates the project venv AND injects pip-licenses on top, so
    pip-licenses introspects our actual installed packages."""
    uv = shutil.which("uv")
    if uv is None:
        return [], "uv not on PATH"

    result = subprocess.run(
        [
            uv,
            "run",
            "--with",
            "pip-licenses",
            "pip-licenses",
            "--format=json",
            "--ignore-packages",
            "pip",
            "setuptools",
            "wheel",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 and not result.stdout.strip():
        return [], f"pip-licenses failed: {result.stderr.strip()[:300]}"
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return [], f"pip-licenses returned non-JSON: {e}"
    return items, None


def _render_text(pkgs: list[Pkg], err: str | None) -> str:
    lines = ["# License audit"]
    if err:
        lines.append(f"  WARNING: {err}")

    runtime = [p for p in pkgs if p.is_runtime]
    dev = [p for p in pkgs if not p.is_runtime]
    runtime_copyleft = [p for p in runtime if p.classification == "copyleft"]
    dev_copyleft = [p for p in dev if p.classification == "copyleft"]
    unknowns = [p for p in pkgs if p.classification == "unknown"]

    lines.append(f"Total packages: {len(pkgs)} (runtime: {len(runtime)}, dev: {len(dev)})")
    lines.append(
        f"  permissive: {sum(1 for p in pkgs if p.classification == 'permissive')}, "
        f"copyleft: {len(runtime_copyleft) + len(dev_copyleft)} "
        f"(runtime: {len(runtime_copyleft)}, dev: {len(dev_copyleft)}), "
        f"other: {sum(1 for p in pkgs if p.classification == 'other')}, "
        f"unknown: {len(unknowns)}"
    )
    lines.append("")

    if runtime_copyleft:
        lines.append("FAIL — copyleft license in RUNTIME deps:")
        for p in runtime_copyleft:
            lines.append(f"  - {p.name} {p.version}  [{p.license}]")
    else:
        lines.append("PASS — no copyleft in runtime deps.")

    if dev_copyleft:
        lines.append("")
        lines.append("WARN — copyleft in DEV deps (informational; not blocking):")
        for p in dev_copyleft:
            lines.append(f"  - {p.name} {p.version}  [{p.license}]")

    if unknowns:
        lines.append("")
        lines.append(
            f"NOTE — {len(unknowns)} package(s) with UNKNOWN license. Manual review recommended:"
        )
        for p in unknowns[:10]:
            lines.append(f"  - {p.name} {p.version}  [{p.license or '(empty)'}]")
        if len(unknowns) > 10:
            lines.append(f"  ... ({len(unknowns) - 10} more — use --json for full list)")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    args = parser.parse_args(argv)

    with contextlib.suppress(AttributeError, OSError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    items, err = _run_pip_licenses()
    if err and not items:
        print(f"error: {err}", file=sys.stderr)
        return 2

    runtime_names = _runtime_set()
    pkgs: list[Pkg] = []
    for item in items:
        name_norm = item.get("Name", "").strip().lower().replace("_", "-")
        license_str = item.get("License", "") or ""
        pkgs.append(
            Pkg(
                name=item.get("Name", "<unknown>"),
                version=item.get("Version", "<unknown>"),
                license=license_str,
                classification=_classify(license_str),
                is_runtime=name_norm in runtime_names,
            )
        )

    runtime_copyleft_count = sum(1 for p in pkgs if p.is_runtime and p.classification == "copyleft")

    if args.json:
        payload = {
            "total": len(pkgs),
            "runtime": sum(1 for p in pkgs if p.is_runtime),
            "dev": sum(1 for p in pkgs if not p.is_runtime),
            "runtime_copyleft_count": runtime_copyleft_count,
            "packages": [asdict(p) for p in pkgs],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(_render_text(pkgs, err))

    return 1 if runtime_copyleft_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
