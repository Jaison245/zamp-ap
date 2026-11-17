"""Central config: paths, rules.yaml loading (with live edit), extractor mode."""
from __future__ import annotations
import os
from datetime import date, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
INVOICES_DIR = ROOT / "invoices"
UPLOADS_DIR = ROOT / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
FRONTEND_DIST = ROOT / "frontend" / "dist"
DB_PATH = ROOT / "app.db"
RULES_PATH = DATA_DIR / "rules.yaml"

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
# EXTRACTOR: mock | claude | auto  (auto -> claude if ANTHROPIC_API_KEY present, else mock)
_EXTRACTOR = os.getenv("EXTRACTOR", "auto").lower()


def extractor_mode() -> str:
    if _EXTRACTOR == "auto":
        return "claude" if os.getenv("ANTHROPIC_API_KEY") else "mock"
    return _EXTRACTOR


_rules_cache: dict | None = None


def load_rules(force: bool = False) -> dict:
    global _rules_cache
    if _rules_cache is None or force:
        _rules_cache = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    return _rules_cache


def save_rules(rules: dict) -> dict:
    """Persist edited rules back to rules.yaml and refresh the cache (live tolerance edits)."""
    global _rules_cache
    RULES_PATH.write_text(yaml.safe_dump(rules, sort_keys=False), encoding="utf-8")
    _rules_cache = rules
    return rules


def reference_date() -> date:
    r = load_rules().get("reference_date")
    if r:
        return datetime.strptime(str(r), "%Y-%m-%d").date()
    return date.today()
