from datetime import datetime
from pathlib import Path
import os
import zipfile
from .paths import inside, data_dir

def worlds(game_dir):
    saves = Path(game_dir) / 'saves'
    if not saves.exists():
        return []
    return [p for p in sorted(saves.iterdir()) if p.is_dir() and not p.is_symlink() and (p / 'level.dat').is_file()]

def backup_world(game_dir, name, cancel=None, emit=None):
    saves = Path(game_dir) / 'saves'
    world = inside(saves, name)
    if world not in worlds(game_dir):
        raise ValueError('Мир не найден')
    root = data_dir() / 'backups'
    root.mkdir(parents=True, exist_ok=True)
    target = root / (world.name + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.zip')
    part = target.with_suffix('.part')
    try:
        with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as archive:
            for folder, dirs, files in os.walk(world, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
                for name in files:
                    if cancel and cancel.is_set():
                        from .download_manager import Cancelled
                        raise Cancelled('Резервное копирование отменено')
                    path = Path(folder) / name
                    if path.is_symlink():
                        continue
                    archive.write(path, path.relative_to(world.parent))
        part.replace(target)
        return str(target)
    finally:
        part.unlink(missing_ok=True)
