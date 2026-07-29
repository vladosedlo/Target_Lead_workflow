"""Клиент опроса XML-данных от mandala с частотой 10 Гц.

Детектирует «замороженные» данные: если значения roll/pitch/yaw/altitude/airspeed
не меняются дольше N секунд — считается, что связи нет, даже если HTTP отвечает.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from PySide6.QtCore import QObject, QThread, Signal, QMutex, QMutexLocker


@dataclass
class FlightData:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    altitude: float = 0.0
    airspeed: float = 0.0
    vspeed: float = 0.0
    course: float = 0.0
    rpm: float = 0.0
    agl: float = 0.0
    wind_spd: float = 0.0
    wind_hdg: float = 0.0
    g_speed: float = 0.0
    cmd_roll: float = 0.0
    cmd_pitch: float = 0.0
    ctr_throttle: float = 0.0
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    ts: float = field(default_factory=time.time)


# Теги, которые парсим
_TAGS = {
    "roll": "roll", "pitch": "pitch", "yaw": "yaw",
    "altitude": "altitude", "airspeed": "airspeed", "vspeed": "vspeed",
    "course": "course", "rpm": "rpm", "agl": "agl",
    "windSpd": "wind_spd", "windHdg": "wind_hdg",
    "gSpeed": "g_speed",
    "cmd_roll": "cmd_roll", "cmd_pitch": "cmd_pitch",
    "ctr_throttle": "ctr_throttle",
    "gps_lat": "gps_lat", "gps_lon": "gps_lon",
}

_PATTERNS = {tag: re.compile(rf"<{tag}>([-+0-9.eE]+)</{tag}>") for tag in _TAGS}


def parse_xml(text: str) -> FlightData:
    fd = FlightData()
    for tag, attr in _TAGS.items():
        m = _PATTERNS[tag].search(text)
        if m:
            try:
                setattr(fd, attr, float(m.group(1)))
            except ValueError:
                pass
    return fd


class _Worker(QObject):
    data_ready = Signal(object)        # FlightData
    link_status = Signal(bool, str)    # (ok, reason)

    def __init__(self, get_url, period_ms: int = 100, freeze_timeout: float = 3.0):
        super().__init__()
        self._get_url = get_url
        self._period = period_ms / 1000.0
        self._freeze_timeout = freeze_timeout
        self._stop = False
        self._mutex = QMutex()
        self._last_change_ts = time.time()
        self._last_signature: Optional[tuple] = None
        self._session = requests.Session()

    def stop(self):
        with QMutexLocker(self._mutex):
            self._stop = True

    def _stopped(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._stop

    def run(self):
        while not self._stopped():
            t0 = time.time()
            url = self._get_url()
            try:
                r = self._session.get(url, timeout=0.5)
                if r.status_code == 200 and r.text:
                    fd = parse_xml(r.text)
                    sig = (fd.roll, fd.pitch, fd.yaw, fd.altitude, fd.airspeed, fd.gps_lat, fd.gps_lon)
                    now = time.time()
                    if sig != self._last_signature:
                        self._last_signature = sig
                        self._last_change_ts = now
                    frozen = (now - self._last_change_ts) > self._freeze_timeout
                    self.data_ready.emit(fd)
                    if frozen:
                        self.link_status.emit(False, "Данные заморожены")
                    else:
                        self.link_status.emit(True, "OK")
                else:
                    self.link_status.emit(False, f"HTTP {r.status_code}")
            except Exception as e:
                # Не отмечаем сразу как нет связи — только если давно не менялось
                if (time.time() - self._last_change_ts) > self._freeze_timeout:
                    self.link_status.emit(False, f"Нет ответа: {type(e).__name__}")
            # Сон до следующего тика
            dt = time.time() - t0
            sleep = max(0.0, self._period - dt)
            # Дискретный сон, чтобы можно было быстро остановить
            steps = int(sleep / 0.05) + 1
            for _ in range(steps):
                if self._stopped():
                    return
                time.sleep(min(0.05, sleep))
                sleep -= 0.05
                if sleep <= 0:
                    break


class MandalaClient(QObject):
    """Высокоуровневая обёртка над фоновым потоком опроса."""
    data_ready = Signal(object)
    link_status = Signal(bool, str)

    def __init__(self, url: str = "http://127.0.0.1:9080/mandala", parent=None):
        super().__init__(parent)
        self._url = url
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None

    def set_url(self, url: str):
        self._url = url

    def url(self) -> str:
        return self._url

    def start(self):
        if self._thread:
            return
        self._thread = QThread()
        self._worker = _Worker(get_url=lambda: self._url)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.data_ready.connect(self.data_ready)
        self._worker.link_status.connect(self.link_status)
        self._thread.start()

    def stop(self):
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
            self._worker = None