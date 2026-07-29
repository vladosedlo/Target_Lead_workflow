#!/usr/bin/env python3
"""Точка входа приложения авионики."""
from __future__ import annotations

import sys
import os

# === Платформенная настройка QtWebEngine ===
#
# На macOS QWebEngineView внутри QDockWidget падает при drag/dock операциях
# ("Compositor returned null texture"), потому что Qt пересоздаёт NSView и
# Chromium-композитор теряет GL-поверхность. Решение — layer-backed NSView
# (QT_MAC_WANTS_LAYER=1) + native window-атрибуты на виджете (см. map_view.py)
# и более консервативные флаги Chromium.
#
# На Linux (включая Intel GPU) и Windows таких проблем нет — там GPU-стек
# Chromium стабилен из коробки, костыли не нужны и даже вредны.
import sys as _sys

if _sys.platform == "darwin":
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        " ".join([
            # GPU включён, но без аппаратной растеризации — она нестабильна
            # на macOS при перепарентинге окон.
            "--disable-gpu-rasterization",
            "--disable-features=UseChromeOSDirectVideoDecoder,Vulkan",
            "--enable-features=NetworkService",
            "--no-sandbox",
        ])
    )
elif _sys.platform.startswith("linux"):
    # Linux + Intel iGPU: стандартный путь — OpenGL/EGL через Mesa.
    # Включаем GPU-растеризацию и zero-copy для максимальной плавности карты.
    # ignore-gpu-blocklist нужен для некоторых старых Intel-чипов (Chromium
    # иначе заносит их в чёрный список и откатывается на software).
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        " ".join([
            "--enable-gpu-rasterization",
            "--enable-zero-copy",
            "--ignore-gpu-blocklist",
            "--enable-features=NetworkService",
            "--no-sandbox",
        ])
    )
else:  # Windows и прочее
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        " ".join([
            "--enable-gpu-rasterization",
            "--enable-features=NetworkService",
        ])
    )

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    # AA_UseSoftwareOpenGL НЕ ставим — иначе всё уйдёт в CPU и карта будет тормозить.
    app = QApplication(sys.argv)
    app.setApplicationName("Авионика")
    app.setOrganizationName("Avionics")

    # Тёмная палитра по умолчанию через QSS
    app.setStyleSheet(_load_qss())

    w = MainWindow()
    w.show()
    return app.exec()


def _load_qss() -> str:
    return """
    /* === Базовая палитра === */
    QMainWindow, QWidget {
        background: #0d1217; color: #e6edf3;
        font-family: 'SF Pro Display','Segoe UI','Inter','Helvetica Neue',Arial;
        font-size: 13px;
    }

    /* === Доки: чёткое разделение секций === */
    QMainWindow::separator {
        background: #0a0e12;
        width: 4px; height: 4px;
    }
    QMainWindow::separator:hover { background: #2a6cff; }

    QDockWidget {
        color: #e6edf3;
        titlebar-close-icon: url(none);
        titlebar-normal-icon: url(none);
    }
    QDockWidget::title {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #1f2a36, stop:1 #161d25);
        color: #cfe0f5;
        padding: 8px 12px;
        font-weight: 700;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
        border-bottom: 1px solid #2c3a4a;
    }
    QDockWidget > QWidget {
        background: #11161c;
        border: 1px solid #1f2a36;
    }

    /* === Кнопки === */
    QPushButton {
        background: #1f2a36; border: 1px solid #2c3a4a;
        border-radius: 6px; padding: 6px 12px;
    }
    QPushButton:hover { background: #2a3849; border-color: #3a4d63; }
    QPushButton:pressed { background: #16202b; }

    /* === Поля ввода === */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #161d25; border: 1px solid #2c3a4a;
        border-radius: 5px; padding: 4px 6px; color: #e6edf3;
        selection-background-color: #2a6cff;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border-color: #3a7dff;
    }

    /* === Меню === */
    QMenuBar { background: #0d1217; border-bottom: 1px solid #1b232c; padding: 2px; }
    QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
    QMenuBar::item:selected { background: #2a3849; }
    QMenu { background: #1b232c; border: 1px solid #2c3a4a; padding: 4px; }
    QMenu::item { padding: 6px 18px; border-radius: 4px; }
    QMenu::item:selected { background: #2a3849; }
    QMenu::separator { height: 1px; background: #2c3a4a; margin: 4px 6px; }

    /* === Статус-бар === */
    QStatusBar {
        background: #0a0e12; border-top: 1px solid #1b232c;
        color: #9fb4cc;
    }

    /* === Чекбоксы === */
    QCheckBox { spacing: 6px; }

    /* === Списки === */
    QListWidget {
        background: #0f141a; border: 1px solid #2c3a4a; border-radius: 4px;
        padding: 2px;
    }
    QListWidget::item { padding: 4px 6px; border-radius: 3px; }
    QListWidget::item:selected { background: #2a6cff; color: #fff; }
    QListWidget::item:hover { background: #1b2735; }

    /* === GroupBox: визуально отделённые подсекции === */
    QGroupBox {
        background: #0f141a;
        border: 1px solid #2c3a4a; border-radius: 8px;
        margin-top: 14px; padding: 14px 10px 10px 10px;
        font-weight: 600;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px; padding: 2px 8px;
        color: #cfe0f5;
        background: #1f2a36;
        border: 1px solid #2c3a4a;
        border-radius: 4px;
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 1px;
    }

    /* === Скроллбары === */
    QScrollBar:vertical, QScrollBar:horizontal {
        background: #0d1217; border: 0;
    }
    QScrollBar:vertical { width: 10px; }
    QScrollBar:horizontal { height: 10px; }
    QScrollBar::handle {
        background: #2c3a4a; border-radius: 5px; min-height: 20px; min-width: 20px;
    }
    QScrollBar::handle:hover { background: #3a4d63; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    """


if __name__ == "__main__":
    sys.exit(main())