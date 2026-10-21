import sys
import os
import multiprocessing


def setup_linux_env():
    """Настройка окружения Linux до загрузки библиотек Qt и инициализации OpenGL."""
    if not sys.platform.startswith("linux"):
        return

    # 1. Принудительно используем X11 (xcb) вместо Wayland, так как QtWebEngine 
    # внутри PyInstaller часто ломает композитинг окна и RHI на Wayland
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    # 2. Передаем флаги для Chromium: отключаем песочницу (часто падает в AppImage/PyInstaller)
    # и отключаем GPU-композитинг, который вызывает ошибки QRhiGles2 на встроенной графике Linux
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    extra_flags = "--no-sandbox --ignore-gpu-blocklist --disable-gpu-compositing"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} {extra_flags}".strip()

    # 3. Опциональный жесткий фоллбэк: если запуск идет с флагом --software-gl 
    # или переменной TARGETLEAD_SOFTWARE_GL=1, полностью уходим на софтверный рендеринг
    if "--software-gl" in sys.argv or os.environ.get("TARGETLEAD_SOFTWARE_GL") == "1":
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] += " --disable-gpu"


def main():
    # ОБЯЗАТЕЛЬНО для Qt6 + QtWebEngine: задаем общий контекст OpenGL ДО создания QApplication.
    # Это устраняет ошибку: "WebEngineContext is used before QtWebEngineQuick::initialize()"
    from PySide6.QtCore import Qt, QCoreApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette, QColor
    # Импортируем WebEngineWidgets до создания экземпляра QApplication
    from PySide6 import QtWebEngineWidgets  # noqa: F401
    from app.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Тёмная палитра интерфейса
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 46))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(205, 214, 244))
    palette.setColor(QPalette.ColorRole.Base, QColor(24, 24, 37))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(30, 30, 46))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(30, 30, 46))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(205, 214, 244))
    palette.setColor(QPalette.ColorRole.Text, QColor(205, 214, 244))
    palette.setColor(QPalette.ColorRole.Button, QColor(49, 50, 68))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(205, 214, 244))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(243, 139, 168))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(137, 180, 250))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(17, 17, 27))
    app.setPalette(palette)

    app.setStyleSheet("""
        QToolTip {
            color: #cdd6f4;
            background-color: #1e1e2e;
            border: 1px solid #45475a;
        }
        QGroupBox {
            border: 1px solid #45475a;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 8px;
            font-weight: bold;
            color: #89b4fa;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QPushButton {
            background-color: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 5px 12px;
            color: #cdd6f4;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #45475a;
            border-color: #89b4fa;
        }
        QPushButton:pressed {
            background-color: #585b70;
        }
        QPushButton:disabled {
            background-color: #181825;
            color: #585b70;
            border-color: #313244;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #181825;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 4px 8px;
            color: #cdd6f4;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
            border-color: #89b4fa;
        }
        QListWidget, QTableWidget {
            background-color: #181825;
            border: 1px solid #45475a;
            border-radius: 4px;
            color: #cdd6f4;
        }
        QHeaderView::section {
            background-color: #313244;
            color: #cdd6f4;
            padding: 4px;
            border: 1px solid #45475a;
        }
        QScrollBar:vertical {
            background: #181825;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #45475a;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # Защита от открытия второго окна при вызове субпроцессов в замороженном билде
    multiprocessing.freeze_support()
    setup_linux_env()
    main()