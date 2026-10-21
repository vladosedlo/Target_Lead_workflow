
from __future__ import annotations

import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

from .storage import TILES_DIR, DATA_DIR

STATIC_DIR = DATA_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Локальные ассеты Leaflet (скачиваются один раз)
LEAFLET_FILES = {
    "leaflet.js":  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    "leaflet.css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
}


def ensure_leaflet(timeout: float = 6.0) -> bool:
    ok = True
    for name, url in LEAFLET_FILES.items():
        p = STATIC_DIR / name
        if p.exists() and p.stat().st_size > 0:
            continue
        try:
            r = _SESSION.get(url, timeout=timeout)
            if r.status_code == 200 and r.content:
                p.write_bytes(r.content)
            else:
                ok = False
        except Exception:
            ok = False
    return ok


PROVIDERS_WORLD = {
    "sat":        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "sat_labels": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "ref":        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    "topo":       "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    "osm":        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

PROVIDERS_RU = {
    "sat":        "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "sat_labels": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "ref":        "https://mt1.google.com/vt/lyrs=h&x={x}&y={y}&z={z}",
    "topo":       "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    "osm":        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

_CURRENT_SET = "world"
PROVIDERS = dict(PROVIDERS_WORLD)


def current_provider_set() -> str:
    return _CURRENT_SET


def set_provider_set(name: str) -> None:
    global PROVIDERS, _CURRENT_SET
    _CURRENT_SET = "ru" if name == "ru" else "world"
    src = PROVIDERS_RU if _CURRENT_SET == "ru" else PROVIDERS_WORLD
    PROVIDERS.clear(); PROVIDERS.update(src)


_REFERERS = {
    "google": "https://www.google.com/maps",
    "yandex": "https://yandex.ru/maps/",
}

def _referer_for(url: str) -> str | None:
    if "google.com" in url:  return _REFERERS["google"]
    if "yandex.net" in url or "yandex.ru" in url: return _REFERERS["yandex"]
    return None

UA = "AvionicsApp/1.0 (+offline-cache)"

# Один общий пул соединений + сессия с keep-alive
_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64, max_retries=1)
_SESSION.mount("http://", _adapter); _SESSION.mount("https://", _adapter)
_SESSION.headers.update({"User-Agent": UA})

_DL_POOL = ThreadPoolExecutor(max_workers=16)
_INFLIGHT: dict = {}
_INFLIGHT_LOCK = threading.Lock()


def _tile_path(provider: str, z: int, x: int, y: int) -> Path:
    return TILES_DIR / _CURRENT_SET / provider / str(z) / str(x) / f"{y}.png"


def tile_exists(provider: str, z: int, x: int, y: int) -> bool:
    p = _tile_path(provider, z, x, y)
    return p.exists() and p.stat().st_size > 0


def _download(provider: str, z: int, x: int, y: int) -> Optional[bytes]:
    url_tmpl = PROVIDERS.get(provider)
    if not url_tmpl:
        return None
    key = (provider, z, x, y)
    with _INFLIGHT_LOCK:
        ev = _INFLIGHT.get(key)
        if ev is not None:
            wait = ev
        else:
            ev = threading.Event(); _INFLIGHT[key] = ev; wait = None
    if wait is not None:
        wait.wait(timeout=10)
        p = _tile_path(provider, z, x, y)
        return p.read_bytes() if p.exists() and p.stat().st_size > 0 else None
    try:
        url = url_tmpl.format(z=z, x=x, y=y)
        headers = {}
        ref = _referer_for(url)
        if ref: headers["Referer"] = ref
        r = _SESSION.get(url, timeout=6, headers=headers or None)
        if r.status_code == 200 and r.content:
            p = _tile_path(provider, z, x, y)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            os.replace(tmp, p)
            return r.content
    except Exception:
        pass
    finally:
        with _INFLIGHT_LOCK:
            ev2 = _INFLIGHT.pop(key, None)
        if ev2 is not None:
            ev2.set()
    return None


def get_tile(provider: str, z: int, x: int, y: int) -> Optional[bytes]:
    p = _tile_path(provider, z, x, y)
    if p.exists() and p.stat().st_size > 0:
        try:
            return p.read_bytes()
        except Exception:
            pass
    return _download(provider, z, x, y)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def _safe_write(self, data: bytes) -> None:
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        # /static/<file>
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            p = STATIC_DIR / name
            if p.exists() and p.is_file():
                ctype = "application/javascript" if name.endswith(".js") else \
                        "text/css" if name.endswith(".css") else "application/octet-stream"
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "public, max-age=2592000")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                try:
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                self._safe_write(data); return
            self.send_response(404); self.end_headers(); return
        parts = path.strip("/").split("/")
        if len(parts) == 5 and parts[0] == "tiles":
            provider = parts[1]
            try:
                z = int(parts[2]); x = int(parts[3]); y = int(parts[4].rsplit(".", 1)[0])
            except ValueError:
                self.send_response(400); self.end_headers(); return
            data = get_tile(provider, z, x, y)
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=604800")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                try:
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                self._safe_write(data)
                return
            self.send_response(502); self.end_headers(); return
        self.send_response(404); self.end_headers()


class TileServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._srv = ThreadingHTTPServer((host, port), _Handler)
        self._thr = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self.host = host
        self.port = self._srv.server_address[1]

    def start(self):
        self._thr.start()

    def stop(self):
        try:
            self._srv.shutdown(); self._srv.server_close()
        except Exception:
            pass

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


# Утилиты для предзагрузки видимой области карты
def deg2num(lat: float, lon: float, z: int):
    lat_r = math.radians(lat)
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _expand_providers(provider: str) -> list[str]:
    """Если выбран композитный слой sat_labels — качаем и базу, и overlay."""
    if provider == "sat_labels":
        return ["sat", "ref"]
    return [provider]


def download_area(provider: str, lat1: float, lon1: float, lat2: float, lon2: float,
                  z_min: int, z_max: int, progress=None) -> tuple[int, int]:
    """Параллельно скачать тайлы для прямоугольной области."""
    south = min(lat1, lat2); north = max(lat1, lat2)
    west  = min(lon1, lon2); east  = max(lon1, lon2)
    plan = []
    for prov in _expand_providers(provider):
        for z in range(z_min, z_max + 1):
            x1, y1 = deg2num(north, west, z)
            x2, y2 = deg2num(south, east, z)
            for x in range(min(x1,x2), max(x1,x2)+1):
                for y in range(min(y1,y2), max(y1,y2)+1):
                    if not tile_exists(prov, z, x, y):
                        plan.append((prov, z, x, y))
    total = len(plan); done = 0; new = 0
    if total == 0:
        if progress: progress(1, 1)
        return 0, 0
    futures = [_DL_POOL.submit(_download, prov, z, x, y) for (prov, z, x, y) in plan]
    for f in futures:
        try:
            if f.result() is not None:
                new += 1
        except Exception:
            pass
        done += 1
        if progress:
            progress(done, total)
    return new, total


def preload_world(provider: str = "sat", z_max: int = 3,
                  progress=None, sync: bool = False) -> int:

    def _plan():
        plan = []
        for prov in _expand_providers(provider):
            for z in range(0, z_max + 1):
                n = 2 ** z
                for x in range(n):
                    for y in range(n):
                        if not tile_exists(prov, z, x, y):
                            plan.append((prov, z, x, y))
        return plan

    if not sync:
        def _run():
            for (prov, z, x, y) in _plan():
                _DL_POOL.submit(_download, prov, z, x, y)
        threading.Thread(target=_run, daemon=True).start()
        return 0

    plan = _plan()
    total = len(plan); done = 0; new = 0
    if total == 0:
        if progress: progress(1, 1)
        return 0
    futures = [_DL_POOL.submit(_download, prov, z, x, y) for (prov, z, x, y) in plan]
    for f in futures:
        try:
            if f.result() is not None:
                new += 1
        except Exception:
            pass
        done += 1
        if progress:
            progress(done, total)
    return new