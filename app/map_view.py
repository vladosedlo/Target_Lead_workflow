"""Виджет карты на QtWebEngine + Leaflet, с мостом QWebChannel."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot, QTimer, Qt
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWidgets import QWidget, QVBoxLayout


class _Bridge(QObject):
    ready_signal = Signal()
    context_action = Signal(str, float, float)        # action, lat, lon
    site_moved_signal = Signal(str, float, float)     # site_id, lat, lon
    site_selected_signal = Signal(str)                # site_id

    @Slot()
    def ready(self):
        self.ready_signal.emit()

    @Slot(str, str, str)
    def contextAction(self, action: str, lat: str, lon: str):
        # Координаты приходят строками: QWebChannel искажает второй подряд
        # float-аргумент (долгота обнулялась/клампилась в 180). Парсим сами.
        self.context_action.emit(action, float(lat), float(lon))

    @Slot(str, str, str)
    def siteMoved(self, site_id: str, lat: str, lon: str):
        self.site_moved_signal.emit(site_id, float(lat), float(lon))

    @Slot(str)
    def siteSelected(self, site_id: str):
        self.site_selected_signal.emit(site_id)


class MapView(QWidget):
    map_ready = Signal()
    context_action = Signal(str, float, float)
    bounds_received = Signal(dict)
    site_moved = Signal(str, float, float)
    site_selected = Signal(str)

    def __init__(self, tile_base_url: str, parent=None):
        super().__init__(parent)
        self._tile_base = tile_base_url
        self._ready = False
        self._pending: list[str] = []

        # ВАЖНО для macOS: даём контейнеру собственное native NSView, чтобы
        # WebEngineView внутри него имел стабильную родительскую поверхность
        # при drag/dock/float операциях. На сам QWebEngineView атрибуты НЕ
        # ставим — это ломает рендер (карта становится пустой), он сам
        # управляет своим layer-backed view.
        self.setAttribute(Qt.WA_NativeWindow, True)

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self._view = QWebEngineView(self)
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        lay.addWidget(self._view)

        self._channel = QWebChannel(self)
        self._bridge = _Bridge()
        self._bridge.ready_signal.connect(self._on_ready)
        self._bridge.context_action.connect(self.context_action)
        self._bridge.site_moved_signal.connect(self.site_moved)
        self._bridge.site_selected_signal.connect(self.site_selected)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # Поиск map.html: сначала рядом с модулем, потом в PyInstaller _MEIPASS
        import sys as _sys
        candidates = [
            Path(__file__).parent / "map.html",
            Path(getattr(_sys, "_MEIPASS", "")) / "app" / "map.html",
            Path(getattr(_sys, "_MEIPASS", "")) / "map.html",
        ]
        html_path = next((c for c in candidates if c.exists()), candidates[0])
        url = QUrl.fromLocalFile(str(html_path))
        # Передаём базовый URL локального тайл-сервера через query, чтобы
        # Leaflet и тайлы грузились локально (офлайн-режим).
        from PySide6.QtCore import QUrlQuery
        q = QUrlQuery(); q.addQueryItem("base", self._tile_base)
        url.setQuery(q)
        self._view.load(url)

    def _on_ready(self):
        self._ready = True
        self._js(f"api.setTileBase({json.dumps(self._tile_base)});")
        self._js("api.setLayer('sat');")
        for cmd in self._pending:
            self._view.page().runJavaScript(cmd)
        self._pending.clear()
        self.map_ready.emit()

    def _js(self, code: str, cb: Optional[Callable] = None):
        if not self._ready:
            self._pending.append(code)
            return
        if cb is None:
            self._view.page().runJavaScript(code)
        else:
            self._view.page().runJavaScript(code, cb)

    # ---- API ----
    def set_layer(self, kind: str):
        self._js(f"api.setLayer({json.dumps(kind)});")

    def set_plane(self, lat: float, lon: float, course: float):
        self._js(f"api.setPlane({lat},{lon},{course});")

    def set_show_track(self, v: bool):
        self._js(f"api.setShowTrack({'true' if v else 'false'});")

    def clear_track(self):
        self._js("api.clearTrack();")

    def render_polygons(self, items: list):
        self._js(f"api.renderPolygons({json.dumps(items, ensure_ascii=False)});")

    def render_sites(self, items: list):
        self._js(f"api.renderSites({json.dumps(items, ensure_ascii=False)});")

    def fly_to(self, lat: float, lon: float, z: int = 14):
        self._js(f"api.flyTo({lat},{lon},{z});")

    def center_on(self, lat: float, lon: float):
        """Переместить центр карты на координаты, сохранив текущий зум."""
        self._js(f"api.centerOn({lat},{lon});")

    def set_follow(self, v: bool):
        """Включить плавное следование карты за самолётом (без рывков)."""
        self._js(f"api.setFollow({'true' if v else 'false'});")

    def get_bounds(self, cb: Callable[[dict], None]):
        def _wrap(s):
            try: cb(json.loads(s))
            except Exception: cb({})
        self._js("api.getBounds()", _wrap)