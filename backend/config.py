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
# Default to a *-flash-lite model: as of Nov 2026 the full-size Flash models
# (3.6/3.7/3.8) are chronically 503-overloaded on the free tier, while the lite
# variants have capacity and answer in ~3s. Confirmed working on a fresh free key.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Tried in order on a transient 503/429 ("model overloaded") before giving up.
GEMINI_FALLBACK_MODELS = [m.strip() for m in
    os.getenv("GEMINI_FALLBACK_MODELS",
              "gemini-3.1-flash-lite,gemini-2.5-flash-lite,gemini-3.8-flash").split(",") if m.strip()]
# EXTRACTOR: mock | claude | gemini | auto
#   auto -> claude if ANTHROPIC_API_KEY, else gemini if GEMINI_API_KEY/GOOGLE_API_KEY, else mock
_EXTRACTOR = os.getenv("EXTRACTOR", "auto").lower()


def _has_gemini_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def extractor_mode() -> str:
    if _EXTRACTOR == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            return "claude"
        if _has_gemini_key():
            return "gemini"
        return "mock"
    return _EXTRACTOR


def active_model() -> str:
    """The model actually in use, for display in /api/health."""
    mode = extractor_mode()
    if mode == "gemini":
        return GEMINI_MODEL
    if mode == "claude":
        return MODEL
    return "mock"


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
