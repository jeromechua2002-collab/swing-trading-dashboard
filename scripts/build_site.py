"""Assemble the GitHub Pages artifact from an explicit allowlist, then audit it.

Only approved HTML/CSS/JS and sanitized generated JSON are copied into _site/.
Source code, workflows, docs, fixtures and any other repository file are never
published. The audit fails the build if the directory contains an unexpected
file, a secret-like string, a Notion link/ID, or a journal field outside the
public privacy contract.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

from journal_public import find_private_markers, validate_public

STOCK_SECTORS = ("XLK", "XLY", "XLC", "XLF", "XLI", "XLB", "XLV", "XLE", "XLP", "XLU", "XLRE")
PAGES = ("index.html", "rrg.html", "rotation-lab.html", "stock-leadership.html", "sector-breadth.html",
         "trade-gate.html", "equity.html", "calendar.html", "sectors.html", "industries.html", "rates.html",
         "thematic-rrg.html")
ASSETS = ("dashboard.css", "desk-home.css", "desk-health.js", "stock-leadership.js", "trade-gate.js",
          "breadth-feed.js", "breadth-confirmation.js", ".nojekyll")
DATA = ("data/rrg-core.json", "data/rrg-audit.json", "data/rrg-validation.json", "data/rrg-sensitivity.json",
        "data/rrg-reference-trajectory-audit.json", "data/sector-breadth.json",
        "data/journal-performance.json", "data/release-manifest.json", "data/rrg-thematic.json",
        *(f"data/stocks/{s}.json" for s in STOCK_SECTORS))
ALLOWED = (*PAGES, *ASSETS, *DATA)
ALLOWED_SUFFIXES = {".html", ".css", ".js", ".json", ""}
MANIFEST_KEYS = {"schema_version", "built_at", "commit", "workflow_run", "market_status", "rrg_session",
                 "breadth_session", "market_generated_at", "market_coverage", "journal_status",
                 "journal_generated_at", "journal_last_closed_trade", "journal_closed_count",
                 "journal_return_pct", "sha256", "caveats"}

SECRET_PATTERNS = (
    re.compile(r"\b(ntn|secret)_[A-Za-z0-9]{20,}"),           # Notion integration tokens
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),              # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
)
PRIVATE_LINK_PATTERNS = (
    re.compile(r"notion\.(so|com|site)", re.I),
    re.compile(r"\b[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}\b", re.I),
)
SECRET_ENV = ("NOTION_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
PRIVATE_ID_ENV = ("NOTION_TRADES_DS", "NOTION_SWING_ACCOUNT_ID", "NOTION_ROTATION_CHART_DS", "NOTION_ROTATION_SIGNAL_DS")


def build(root=Path("."), out=Path("_site")):
    root, out = Path(root), Path(out)
    missing = [name for name in ALLOWED if not (root / name).is_file()]
    if missing:
        raise SystemExit("Publication inputs missing: " + ", ".join(missing))
    if out.exists():
        shutil.rmtree(out)
    for name in ALLOWED:
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dst)
    return audit(out)


def audit(out=Path("_site"), environ=None):
    out = Path(out)
    environ = os.environ if environ is None else environ
    problems = []
    found = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() or p.is_symlink())
    unexpected = sorted(set(found) - set(ALLOWED))
    if unexpected:
        problems.append("unexpected files: " + ", ".join(unexpected[:20]))
    absent = sorted(set(ALLOWED) - set(found))
    if absent:
        problems.append("required files absent: " + ", ".join(absent))
    secrets = [environ[k] for k in SECRET_ENV if len(environ.get(k, "")) >= 8]
    private_ids = {environ[k].replace("-", "").lower() for k in PRIVATE_ID_ENV if len(environ.get(k, "")) >= 8}
    for name in found:
        path = out / name
        if path.is_symlink():
            problems.append(f"{name}: symlinks are not publishable")
            continue
        if path.suffix not in ALLOWED_SUFFIXES:
            problems.append(f"{name}: file type not publishable")
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{name}: secret-like string ({pattern.pattern})")
        for pattern in PRIVATE_LINK_PATTERNS:
            if pattern.search(text):
                problems.append(f"{name}: Notion link or private identifier ({pattern.pattern})")
        if any(s in text for s in secrets):
            problems.append(f"{name}: contains the value of a CI secret")
        flat = text.replace("-", "").lower()
        if any(i in flat for i in private_ids):
            problems.append(f"{name}: contains a configured Notion identifier")
    journal_path = out / "data/journal-performance.json"
    if journal_path.is_file():
        try:
            validate_public(json.loads(journal_path.read_text(encoding="utf-8")))
        except ValueError as exc:
            problems.append(f"journal privacy contract: {exc}")
    manifest_path = out / "data/release-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        extra = sorted(set(manifest) - MANIFEST_KEYS)
        if extra:
            problems.append("release manifest has non-allowlisted keys: " + ", ".join(extra))
        hits = find_private_markers({k: v for k, v in manifest.items() if k != "sha256"})
        if hits:
            problems.append("release manifest private markers: " + ", ".join(hits[:8]))
    if problems:
        raise SystemExit("PUBLICATION AUDIT FAILED:\n  - " + "\n  - ".join(problems))
    print(f"PUBLICATION AUDIT PASSED: {len(found)} allowlisted files; no unexpected files, "
          "secrets, Notion links/IDs or private journal fields")
    return found


if __name__ == "__main__":
    build(out=Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_site"))
