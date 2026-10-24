import json
import os
import shlex
import sys
from pathlib import Path
import psutil
from .paths import data_dir

def safe_ram() -> int:
    return max(512, int(psutil.virtual_memory().total / 1024**2 * 0.7) // 256 * 256)

def defaults():
    return dict(minecraft_dir=str(data_dir() / 'minecraft'), cache_dir=str(data_dir() / 'cache'),
                min_ram=512, max_ram=min(4096, safe_ram()), width=1280, height=720,
                fullscreen=False, java='', jvm_args='', game_args='', verify=True,
                remember=True, launch_behavior='open', theme='dark', accent='green',
                animations=True, background='emerald', workers=4, selected_profile='',
                active_account='', oauth_client_id='', oauth_port=53682, autostart=False)

class Settings:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'settings.json'
        self.values = defaults()
        if self.path.exists():
            self.values.update(json.loads(self.path.read_text('utf-8')))
        self.validate(self.values)

    @staticmethod
    def validate(v):
        for field in ('minecraft_dir', 'cache_dir'):
            if not str(v[field]).strip() or not Path(v[field]).is_absolute():
                raise ValueError('Для игровых файлов и кэша нужен полный путь к папке')
        if not 256 <= int(v['min_ram']) <= int(v['max_ram']) <= safe_ram():
            raise ValueError(f'RAM должна быть в диапазоне 256–{safe_ram()} МБ; минимум ≤ максимум')
        if not 1 <= int(v['workers']) <= 16:
            raise ValueError('Число загрузок: от 1 до 16')
        if not 640 <= int(v['width']) <= 16384 or not 480 <= int(v['height']) <= 16384:
            raise ValueError('Недопустимое разрешение')
        if not 1024 <= int(v['oauth_port']) <= 65535:
            raise ValueError('Недопустимый OAuth порт')
        # Parse now so malformed quoting fails before launching.
        shlex.split(v['jvm_args'])
        args = shlex.split(v['game_args'])
        protected = ('--accesstoken', '--username', '--uuid', '--usertype', '--gamedir', '--version', '--demо', '--demo')
        if any(a.lower().split('=')[0] in protected for a in args):
            raise ValueError('Параметры аккаунта, версии и папки задаёт лаунчер')
        if any(a.lower().startswith(('-xmx', '-xms')) for a in shlex.split(v['jvm_args'])):
            raise ValueError('Задайте память в полях RAM')
        if v['launch_behavior'] not in ('open', 'minimize', 'close'):
            raise ValueError('Неизвестное поведение после запуска')

    def save(self, updates=None):
        updated = dict(self.values, **(updates or {}))
        self.validate(updated)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(temp, self.path)
        self.values = updated

    def __getitem__(self, key):
        return self.values[key]

def set_autostart(enabled: bool):
    if sys.platform != 'win32':
        if enabled:
            raise RuntimeError('Автозапуск доступен только в Windows')
        return
    import winreg
    command = subprocess_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            winreg.SetValueEx(key, 'ZauchLauncher', 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, 'ZauchLauncher')
            except FileNotFoundError:
                pass

def subprocess_command():
    import subprocess
    exe = sys.executable
    args = [exe] if getattr(sys, 'frozen', False) else [exe, str(Path(__file__).resolve().parents[1] / 'main.py')]
    return subprocess.list2cmdline(args)
