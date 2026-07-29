"""Диалоги: ввод пароля и собственно настройки (URL mandala)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QLineEdit, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QMessageBox, QFormLayout,
                              QCheckBox)


class PasswordDialog(QDialog):
    def __init__(self, expected: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Доступ к настройкам")
        self._expected = expected
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Введите пароль для доступа к настройкам:"))
        self.edit = QLineEdit(); self.edit.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.edit)
        row = QHBoxLayout()
        ok = QPushButton("OK"); cancel = QPushButton("Отмена")
        ok.clicked.connect(self._check); cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(ok); row.addWidget(cancel)
        lay.addLayout(row)
        self.edit.returnPressed.connect(self._check)

    def _check(self):
        if self.edit.text() == self._expected:
            self.accept()
        else:
            QMessageBox.warning(self, "Ошибка", "Неверный пароль")
            self.edit.clear()


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.resize(480, 160)
        self._settings = dict(settings)

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit(self._settings.get("mandala_url", ""))
        form.addRow("Ссылка mandala:", self.url_edit)
        self.pwd_edit = QLineEdit(self._settings.get("settings_password", ""))
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Пароль настроек:", self.pwd_edit)

        # RU-провайдеры: Google спутник/гибрид + Yandex карты — больше
        # подписей и лучшее качество спутника в СНГ.
        self.ru_cb = QCheckBox("RU-провайдеры")
        self.ru_cb.setChecked(self._settings.get("provider_set", "world") == "ru")
        form.addRow("Карты:", self.ru_cb)
        lay.addLayout(form)

        row = QHBoxLayout()
        save = QPushButton("Сохранить"); cancel = QPushButton("Отмена")
        save.clicked.connect(self._save); cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(save); row.addWidget(cancel)
        lay.addLayout(row)

    def _save(self):
        self._settings["mandala_url"] = self.url_edit.text().strip() or self._settings["mandala_url"]
        self._settings["settings_password"] = self.pwd_edit.text() or self._settings["settings_password"]
        self._settings["provider_set"] = "ru" if self.ru_cb.isChecked() else "world"
        self.accept()

    def result_settings(self) -> dict:
        return self._settings