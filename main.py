#!/usr/bin/env python3
from __future__ import annotations

import sys
import os


import sys as _sys


def _has_gpu() -> bool:
    """Есть ли реальный GPU (узел DRI) — иначе форсируем software-рендер."""
    import glob as _glob
    try:
        if _glob.glob("/dev/dri/card*") or _glob.glob("/dev/dri/renderD*"):
            return True
    except Exception:
        pass
    return False


def _software_gl() -> bool:
    """True, если текущую сессию нужно гнать на software-рендере (нет GPU)."""
    if not _sys.platform.startswith("linux"):
        return False
    return os.environ.get("QTWEBENGINE_FORCE_SOFTWARE", "") == "1" or not _has_gpu()


def _setup_qt_env() -> None:
    if _sys.platform == "darwin":
        os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
        os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            " ".join([
                "--disable-gpu-rasterization",
                "--disable-features=UseChromeOSDirectVideoDecoder,Vulkan",
                "--enable-features=NetworkService",
                "--no-sandbox",
            ])
        )
    elif _sys.platform.startswith("linux"):
        # Машин без рабочего GL много (ВМ, старый Mesa, Wayland без EGL):
        # форсированный GPU-path (enable-gpu-rasterization / zero-copy /
        # ignore-gpu-blocklist) там даёт "QRhiGles2: Failed to create context",
        # после чего внутренний QQuickWidget WebEngine падает с
        # "GLOzone not found" -> Aborted (core dumped).
        # Поэтому: без /dev/dri — только software (SwiftShader), с GPU —
        # штатный path + SwiftShader как fallback для WebGL.
        if _software_gl():
            # Нет GPU. Критично: НЕ форсировать GL в Chromium (--use-gl/angle),
            # иначе Ozone пытается поднять GL, падает -> "GLOzone not found".
            # Qt-сторона (scene graph QQuickWidget внутри WebEngine) переводится
            # на software-рендер => RHI/GL-контекст вообще не создаётся, значит
            # нет "QRhiGles2: Failed to create context".
            # Chromium — чистый software через --disable-gpu (без инициализации GL).
            os.environ.setdefault("QT_QUICK_BACKEND", "software")
            os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
            os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
            os.environ.setdefault(
                "QTWEBENGINE_CHROMIUM_FLAGS",
                " ".join([
                    "--disable-gpu",
                    "--disable-gpu-compositing",
                    "--disable-gpu-rasterization",
                    "--in-process-gpu",
                    "--disable-features=Vulkan",
                    "--enable-features=NetworkService",
                    "--no-sandbox",
                ])
            )
        else:
            os.environ.setdefault(
                "QTWEBENGINE_CHROMIUM_FLAGS",
                " ".join([
                    "--disable-gpu-rasterization",
                    "--disable-features=Vulkan",
                    "--enable-features=NetworkService",
                    "--no-sandbox",
                ])
            )
    else:  # Windows и прочее
        os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            " ".join([
                "--disable-gpu-rasterization",
                "--enable-features=NetworkService",
            ])
        )


_setup_qt_env()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    if _software_gl():
        # Без GPU шаринг GL-контекстов сам инициализирует GL -> тот же краш.
        # На software-сессии переводим Qt scene graph в software и НЕ шарим GL.
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        QQuickWindow.setGraphicsApi(QSGRendererInterface.Software)
    else:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Авионика")
    app.setOrganizationName("Avionics")

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