from pathlib import Path
import os
import sys

APP_NAME = 'Zauch Launcher'
VERSION = '0.1.0'

def resource(relative: str) -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / relative

def data_dir() -> Path:
    override = os.environ.get('ZAUCH_DATA_DIR')
    root = Path(override) if override else Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'ZauchLauncher'
    root.mkdir(parents=True, exist_ok=True)
    return root

def inside(root: Path, relative: str) -> Path:
    root = root.resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root) or result == root:
        raise ValueError('Недопустимый путь файла')
    return result

def identifier(value: str) -> str:
    import re
    if not re.fullmatch(r'[A-Za-z0-9_.+\-]{1,160}', value) or value in ('.', '..'):
        raise ValueError('Недопустимый идентификатор версии')
    return value
