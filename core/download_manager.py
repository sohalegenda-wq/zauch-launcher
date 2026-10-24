"""Verified, cancellable, atomic downloads. No invented aggregate size."""
import hashlib
import json
import lzma
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .paths import inside

class Cancelled(Exception):
    pass

def session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=('GET',))
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.headers['User-Agent'] = 'ZauchLauncher/0.1.0'
    return s

def validate_url(url):
    u = urlparse(url)
    host = (u.hostname or '').lower()
    trusted = ('mojang.com', 'minecraft.net', 'fabricmc.net')
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443) or not any(host == h or host.endswith('.' + h) for h in trusted):
        raise ValueError('Источник загрузки не разрешён: ' + host)
    return url

def get_json(url):
    validate_url(url)
    with session() as s:
        with s.get(url, timeout=(15, 60), allow_redirects=False) as r:
            r.raise_for_status()
            if r.status_code != 200:
                raise RuntimeError('Неожиданный HTTP статус')
            return r.json()

def sha1_file(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha1').hexdigest()

class Downloader:
    def __init__(self, root, cancel=None, emit=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cancel = cancel or threading.Event()
        self.emit = emit or (lambda e: None)
        self.records = {}
        self.known_hashes = {}
        self.lock = threading.Lock()
        self.bytes = 0
        self.started = time.monotonic()

    def check(self):
        if self.cancel.is_set():
            raise Cancelled('Установка отменена. Повторная установка восстановит файлы.')

    def download(self, url, path, callback=None, sha1=None, lzma_compressed=False,
                 session=None, minecraft_directory=None, overwrite=False):
        validate_url(url)
        path = Path(path).resolve()
        inside(self.root, str(path.relative_to(self.root)))
        self.check()
        cache_hash = sha1 or self.known_hashes.get(str(path.relative_to(self.root)))
        if path.is_file() and not overwrite and (cache_hash is None or sha1_file(path) == cache_hash):
            self.record(path, sha1)
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + '.zauch.part')
        error = None
        for attempt in range(3):
            self.check()
            try:
                with globals()['session']() as client:
                    with client.get(url, stream=True, timeout=(15, 45), allow_redirects=False) as r:
                        r.raise_for_status()
                        if r.status_code != 200:
                            raise RuntimeError(f'HTTP {r.status_code}')
                        length = int(r.headers.get('Content-Length', '0'))
                        current = 0
                        last = 0
                        with part.open('wb') as f:
                            for chunk in r.iter_content(128 * 1024):
                                self.check()
                                f.write(chunk)
                                current += len(chunk)
                                with self.lock:
                                    self.bytes += len(chunk)
                                    transferred = self.bytes
                                tick = time.monotonic()
                                if tick - last > .15:
                                    self.emit(dict(type='bytes', file=path.name, current=current, total=length,
                                        transferred=transferred, speed=transferred / max(.1, tick - self.started)))
                                    last = tick
                        if lzma_compressed:
                            raw = part.with_suffix('.raw')
                            try:
                                with lzma.open(part, 'rb') as source, raw.open('wb') as target:
                                    while chunk := source.read(128 * 1024):
                                        self.check()
                                        target.write(chunk)
                                os.replace(raw, part)
                            finally:
                                raw.unlink(missing_ok=True)
                        if sha1 and sha1_file(part) != sha1:
                            raise ValueError('Не совпадает SHA-1: ' + path.name)
                        self.check()
                        os.replace(part, path)
                        self.record(path, sha1)
                        return True
            except Cancelled:
                raise
            except (requests.RequestException, OSError, ValueError, lzma.LZMAError, RuntimeError) as exc:
                error = exc
                self.emit(dict(type='status', text=f'Повтор {attempt+1}/3: {path.name}'))
                if self.cancel.wait(.5 * (attempt+1)):
                    self.check()
            finally:
                part.unlink(missing_ok=True)
        raise RuntimeError(f'Загрузка {path.name} не выполнена: {error}') from None

    def record(self, path, expected=None):
        with self.lock:
            self.records[str(path.relative_to(self.root))] = dict(sha1=expected or sha1_file(path), size=path.stat().st_size)

    def save_inventory(self, version):
        from .paths import identifier
        target = self.root / '.zauch' / (identifier(version) + '.json')
        target.parent.mkdir(exist_ok=True)
        part = target.with_suffix('.tmp')
        part.write_text(json.dumps(self.records, indent=2), 'utf-8')
        os.replace(part, target)

def verify_inventory(root, version, cancel=None, emit=None):
    from .paths import identifier
    root = Path(root)
    path = root / '.zauch' / (identifier(version) + '.json')
    records = json.loads(path.read_text('utf-8'))
    if not records:
        raise RuntimeError('Пустой список проверки. Восстановите установку.')
    for i, (name, info) in enumerate(records.items()):
        if cancel and cancel.is_set():
            raise Cancelled('Проверка отменена')
        f = inside(root, name)
        if not f.is_file() or f.stat().st_size != info['size'] or sha1_file(f) != info['sha1']:
            raise RuntimeError('Повреждён или отсутствует файл: ' + name + '. Нажмите «Восстановить».')
        if emit and i % 30 == 0:
            emit(dict(type='progress', value=i+1, maximum=len(records), text='Проверка файлов'))
