import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from .paths import data_dir, identifier

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Database:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'launcher.sqlite3'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
              base TEXT NOT NULL, kind TEXT NOT NULL, root TEXT NOT NULL, game_dir TEXT NOT NULL,
              options TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS installations(root TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL,
              updated TEXT NOT NULL, PRIMARY KEY(root,version));
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, name TEXT NOT NULL, skin TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS launches(id INTEGER PRIMARY KEY, profile TEXT, name TEXT, version TEXT,
              started TEXT, ended TEXT, exit_code INTEGER);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def profiles(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM profiles ORDER BY name')]

    def profile(self, pid):
        return next((p for p in self.profiles() if p['id'] == pid), None)

    @staticmethod
    def validate_game_dir(root, game_dir):
        if not str(game_dir).strip():
            raise ValueError('Укажите отдельную папку игры')
        root = Path(root).resolve()
        game = Path(game_dir).resolve()
        if root.is_relative_to(game) or any(game.is_relative_to(root / part) for part in ('versions', 'libraries', 'assets', 'runtime', '.zauch')):
            raise ValueError('Папка профиля должна быть отдельно от служебных файлов Minecraft')
        return game

    def create_profile(self, name, version, base, kind, root, game_dir=None):
        identifier(version); identifier(base)
        pid = uuid.uuid4().hex
        game_dir = str(Path(game_dir or self.root / 'instances' / pid).resolve())
        self.validate_game_dir(root, game_dir).mkdir(parents=True, exist_ok=True)
        if not name.strip():
            raise ValueError('Введите имя профиля')
        with self.connect() as db:
            db.execute('INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?)',
                       (pid, name.strip(), version, base, kind, str(Path(root).resolve()), game_dir, '{}'))
        return pid

    def update_profile(self, pid, name, game_dir, options):
        if not name.strip():
            raise ValueError('Введите имя профиля')
        profile = self.profile(pid)
        if not profile:
            raise ValueError('Профиль не найден')
        self.validate_game_dir(profile['root'], game_dir).mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('UPDATE profiles SET name=?,game_dir=?,options=? WHERE id=?',
                       (name.strip(), str(Path(game_dir).resolve()), json.dumps(options), pid))

    def delete_profile(self, pid):
        # Worlds, mods and shared installation files deliberately remain on disk.
        with self.connect() as db:
            db.execute('DELETE FROM profiles WHERE id=?', (pid,))

    def installation(self, root, version, status):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO installations VALUES(?,?,?,?)', (str(Path(root).resolve()), version, status, now()))

    def installations(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM installations ORDER BY updated DESC')]

    def remove_installation(self, root, version):
        with self.connect() as db:
            db.execute('DELETE FROM installations WHERE root=? AND version=?', (str(Path(root).resolve()), version))

    def account(self, aid, name, skin=''):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO accounts VALUES(?,?,?)', (aid, name, skin))

    def accounts(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM accounts ORDER BY name')]

    def remove_account(self, aid):
        with self.connect() as db:
            db.execute('DELETE FROM accounts WHERE id=?', (aid,))

    def start_launch(self, profile):
        with self.connect() as db:
            return db.execute('INSERT INTO launches(profile,name,version,started) VALUES(?,?,?,?)',
                (profile['id'], profile['name'], profile['version'], now())).lastrowid

    def finish_launch(self, lid, code):
        with self.connect() as db:
            db.execute('UPDATE launches SET ended=?,exit_code=? WHERE id=?', (now(), code, lid))

    def history(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM launches ORDER BY id DESC LIMIT 20')]
