"""Dependency audit — wraps pip-audit (Python) + pnpm audit (Node).

Dependency audit. Runs against the locked-and-frozen workspace:
  - Python: `uv export --format=requirements-txt --no-hashes` → `uvx pip-audit`
  - Node:   `pnpm audit --json` inside apps/web

Aggregates findings by severity. CI gate semantics:
  - CRITICAL or HIGH = block (exit 1).
  - MEDIUM           = warn (logged, not blocking).
  - LOW              = silent (counted in summary only).

Tools are run via uvx + pnpm so nothing pollutes pyproject.toml.

Exit codes:
  0 — clean (no CRITICAL/HIGH findings).
  1 — CRITICAL/HIGH findings present.
  2 — tool error.

Usage:
    uv run python scripts/audit/deps.py
    uv run python scripts/audit/deps.py --json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS_WEB = REPO_ROOT / "apps" / "web"

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
BLOCK_SEVERITIES = {"CRITICAL", "HIGH"}


@dataclass(frozen=True)
class Vuln:
    ecosystem: str  # "python" | "node"
    package: str
    installed: str
    advisory: str  # CVE / GHSA / advisory id
    severity: str


def _normalize_severity(s: str | None) -> str:
    if s is None:
        return "UNKNOWN"
    s = s.upper()
    if s in {"CRIT", "CRITICAL"}:
        return "CRITICAL"
    if s in {"HIGH", "ERROR"}:
        return "HIGH"
    if s in {"MEDIUM", "MODERATE", "WARN", "WARNING"}:
        return "MEDIUM"
    if s in {"LOW", "INFO", "NOTE"}:
        return "LOW"
    return "UNKNOWN"


def _run_pip_audit() -> tuple[list[Vuln], str | None]:
    """Audit the INSTALLED Python environment with pip-audit.

    This audits what is actually installed rather than a requirements file, and
    that is deliberate. The previous implementation exported the lock to a
    requirements.txt and ran `pip-audit -r` on it, which makes pip resolve and
    build the whole tree inside a scratch venv. That died on `torch==2.12.0+cpu`:
    the `+cpu` local-version tag comes from the pytorch-cpu index we pin, and no
    such version exists on PyPI, so pip errored out — and the audit reported a
    WARNING and then PASS.

    So the Python half of the dependency audit never ran. Not once. It sat green
    in the audit output the entire time while six packages carried advisories
    (aiohttp among them, with eight).

    Auditing the live environment sidesteps resolution completely: the packages
    are already there, with their real resolved versions, `+cpu` and all.
    """
    uv = shutil.which("uv")
    if uv is None:
        return [], "uv binary not on PATH"

    result = subprocess.run(
        # --with pip-audit keeps the tool out of pyproject.toml while still letting
        # it see the project's installed packages.
        [
            uv,
            "run",
            "--with",
            "pip-audit",
            "pip-audit",
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    # pip-audit exits non-zero when it FINDS something, which is not an error —
    # so we judge by whether we got parseable JSON, not by the return code.
    if not result.stdout.strip():
        return [], f"pip-audit failed: {result.stderr.strip()[:300]}"

    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as e:
        return [], f"pip-audit returned non-JSON: {e}"

    vulns: list[Vuln] = []
    # pip-audit JSON shape: { "dependencies": [{"name": ..., "version": ..., "vulns": [...]}, ...] }
    for dep in payload.get("dependencies", []):
        for v in dep.get("vulns", []):
            # pip-audit doesn't always include CVSS severity. Use "fix_versions"
            # presence as a weak proxy: if there's no fix, escalate to MEDIUM at least.
            sev = _normalize_severity(v.get("aliases", [None])[0] if False else None)
            # GitHub Advisory severities live in v["aliases"] as GHSA IDs; explicit
            # severity is in v.get("severity") or v.get("fix_versions"). We don't
            # have a reliable severity field for older pip-audit; default to HIGH
            # as a conservative blocker, which forces a human to triage.
            explicit = v.get("severity") or (v.get("fixed_versions", []) and "MEDIUM") or "HIGH"
            sev = _normalize_severity(explicit if isinstance(explicit, str) else None)
            vulns.append(
                Vuln(
                    ecosystem="python",
                    package=dep.get("name", "<unknown>"),
                    installed=dep.get("version", "<unknown>"),
                    advisory=v.get("id", "<no-id>"),
                    severity=sev,
                )
            )
    return vulns, None


def _run_pnpm_audit() -> tuple[list[Vuln], str | None]:
    """Run pnpm audit in apps/web."""
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return [], "pnpm not on PATH"
    if not APPS_WEB.exists():
        return [], None  # nothing to audit if there is no web app
    result = subprocess.run(
        [pnpm, "audit", "--json"],
        cwd=APPS_WEB,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # pnpm audit exits non-zero on findings; parse stdout regardless.
    if not result.stdout.strip() and result.returncode != 0:
        return [], f"pnpm audit failed: {result.stderr.strip()[:300]}"

    vulns: list[Vuln] = []
    # pnpm emits one JSON object per line OR a single document depending on version.
    # Handle both: try whole-document parse first, fall back to line-mode.
    try:
        payload = json.loads(result.stdout)
        advisories = payload.get("advisories", {}) or payload.get("vulnerabilities", {})
    except json.JSONDecodeError:
        # line-mode fallback (pnpm 8.x style)
        advisories = {}
        for raw in result.stdout.splitlines():
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "auditAdvisory":
                advisories[obj.get("data", {}).get("advisory", {}).get("id")] = obj.get(
                    "data", {}
                ).get("advisory", {})

    for advisory in advisories.values():
        if not isinstance(advisory, dict):
            continue
        vulns.append(
            Vuln(
                ecosystem="node",
                package=advisory.get("module_name") or advisory.get("name", "<unknown>"),
                installed=advisory.get("vulnerable_versions", "<unknown>"),
                advisory=str(
                    advisory.get("github_advisory_id")
                    or advisory.get("url")
                    or advisory.get("id", "")
                ),
                severity=_normalize_severity(advisory.get("severity")),
            )
        )
    return vulns, None


def _render_text(python: list[Vuln], node: list[Vuln], errors: dict[str, str | None]) -> str:
    all_vulns = python + node
    if not all_vulns and not any(errors.values()):
        return "Dep audit: PASS — 0 vulnerabilities found.\n"

    lines = ["# Dependency audit"]
    for tool, err in errors.items():
        if err:
            lines.append(f"  WARNING [{tool}]: {err}")

    counts: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    for v in all_vulns:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    summary = " ".join(f"{s}={counts[s]}" for s in SEVERITY_ORDER if counts.get(s))
    lines.append(f"Found {len(all_vulns)} vuln(s): {summary or 'none'}")
    lines.append("")
    if all_vulns:
        lines.append(f"  {'ecosystem':<10}{'severity':<10}{'package':<28}{'installed':<18}advisory")
        lines.append("  " + "-" * 100)
        for v in sorted(all_vulns, key=lambda x: (SEVERITY_ORDER.index(x.severity), x.package)):
            lines.append(
                f"  {v.ecosystem:<10}{v.severity:<10}{v.package[:27]:<28}{v.installed[:17]:<18}{v.advisory}"
            )
    blockers = [v for v in all_vulns if v.severity in BLOCK_SEVERITIES]
    if blockers:
        lines.append("")
        lines.append(f"FAIL — {len(blockers)} CRITICAL/HIGH finding(s). Address before merge.")
    else:
        lines.append("")
        lines.append("PASS — no CRITICAL/HIGH findings. (Medium / Low surfaced for awareness.)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    args = parser.parse_args(argv)

    with contextlib.suppress(AttributeError, OSError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    python_vulns, py_err = _run_pip_audit()
    node_vulns, node_err = _run_pnpm_audit()

    if args.json:
        payload = {
            "python": [asdict(v) for v in python_vulns],
            "node": [asdict(v) for v in node_vulns],
            "errors": {"pip-audit": py_err, "pnpm-audit": node_err},
            "blocker_count": sum(
                1 for v in python_vulns + node_vulns if v.severity in BLOCK_SEVERITIES
            ),
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(
            _render_text(python_vulns, node_vulns, {"pip-audit": py_err, "pnpm-audit": node_err})
        )

    # FAIL CLOSED. If either engine errored, exit 2 — no matter what the other one
    # found.
    #
    # This used to read "exit 2 only when we got NO partial results to gate on",
    # which forgave a dead engine as long as the other one produced output. That
    # is exactly how this script spent its whole life reporting PASS while the
    # Python audit was crashing on every run and scanning nothing.
    #
    # A scanner that did not run is not a clean scan. The only safe reading of "I
    # could not check" is "assume the worst" — anything else is a green tick that
    # means nothing, which is more dangerous than no tick at all, because people
    # trust it.
    if py_err or node_err:
        for engine, err in (("pip-audit", py_err), ("pnpm audit", node_err)):
            if err:
                sys.stderr.write(
                    f"\nAUDIT ENGINE FAILED — {engine}: {err}\n"
                    f"Failing closed: an audit that could not run is NOT a pass.\n"
                )
        return 2

    blockers = [v for v in python_vulns + node_vulns if v.severity in BLOCK_SEVERITIES]
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
