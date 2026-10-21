"""Главное окно: меню, dock-виджеты (авионика, индикаторы, панель полигонов/ЗРК), карта."""
from __future__ import annotations

import time
import uuid
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPoint, QSize
from PySide6.QtGui import QAction, QKeySequence, QColor
from PySide6.QtWidgets import QColorDialog
from PySide6.QtWidgets import (QMainWindow, QDockWidget, QWidget, QVBoxLayout,
                              QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
                              QInputDialog, QMessageBox, QComboBox, QLabel, QCheckBox,
                              QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox,
                              QFileDialog, QProgressDialog, QApplication, QToolBar,
                              QScrollArea, QSizePolicy, QAbstractSpinBox)

from .avionics import AvionicsWidget
from .indicators import IndicatorsPanel
from .mandala_client import MandalaClient, FlightData
from .map_view import MapView
from .settings_dialog import PasswordDialog, SettingsDialog
from .tile_server import (TileServer, download_area, PROVIDERS,
                          preload_world, ensure_leaflet, set_provider_set)
from . import storage
from .geo import in_sector


class SteadyDoubleSpinBox(QDoubleSpinBox):
    def stepEnabled(self):
        return (QAbstractSpinBox.StepUpEnabled |
                QAbstractSpinBox.StepDownEnabled)


LAYER_LABELS = {
    "sat":        "Спутник",
    "sat_labels": "Спутник + подписи",
    "topo":       "Топография",
    "osm":        "Карта (OSM)",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Мишень. АРМ Руководителя стрельб")
        self.resize(1500, 950)

        self.settings = storage.load_settings()
        self.polygons = storage.load_polygons()
        self.sites = storage.load_sites()
        self._current_polygon_id: Optional[str] = None
        self._last_data: FlightData = FlightData()

        set_provider_set(self.settings.get("provider_set", "world"))

        self._tiles = TileServer()
        self._tiles.start()
        self._ensure_offline_assets()

        self.setDockNestingEnabled(True)

        _ph = QWidget(); _ph.setMaximumSize(0, 0)
        self.setCentralWidget(_ph)

        self._docks_unlocked = bool(self.settings.get("docks_unlocked", False))
        F = self._dock_features(self._docks_unlocked)

        # Авионика
        self.avionics = AvionicsWidget()
        self.dock_av = QDockWidget("Авионика", self)
        self.dock_av.setObjectName("dock_av")
        self.dock_av.setWidget(self.avionics)

        # Индикаторы
        self.indicators = IndicatorsPanel()
        self.dock_ind = QDockWidget("Индикаторы", self)
        self.dock_ind.setObjectName("dock_ind")
        self.dock_ind.setWidget(self.indicators)

        # Карта
        self.map_view = MapView(self._tiles.base_url, self)
        self.dock_map = QDockWidget("Карта", self)
        self.dock_map.setObjectName("dock_map")
        self.dock_map.setWidget(self.map_view)
        self.map_view.map_ready.connect(self._on_map_ready)
        self.map_view.context_action.connect(self._on_map_ctx)
        self.map_view.site_moved.connect(self._on_site_moved)
        self.map_view.site_selected.connect(self._on_site_selected_on_map)

        # Объекты (полигоны/ЗРК)
        self.side_panel = self._build_side_panel()
        self.dock_side = QDockWidget("Объекты", self)
        self.dock_side.setObjectName("dock_side")
        self.dock_side.setWidget(self.side_panel)

        self._apply_dock_features()

        self._apply_default_layout()
        saved = self.settings.get("dock_state")
        if saved:
            try:
                from PySide6.QtCore import QByteArray
                self.restoreState(QByteArray.fromBase64(saved.encode("ascii")))
            except Exception:
                pass

        self._build_menu()
        self._build_toolbar()

        self.statusBar().showMessage("Готово")

        self.client = MandalaClient(self.settings.get("mandala_url"))
        self.client.data_ready.connect(self._on_data)
        self.client.link_status.connect(self._on_link)
        self.client.start()

        self._zone_timer = QTimer(self); self._zone_timer.setInterval(200)
        self._zone_timer.timeout.connect(self._update_zone)
        self._zone_timer.start()

    # =========================================================
    def _dock_features(self, unlocked: bool):
        if unlocked:
            return (QDockWidget.DockWidgetMovable
                    | QDockWidget.DockWidgetFloatable
                    | QDockWidget.DockWidgetClosable)
        return QDockWidget.NoDockWidgetFeatures

    def _apply_dock_features(self):
        F = self._dock_features(self._docks_unlocked)
        for d in (self.dock_av, self.dock_ind, self.dock_map, self.dock_side):
            d.setFeatures(F)
            if self._docks_unlocked:
                d.setTitleBarWidget(None)
            else:
                empty = QWidget(); empty.setFixedHeight(0)
                d.setTitleBarWidget(empty)

    def _toggle_docks_unlocked(self, v: bool):
        self._docks_unlocked = bool(v)
        self.settings["docks_unlocked"] = self._docks_unlocked
        storage.save_settings(self.settings)
        self._apply_dock_features()
        self.statusBar().showMessage(
            "Перенос окон РАЗРЕШЁН — можно перетаскивать панели за заголовок"
            if self._docks_unlocked else
            "Перенос окон заблокирован", 3000)

    def _apply_default_layout(self):

        for d in (self.dock_av, self.dock_ind, self.dock_map, self.dock_side):
            self.removeDockWidget(d)
            d.setFloating(False)
            d.show()

        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_av)
        self.splitDockWidget(self.dock_av, self.dock_ind, Qt.Horizontal)
        self.splitDockWidget(self.dock_av, self.dock_map, Qt.Vertical)
        self.splitDockWidget(self.dock_ind, self.dock_side, Qt.Vertical)

        self.resizeDocks([self.dock_av, self.dock_ind], [3, 1], Qt.Horizontal)
        self.resizeDocks([self.dock_av, self.dock_map], [1, 3], Qt.Vertical)
        self.resizeDocks([self.dock_ind, self.dock_side], [1, 3], Qt.Vertical)

    def _reset_layout(self):
        self._apply_default_layout()
        self._save_layout()

    def _save_layout(self):
        try:
            from PySide6.QtCore import QByteArray
            data = bytes(self.saveState().toBase64()).decode("ascii")
            self.settings["dock_state"] = data
            storage.save_settings(self.settings)
        except Exception:
            pass

    def _ensure_offline_assets(self):
        """Проверяет Leaflet и базовые тайлы; качает при первом запуске."""
        from .tile_server import STATIC_DIR, tile_exists
        leaflet_ok = (STATIC_DIR / "leaflet.js").exists() and (STATIC_DIR / "leaflet.css").exists()
        prov = self.settings.get("map_layer", "sat")
        base_prov = "sat" if prov == "sat_labels" else prov
        world_ok = tile_exists(base_prov, 0, 0, 0)
        if leaflet_ok and world_ok:
            preload_world(prov, z_max=3)
            return

        dlg = QProgressDialog("Подготовка карты (нужен интернет один раз)…",
                              "Пропустить", 0, 100, self)
        dlg.setWindowTitle("Первый запуск")
        dlg.setMinimumDuration(0); dlg.setValue(0)
        QApplication.processEvents()
        if not leaflet_ok:
            dlg.setLabelText("Загрузка Leaflet…")
            QApplication.processEvents()
            ensure_leaflet()
        dlg.setLabelText("Загрузка базовых тайлов мира (z 0–3)…")
        QApplication.processEvents()
        def progress(i, total):
            dlg.setMaximum(max(1,total)); dlg.setValue(i)
            QApplication.processEvents()
            if dlg.wasCanceled():
                raise RuntimeError("cancelled")
        try:
            preload_world(prov, z_max=3, progress=progress, sync=True)
        except Exception:
            pass
        dlg.close()

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("Файл")
        a_quit = QAction("Выход", self); a_quit.setShortcut(QKeySequence.Quit)
        a_quit.triggered.connect(self.close); m_file.addAction(a_quit)

        m_view = mb.addMenu("Вид")
        for d, title in ((self.dock_av, "Авионика"),
                         (self.dock_ind, "Индикаторы"),
                         (self.dock_side, "Объекты"),
                         (self.dock_map, "Карта")):
            act = d.toggleViewAction()
            act.setText(title)
            m_view.addAction(act)
        m_view.addSeparator()
        a_unlock = QAction("🔓  Разрешить перенос окон", self, checkable=True)
        a_unlock.setChecked(self._docks_unlocked)
        a_unlock.setShortcut("Ctrl+Shift+L")
        a_unlock.toggled.connect(self._toggle_docks_unlocked)
        a_unlock.setStatusTip("Включает возможность перетаскивать и откреплять панели")
        m_view.addAction(a_unlock)
        a_float_map = QAction("Карта в отдельном окне", self, checkable=True)
        a_float_map.toggled.connect(lambda v: self.dock_map.setFloating(v))
        self.dock_map.topLevelChanged.connect(a_float_map.setChecked)
        m_view.addAction(a_float_map)
        m_view.addSeparator()
        a_reset = QAction("↺  Стандартный вид", self)
        a_reset.setShortcut("Ctrl+Shift+R")
        a_reset.triggered.connect(self._reset_layout)
        m_view.addAction(a_reset)

        m_map = mb.addMenu("Карта")
        for k, label in LAYER_LABELS.items():
            a = QAction(label, self, checkable=True)
            a.setData(k)
            a.triggered.connect(lambda checked=False, kind=k: self._set_layer(kind))
            m_map.addAction(a)
        m_map.addSeparator()
        a_save = QAction("Сохранить видимую область локально…", self)
        a_save.triggered.connect(self._save_area)
        m_map.addAction(a_save)
        a_track = QAction("Показывать трек", self, checkable=True)
        a_track.setChecked(self.settings.get("show_track", True))
        a_track.toggled.connect(self._toggle_track)
        m_map.addAction(a_track)
        a_clear = QAction("Очистить трек", self)
        a_clear.triggered.connect(lambda: self.map_view.clear_track())
        m_map.addAction(a_clear)

        m_set = mb.addMenu("Настройки")
        a_open = QAction("Открыть настройки…", self)
        a_open.triggered.connect(self._open_settings)
        m_set.addAction(a_open)

    # =========================================================
    def _build_toolbar(self):
        tb = QToolBar("Карта", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setObjectName("mapToolbar")
        # Стили тулбара
        tb.setStyleSheet("""
            QToolBar#mapToolbar {
                background: #161d25;
                border: 0;
                border-bottom: 1px solid #2c3a4a;
                padding: 6px 8px; spacing: 8px;
            }
            QToolBar#mapToolbar QLabel { color:#9fb4cc; padding: 0 4px; }
            QToolBar#mapToolbar QPushButton {
                background:#1f2a36; color:#e6edf3; border:1px solid #2c3a4a;
                border-radius:6px; padding:6px 12px; min-height: 24px;
            }
            QToolBar#mapToolbar QPushButton:hover { background:#2a3849; }
            QToolBar#mapToolbar QPushButton:pressed { background:#16202b; }
            QToolBar#mapToolbar QComboBox {
                background:#1f2a36; color:#e6edf3; border:1px solid #2c3a4a;
                border-radius:6px; padding:4px 28px 4px 10px; min-height: 24px;
                min-width: 200px;
            }
            QToolBar#mapToolbar QComboBox::drop-down { border: 0; width: 22px; }
            QToolBar#mapToolbar QComboBox QAbstractItemView {
                background:#1b232c; color:#e6edf3; border:1px solid #2c3a4a;
                selection-background-color:#2a3849; padding:4px;
            }
            QToolBar#mapToolbar QCheckBox { color:#e6edf3; padding: 0 6px; spacing:6px; }
            QToolBar#mapToolbar QFrame[frameShape="5"] { color:#2c3a4a; }
        """)
        self.addToolBar(Qt.TopToolBarArea, tb)

        tb.addWidget(QLabel("Подложка:"))
        self.layer_combo = QComboBox()
        self.layer_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for k, label in LAYER_LABELS.items():
            self.layer_combo.addItem(label, k)
        cur = self.settings.get("map_layer", "sat")
        keys = list(LAYER_LABELS.keys())
        self.layer_combo.setCurrentIndex(keys.index(cur) if cur in keys else 0)
        self.layer_combo.currentIndexChanged.connect(
            lambda i: self._set_layer(self.layer_combo.itemData(i)))
        tb.addWidget(self.layer_combo)
        tb.addSeparator()

        b_save = QPushButton("💾  Сохранить видимую область")
        b_save.setToolTip("Сохранить тайлы текущей видимой области для оффлайн-режима")
        b_save.clicked.connect(self._save_area)
        tb.addWidget(b_save)

        self.cb_all_zooms = QCheckBox("Все зумы")
        self.cb_all_zooms.setToolTip(
            "Сохранять тайлы для ВСЕХ уровней зума (1–18).\n"
            "Внимание: для больших областей это может быть десятки/сотни тысяч тайлов.")
        self.cb_all_zooms.setChecked(bool(self.settings.get("save_all_zooms", False)))
        self.cb_all_zooms.toggled.connect(self._toggle_all_zooms)
        tb.addWidget(self.cb_all_zooms)
        tb.addSeparator()

        self.cb_track = QCheckBox("Показывать трек")
        self.cb_track.setChecked(self.settings.get("show_track", True))
        self.cb_track.toggled.connect(self._toggle_track)
        tb.addWidget(self.cb_track)

        b_clear = QPushButton("Очистить трек")
        b_clear.clicked.connect(lambda: self.map_view.clear_track())
        tb.addWidget(b_clear)
        tb.addSeparator()

        # Камера / Следование
        b_center = QPushButton("🎯  К самолёту")
        b_center.setToolTip("Переместить вид карты на текущие координаты самолёта")
        b_center.clicked.connect(self._center_on_plane)
        tb.addWidget(b_center)

        self.cb_follow = QCheckBox("Следить за самолётом")
        self.cb_follow.setChecked(bool(self.settings.get("follow_plane", False)))
        self.cb_follow.toggled.connect(self._toggle_follow)
        tb.addWidget(self.cb_follow)

        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

    def _build_side_panel(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner); lay.setContentsMargins(8,8,8,8); lay.setSpacing(8)

        # --- Полигоны ---
        gp = QGroupBox("Полигоны")
        gpl = QVBoxLayout(gp)
        self.poly_list = QListWidget()
        self.poly_list.itemSelectionChanged.connect(self._poly_selected)
        self.poly_list.itemClicked.connect(lambda _it: self._center_on_polygon())
        gpl.addWidget(self.poly_list)
        row = QHBoxLayout()
        b_new = QPushButton("Новый"); b_new.clicked.connect(self._new_polygon)
        b_addp = QPushButton("+ точка"); b_addp.clicked.connect(self._add_point_dialog)
        b_del = QPushButton("Удалить"); b_del.clicked.connect(self._del_polygon)
        row.addWidget(b_new); row.addWidget(b_addp); row.addWidget(b_del)
        gpl.addLayout(row)
        self.poly_points = QListWidget()
        self.poly_points.setMaximumHeight(140)
        self.poly_points.itemDoubleClicked.connect(self._edit_poly_point)
        gpl.addWidget(self.poly_points)
        row_pt = QHBoxLayout()
        b_edit_pt = QPushButton("Изменить точку"); b_edit_pt.clicked.connect(lambda: self._edit_poly_point(self.poly_points.currentItem()))
        b_del_pt  = QPushButton("Удалить точку");  b_del_pt.clicked.connect(self._del_poly_point)
        row_pt.addWidget(b_edit_pt); row_pt.addWidget(b_del_pt)
        gpl.addLayout(row_pt)
        # Палитра цветов полигона
        row_col = QHBoxLayout()
        row_col.addWidget(QLabel("Цвет:"))
        self.poly_color_btn = QPushButton("Контур")
        self.poly_color_btn.clicked.connect(lambda: self._pick_poly_color("color"))
        row_col.addWidget(self.poly_color_btn)
        self.poly_fill_btn = QPushButton("Заливка")
        self.poly_fill_btn.clicked.connect(lambda: self._pick_poly_color("fill_color"))
        row_col.addWidget(self.poly_fill_btn)
        gpl.addLayout(row_col)
        lay.addWidget(gp)

        # --- ЗРК ---
        gs = QGroupBox("Точки стояния ЗРК")
        gsl = QVBoxLayout(gs)
        self.sites_list = QListWidget()
        self.sites_list.itemSelectionChanged.connect(self._site_selected)
        gsl.addWidget(self.sites_list)
        form = QFormLayout()
        self.s_type = QComboBox(); self.s_type.addItems(["Тунгуска","Стрела-10","Игла","Оса","Бук"])
        self.s_label = QSpinBox(); self.s_label.setRange(0, 9999)
        self.s_lat = SteadyDoubleSpinBox(); self.s_lat.setRange(-90, 90); self.s_lat.setDecimals(7); self.s_lat.setSingleStep(0.0001); self.s_lat.setSuffix("°")
        self.s_lon = SteadyDoubleSpinBox(); self.s_lon.setRange(-180, 180); self.s_lon.setDecimals(7); self.s_lon.setSingleStep(0.0001); self.s_lon.setSuffix("°")
        self.s_az0 = SteadyDoubleSpinBox(); self.s_az0.setRange(0,360); self.s_az0.setSuffix("°")
        self.s_az1 = SteadyDoubleSpinBox(); self.s_az1.setRange(0,360); self.s_az1.setSuffix("°")
        self.s_range = SteadyDoubleSpinBox(); self.s_range.setRange(0.1,50); self.s_range.setValue(10); self.s_range.setSuffix(" км")
        form.addRow("Тип:", self.s_type)
        form.addRow("Метка №:", self.s_label)
        form.addRow("Широта:", self.s_lat)
        form.addRow("Долгота:", self.s_lon)
        form.addRow("Азимут начало:", self.s_az0)
        form.addRow("Азимут конец:", self.s_az1)
        form.addRow("Дальность:", self.s_range)
        gsl.addLayout(form)
        # Палитра цветов ЗРК
        row_sc = QHBoxLayout()
        row_sc.addWidget(QLabel("Цвет:"))
        self.site_color_btn = QPushButton("Точка")
        self.site_color_btn.clicked.connect(lambda: self._pick_site_color("color"))
        row_sc.addWidget(self.site_color_btn)
        self.site_fill_btn = QPushButton("Зона")
        self.site_fill_btn.clicked.connect(lambda: self._pick_site_color("fill_color"))
        row_sc.addWidget(self.site_fill_btn)
        gsl.addLayout(row_sc)
        row2 = QHBoxLayout()
        b_apply = QPushButton("Применить"); b_apply.clicked.connect(self._apply_site)
        b_dels = QPushButton("Удалить"); b_dels.clicked.connect(self._del_site)
        row2.addWidget(b_apply); row2.addWidget(b_dels)
        gsl.addLayout(row2)
        lay.addWidget(gs)

        lay.addStretch(1)
        self._refresh_polys(); self._refresh_sites()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(inner)
        scroll.setMinimumWidth(280)
        return scroll

    # =========================================================
    def _on_map_ready(self):
        self._set_layer(self.settings.get("map_layer", "sat"))
        self.map_view.set_show_track(self.settings.get("show_track", True))
        self.map_view.render_polygons(self.polygons)
        self.map_view.render_sites(self.sites)
        if self.settings.get("follow_plane", False):
            self.map_view.set_follow(True)

    def _set_layer(self, kind: str):
        if kind not in PROVIDERS: return
        self.settings["map_layer"] = kind
        storage.save_settings(self.settings)
        self.map_view.set_layer(kind)

    def _toggle_track(self, v: bool):
        self.settings["show_track"] = v
        storage.save_settings(self.settings)
        self.map_view.set_show_track(v)

    def _toggle_all_zooms(self, v: bool):
        self.settings["save_all_zooms"] = bool(v)
        storage.save_settings(self.settings)

    # ---------- mandala ----------
    def _on_data(self, fd: FlightData):
        self._last_data = fd
        self.avionics.set_data(fd)
        if fd.gps_lat or fd.gps_lon:
            self.map_view.set_plane(fd.gps_lat, fd.gps_lon, fd.course)

    def _on_link(self, ok: bool, reason: str):
        self.indicators.set_link(ok)
        self.statusBar().showMessage(f"Связь: {'OK' if ok else 'НЕТ'} — {reason}")

    def _update_zone(self):
        fd = self._last_data
        if not fd or (fd.gps_lat == 0 and fd.gps_lon == 0):
            self.indicators.set_zone(False); return
        for s in self.sites:
            if in_sector(fd.gps_lat, fd.gps_lon, s["lat"], s["lon"],
                         s["az_start"], s["az_end"], s.get("range_km",10)*1000):
                self.indicators.set_zone(True); return
        self.indicators.set_zone(False)

    # ---------- настройки ----------
    def _open_settings(self):
        pwd_dlg = PasswordDialog(self.settings.get("settings_password","admin"), self)
        if pwd_dlg.exec() != PasswordDialog.Accepted:
            return
        old_set = self.settings.get("provider_set", "world")
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == SettingsDialog.Accepted:
            self.settings.update(dlg.result_settings())
            storage.save_settings(self.settings)
            self.client.set_url(self.settings["mandala_url"])
            new_set = self.settings.get("provider_set", "world")
            if new_set != old_set:
                set_provider_set(new_set)
                # Перезагружаем текущий слой, чтобы тайлы пошли с новых серверов
                self.map_view.set_layer(self.settings.get("map_layer", "sat"))
                # И подкачиваем базовые тайлы мира нового набора в фоне
                preload_world(self.settings.get("map_layer", "sat"), z_max=3)
                self.statusBar().showMessage(
                    f"Набор карт переключён: {'RU (Google/Yandex)' if new_set=='ru' else 'World (Esri/OSM)'}",
                    4000)

    # ---------- полигоны ----------
    def _refresh_polys(self):
        self.poly_list.clear()
        for p in self.polygons:
            it = QListWidgetItem(p["name"]); it.setData(Qt.UserRole, p["id"])
            self.poly_list.addItem(it)
        self._refresh_poly_points()

    def _refresh_poly_points(self):
        self.poly_points.clear()
        p = self._current_polygon()
        if not p: return
        for i, pt in enumerate(p["points"]):
            self.poly_points.addItem(f"{i+1}: {pt[0]:.6f}, {pt[1]:.6f}")

    def _current_polygon(self) -> Optional[dict]:
        it = self.poly_list.currentItem()
        if not it: return None
        pid = it.data(Qt.UserRole)
        for p in self.polygons:
            if p["id"] == pid: return p
        return None

    def _poly_selected(self):
        p = self._current_polygon()
        self._current_polygon_id = p["id"] if p else None
        self._refresh_poly_points()
        self._update_poly_color_btns()
        self._center_on_polygon()

    def _center_on_polygon(self):
        p = self._current_polygon()
        if p and p.get("points"):
            pts = p["points"]
            clat = sum(pt[0] for pt in pts) / len(pts)
            clon = sum(pt[1] for pt in pts) / len(pts)
            self.map_view.center_on(clat, clon)

    def _update_poly_color_btns(self):
        p = self._current_polygon()
        c  = (p or {}).get("color", "#3ad1ff")
        fc = (p or {}).get("fill_color", c)
        self._style_color_btn(self.poly_color_btn, c)
        self._style_color_btn(self.poly_fill_btn, fc)

    def _style_color_btn(self, btn: QPushButton, hex_color: str):
        try:
            qc = QColor(hex_color)
            yiq = (qc.red()*299 + qc.green()*587 + qc.blue()*114) / 1000
            fg = "#000" if yiq >= 140 else "#fff"
        except Exception:
            fg = "#fff"
        btn.setStyleSheet(
            f"background:{hex_color}; color:{fg}; border:1px solid #2c3a4a;"
            f"border-radius:6px; padding:6px 12px; min-height:24px;")

    def _pick_poly_color(self, field: str):
        p = self._current_polygon()
        if not p:
            QMessageBox.information(self, "Полигон", "Сначала выберите полигон."); return
        cur = p.get(field) or p.get("color") or "#3ad1ff"
        col = QColorDialog.getColor(QColor(cur), self, "Выберите цвет")
        if not col.isValid(): return
        p[field] = col.name()
        if field == "color" and not p.get("fill_color"):
            p["fill_color"] = col.name()
        storage.save_polygons(self.polygons)
        self._update_poly_color_btns()
        self.map_view.render_polygons(self.polygons)

    def _new_polygon(self):
        name, ok = QInputDialog.getText(self, "Новый полигон", "Название:")
        if not ok or not name.strip(): return
        p = {"id": uuid.uuid4().hex, "name": name.strip(), "points": []}
        self.polygons.append(p)
        storage.save_polygons(self.polygons)
        self._refresh_polys()
        for i in range(self.poly_list.count()):
            if self.poly_list.item(i).data(Qt.UserRole) == p["id"]:
                self.poly_list.setCurrentRow(i); break

    def _add_point_dialog(self):
        p = self._current_polygon()
        if not p:
            QMessageBox.information(self, "Полигон", "Сначала выберите или создайте полигон."); return
        text, ok = QInputDialog.getText(self, "Точка полигона", "Введите широту,долготу:")
        if not ok: return
        try:
            la, lo = [float(x.strip()) for x in text.replace(";",",").split(",")[:2]]
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Неверный формат"); return
        p["points"].append([la, lo])
        storage.save_polygons(self.polygons)
        self._refresh_poly_points()
        self.map_view.render_polygons(self.polygons)

    def _del_polygon(self):
        p = self._current_polygon()
        if not p: return
        if QMessageBox.question(self, "Удалить", f"Удалить полигон '{p['name']}'?") != QMessageBox.Yes:
            return
        self.polygons = [x for x in self.polygons if x["id"] != p["id"]]
        storage.save_polygons(self.polygons)
        self._refresh_polys()
        self.map_view.render_polygons(self.polygons)

    # ---------- ЗРК ----------
    def _refresh_sites(self):
        self.sites_list.clear()
        for s in self.sites:
            it = QListWidgetItem(f"{s['type']} #{s.get('label','')} ({s['lat']:.4f},{s['lon']:.4f})")
            it.setData(Qt.UserRole, s["id"])
            self.sites_list.addItem(it)

    def _current_site(self) -> Optional[dict]:
        it = self.sites_list.currentItem()
        if not it: return None
        sid = it.data(Qt.UserRole)
        for s in self.sites:
            if s["id"] == sid: return s
        return None

    def _site_selected(self):
        s = self._current_site()
        if not s: return
        self.s_type.setCurrentText(s["type"])
        self.s_label.setValue(int(s.get("label") or 0))
        self.s_lat.setValue(float(s["lat"])); self.s_lon.setValue(float(s["lon"]))
        self.s_az0.setValue(s["az_start"]); self.s_az1.setValue(s["az_end"])
        self.s_range.setValue(s.get("range_km",10))
        self._update_site_color_btns()
        self.map_view.center_on(float(s["lat"]), float(s["lon"]))

    def _on_site_selected_on_map(self, site_id: str):
        for i in range(self.sites_list.count()):
            if self.sites_list.item(i).data(Qt.UserRole) == site_id:
                self.sites_list.setCurrentRow(i)
                break

    def _update_site_color_btns(self):
        s = self._current_site()
        c  = (s or {}).get("color", "#ff6a6a")
        fc = (s or {}).get("fill_color", c)
        self._style_color_btn(self.site_color_btn, c)
        self._style_color_btn(self.site_fill_btn, fc)

    def _pick_site_color(self, field: str):
        s = self._current_site()
        if not s:
            QMessageBox.information(self, "ЗРК", "Сначала выберите точку."); return
        cur = s.get(field) or s.get("color") or "#ff6a6a"
        col = QColorDialog.getColor(QColor(cur), self, "Выберите цвет")
        if not col.isValid(): return
        s[field] = col.name()
        if field == "color" and not s.get("fill_color"):
            s["fill_color"] = col.name()
        storage.save_sites(self.sites)
        self._update_site_color_btns()
        self.map_view.render_sites(self.sites)

    def _apply_site(self):
        s = self._current_site()
        if not s:
            QMessageBox.information(self, "ЗРК", "Сначала добавьте точку через ПКМ на карте."); return
        s["type"] = self.s_type.currentText()
        s["label"] = self.s_label.value()
        s["lat"] = self.s_lat.value()
        s["lon"] = self.s_lon.value()
        s["az_start"] = self.s_az0.value()
        s["az_end"] = self.s_az1.value()
        s["range_km"] = self.s_range.value()
        storage.save_sites(self.sites)
        sid = s["id"]
        self.sites_list.blockSignals(True)
        self._refresh_sites()
        for i in range(self.sites_list.count()):
            if self.sites_list.item(i).data(Qt.UserRole) == sid:
                self.sites_list.setCurrentRow(i)
                break
        self.sites_list.blockSignals(False)
        self.map_view.render_sites(self.sites)

    def _del_site(self):
        s = self._current_site()
        if not s: return
        if QMessageBox.question(self, "Удалить", f"Удалить точку {s['type']}?") != QMessageBox.Yes:
            return
        self.sites = [x for x in self.sites if x["id"] != s["id"]]
        storage.save_sites(self.sites)
        self._refresh_sites()
        self.map_view.render_sites(self.sites)

    # ---------- камера ----------
    def _center_on_plane(self):
        fd = self._last_data
        if fd and (fd.gps_lat or fd.gps_lon):
            self.map_view.fly_to(fd.gps_lat, fd.gps_lon)
        else:
            self.statusBar().showMessage("Нет координат самолёта", 2000)

    def _toggle_follow(self, v: bool):
        self.settings["follow_plane"] = bool(v)
        storage.save_settings(self.settings)
        self.map_view.set_follow(bool(v))

    # ---------- редактирование точек полигона ----------
    def _edit_poly_point(self, item):
        p = self._current_polygon()
        if not p or item is None:
            return
        idx = self.poly_points.row(item)
        if idx < 0 or idx >= len(p["points"]):
            return
        cur_lat, cur_lon = p["points"][idx]
        text, ok = QInputDialog.getText(self, "Точка полигона",
                                        f"Точка {idx+1}. Введите широту,долготу:",
                                        text=f"{cur_lat:.6f}, {cur_lon:.6f}")
        if not ok: return
        try:
            la, lo = [float(x.strip()) for x in text.replace(";",",").split(",")[:2]]
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Неверный формат"); return
        p["points"][idx] = [la, lo]
        storage.save_polygons(self.polygons)
        self._refresh_poly_points()
        self.map_view.render_polygons(self.polygons)

    def _del_poly_point(self):
        p = self._current_polygon()
        it = self.poly_points.currentItem()
        if not p or it is None: return
        idx = self.poly_points.row(it)
        if idx < 0 or idx >= len(p["points"]): return
        if QMessageBox.question(self, "Удалить", f"Удалить точку {idx+1}?") != QMessageBox.Yes:
            return
        del p["points"][idx]
        storage.save_polygons(self.polygons)
        self._refresh_poly_points()
        self.map_view.render_polygons(self.polygons)

    # ---------- перемещение точки ЗРК на карте (drag) ----------
    def _on_site_moved(self, site_id: str, lat: float, lon: float):
        for s in self.sites:
            if s["id"] == site_id:
                s["lat"] = lat; s["lon"] = lon
                storage.save_sites(self.sites)
                self._refresh_sites()
                cur = self._current_site()
                if cur and cur["id"] == site_id:
                    self.s_lat.setValue(lat); self.s_lon.setValue(lon)
                self.map_view.render_sites(self.sites)
                return

    # ---------- ПКМ карты ----------
    def _on_map_ctx(self, action: str, lat: float, lon: float):
        if action == "add_point":
            p = self._current_polygon()
            if not p:
                QMessageBox.information(self, "Полигон", "Сначала выберите полигон."); return
            p["points"].append([lat, lon])
            storage.save_polygons(self.polygons)
            self._refresh_poly_points()
            self.map_view.render_polygons(self.polygons)
        elif action == "new_poly":
            name, ok = QInputDialog.getText(self, "Новый полигон", "Название:")
            if not ok or not name.strip(): return
            p = {"id": uuid.uuid4().hex, "name": name.strip(), "points": [[lat,lon]]}
            self.polygons.append(p)
            storage.save_polygons(self.polygons)
            self._refresh_polys()
            self.map_view.render_polygons(self.polygons)
        elif action.startswith("site_"):
            stype = action.split("_",1)[1]
            s = {
                "id": uuid.uuid4().hex, "type": stype, "label": "",
                "lat": lat, "lon": lon,
                "az_start": 0.0, "az_end": 90.0, "range_km": 10.0,
            }
            self.sites.append(s)
            storage.save_sites(self.sites)
            self._refresh_sites()
            self.map_view.render_sites(self.sites)
        elif action == "copy":
            QApplication.clipboard().setText(f"{lat:.6f}, {lon:.6f}")
            self.statusBar().showMessage(f"Скопировано: {lat:.6f}, {lon:.6f}", 3000)

    # ---------- сохранение области ----------
    def _save_area(self):
        """Сохраняет тайлы видимой области.
        По умолчанию — текущий зум ±1/+2. Если включён чекбокс «Все зумы» —
        качает ВСЕ уровни от 1 до 18 для текущей области."""
        kind = self.settings.get("map_layer", "sat")
        all_zooms = bool(self.settings.get("save_all_zooms", False))
        def _have(b):
            if not b:
                QMessageBox.warning(self, "Карта", "Не удалось получить границы."); return
            z = int(b.get("z", 14))
            if all_zooms:
                zmin, zmax = 1, 18
            else:
                zmin = max(1, z - 1)
                zmax = min(18, z + 2)
            # Для широких зум-диапазонов предупреждаем пользователя
            if all_zooms:
                # Грубая оценка: тайлов на уровень = (2^(z))^2 для всей сферы,
                # но мы качаем только видимую bbox. Предупредим, что может быть много.
                if QMessageBox.question(self, "Все зумы",
                    f"Будут скачаны тайлы для зумов {zmin}–{zmax} в видимой области.\n"
                    "Это может занять много времени и места на диске.\nПродолжить?"
                ) != QMessageBox.Yes:
                    return
            dlg = QProgressDialog("Скачивание тайлов видимой области…", "ОК", 0, 100, self)
            dlg.setWindowTitle("Сохранение области (оффлайн)")
            dlg.setMinimumDuration(0); dlg.setValue(0)
            dlg.setAutoClose(False)
            QApplication.processEvents()
            def progress(i, total):
                dlg.setMaximum(max(1,total)); dlg.setValue(i)
                QApplication.processEvents()
            new, total = download_area(kind, b["s"], b["w"], b["n"], b["e"],
                                       zmin, zmax, progress=progress)
            dlg.close()
            QMessageBox.information(self, "Готово",
                                    f"Сохранено в кэш: {new} новых тайлов из {total}\n"
                                    f"Зум-уровни: {zmin}–{zmax}\nПровайдер: {LAYER_LABELS.get(kind, kind)}")
        self.map_view.get_bounds(_have)

    # ---------- закрытие ----------
    def closeEvent(self, e):
        # Сохраняем раскладку дока перед выходом
        self._save_layout()
        try:
            self.client.stop()
        except Exception: pass
        try:
            self._tiles.stop()
        except Exception: pass
        super().closeEvent(e)