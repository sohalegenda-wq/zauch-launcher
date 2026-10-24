import json
from pathlib import Path
from .download_manager import get_json, Downloader
from .paths import identifier

MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'

class Versions:
    def __init__(self, cache):
        self.cache = Path(cache)

    def fetch(self):
        data = get_json(MANIFEST)
        if not isinstance(data.get('versions'), list) or not all('id' in v and 'url' in v for v in data['versions']):
            raise ValueError('Некорректный манифест Mojang')
        self.cache.mkdir(parents=True, exist_ok=True)
        part = self.cache / 'manifest.tmp'
        part.write_text(json.dumps(data), 'utf-8')
        part.replace(self.cache / 'manifest.json')
        return data['versions']

    def cached(self):
        path = self.cache / 'manifest.json'
        return json.loads(path.read_text('utf-8'))['versions'] if path.exists() else []

    @staticmethod
    def fabric_loaders(version):
        identifier(version)
        return get_json(f'https://meta.fabricmc.net/v2/versions/loader/{version}')

    @staticmethod
    def metadata(version, downloader):
        identifier(version)
        manifest = get_json(MANIFEST)
        entry = next((v for v in manifest['versions'] if v['id'] == version), None)
        if not entry:
            raise ValueError('Версия отсутствует в официальном манифесте')
        path = downloader.root / 'versions' / version / (version + '.json')
        downloader.download(entry['url'], path, sha1=entry['sha1'])
        data = json.loads(path.read_text('utf-8'))
        if data['id'] != version:
            raise ValueError('Идентификатор метаданных не совпадает')
        return data
