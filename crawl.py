"""Crawl CCAR-F / CCAR-P practice content from flashgenius.net, then rebuild docs/data.js via build.py.

Usage (PowerShell):
    $env:FG_USER = "<user>"; $env:FG_PASS = "..."; python crawl.py

Fetches only what a free account can see: the sample-test question sets
(quick-start + one set per domain) and the public cheat sheets / FAQ that ship
in the site's JS bundle.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

BASE = "https://flashgenius.net"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT_JS = ROOT / "docs" / "data.js"

CERTS = {
    "ccar-f": {
        "code": "CCAR-F",
        "name": "Claude Certified Architect – Foundations",
        "exam": {"questions": 60, "minutes": 120, "passing": "720 / 1000 (scaled)", "cost": "$125"},
        "modules": ["agentic-architecture", "claude-code-workflows", "prompt-engineering",
                    "tool-design-mcp", "context-management"],
        "weights": {"Agentic Architecture & Orchestration": 27, "Claude Code Configuration & Workflows": 20,
                    "Prompt Engineering & Structured Output": 20, "Tool Design & MCP Integration": 18,
                    "Context Management & Reliability": 15},
    },
    "ccar-p": {
        "code": "CCAR-P",
        "name": "Claude Certified Architect – Professional",
        "exam": {"questions": 63, "minutes": 120, "passing": "720 / 1000 (scaled)", "cost": "$175"},
        "modules": ["integration", "solution-design", "evaluation-testing", "governance-safety",
                    "stakeholder-lifecycle", "claude-models-prompting", "developer-productivity"],
        "weights": {"Integration": 19, "Solution Design & Architecture": 17,
                    "Evaluation, Testing & Optimization": 16, "Governance, Safety & Risk Management": 14,
                    "Stakeholder Communication & Lifecycle Management": 14,
                    "Claude Models, Prompting & Context Engineering": 13,
                    "Developer Productivity & Operational Enablement": 7},
    },
}


def login(s: requests.Session) -> None:
    user, pw = os.environ.get("FG_USER"), os.environ.get("FG_PASS")
    if not user or not pw:
        sys.exit("Set FG_USER and FG_PASS environment variables first.")
    r = s.post(f"{BASE}/api/auth/login", json={"username": user, "password": pw}, timeout=30)
    r.raise_for_status()
    print("Logged in as", r.json().get("username"))


def fetch_questions(s: requests.Session) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for slug, cfg in CERTS.items():
        for mod in ["quick-start", *cfg["modules"]]:
            r = s.get(f"{BASE}/api/sample-questions/{slug}/{mod}", timeout=30)
            r.raise_for_status()
            # quick-start returns a random draw each time, so keep every pull
            name = f"{slug}_{mod}-{time.strftime('%Y%m%d%H%M%S')}" if mod == "quick-start" else f"{slug}_{mod}"
            (RAW / f"{name}.json").write_text(r.text, encoding="utf-8")
            print(f"  {slug}/{mod}: {len(r.json())} questions")
            time.sleep(1)


def fetch_study(s: requests.Session) -> dict:
    """Download the cheat-sheet/FAQ chunks and parse their data literals with node."""
    index = s.get(f"{BASE}/my-certification", timeout=30).text
    entry = re.search(r'src="(/assets/index-[^"]+\.js)"', index).group(1)
    bundle = s.get(BASE + entry, timeout=60).text
    chunks = sorted(set(re.findall(r"assets/(ccar-[fp]-(?:cheat-sheet|content)-[A-Za-z0-9_-]+\.js)", bundle)))
    with tempfile.TemporaryDirectory() as tmp:
        for c in chunks:
            Path(tmp, c).write_text(s.get(f"{BASE}/assets/{c}", timeout=30).text, encoding="utf-8")
        out = Path(tmp, "study.json")
        subprocess.run(["node", str(ROOT / "tools" / "extract_study.js"), tmp, str(out)], check=True)
        study = json.loads(out.read_text(encoding="utf-8"))
    (ROOT / "data" / "study.json").write_text(json.dumps(study, ensure_ascii=False, indent=1), encoding="utf-8")
    return study


def main() -> None:
    if not shutil.which("node"):
        sys.exit("node is required to parse the cheat sheets.")
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (study-crawler)"
    login(s)
    fetch_questions(s)
    fetch_study(s)
    from build import build  # build.py imports this module, so import lazily
    build()


if __name__ == "__main__":
    main()
