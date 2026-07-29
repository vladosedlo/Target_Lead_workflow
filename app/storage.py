"""Локальное хранение настроек, полигонов и точек ЗРК (JSON)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import QStandardPaths


def _data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = str(Path.home() / ".avionics")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = _data_dir()
SETTINGS_FILE = DATA_DIR / "settings.json"
POLYGONS_FILE = DATA_DIR / "polygons.json"
SITES_FILE = DATA_DIR / "sites.json"
TILES_DIR = DATA_DIR / "tiles"
TILES_DIR.mkdir(parents=True, exist_ok=True)


DEFAULTS = {
    "mandala_url": "http://127.0.0.1:9080/mandala",
    "settings_password": "admin",  # пароль на меню настроек
    "map_layer": "sat",            # sat | topo | osm
    "show_track": True,
}


def load_settings() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            return {**DEFAULTS, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(d: Dict[str, Any]) -> None:
    SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def load_polygons() -> list:
    if POLYGONS_FILE.exists():
        try:
            return json.loads(POLYGONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_polygons(items: list) -> None:
    POLYGONS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sites() -> list:
    if SITES_FILE.exists():
        try:
            return json.loads(SITES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_sites(items: list) -> None:
    SITES_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")