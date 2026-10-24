import json
import re
import shutil
import subprocess
from pathlib import Path
from minecraft_launcher_lib import runtime

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def inspect_java(path):
    path = str(path)
    if Path(path).name.lower() == 'javaw.exe':
        path = str(Path(path).with_name('java.exe'))
    result = subprocess.run([path, '-XshowSettings:properties', '-version'], capture_output=True,
                            text=True, timeout=15, creationflags=FLAGS)
    output = result.stdout + result.stderr
    match = re.search(r'java\.version\s*=\s*([^\s]+)', output)
    if result.returncode or not match:
        raise RuntimeError('Java не отвечает или не распознана')
    version = match.group(1)
    major = int(version.split('.')[1] if version.startswith('1.') else re.split(r'[.\-+]', version)[0])
    arch = re.search(r'os\.arch\s*=\s*([^\s]+)', output)
    if not arch or arch.group(1).lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('Нужна Java x64 (amd64), обнаружено: ' + (arch.group(1) if arch else 'неизвестно'))
    return dict(path=path, major=major, version=version, arch=arch.group(1))

def requirements(metadata):
    # Official javaVersion is authoritative. Legacy manifests predate this field.
    return metadata.get('javaVersion', dict(majorVersion=8, component='jre-legacy'))

def resolve_java(root, metadata, custom='', install=False, callback=None, workers=4):
    requirement = requirements(metadata)
    major = requirement['majorVersion']
    component = requirement['component']
    if custom:
        info = inspect_java(custom)
        if info['major'] != major:
            raise RuntimeError(f'Эта версия требует Java {major}; выбрана Java {info["major"]}')
        return info
    managed = runtime.get_executable_path(component, str(root))
    for candidate in (managed, shutil.which('java')):
        if candidate:
            try:
                info = inspect_java(candidate)
                if info['major'] == major:
                    return info
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
    if install:
        runtime.install_jvm_runtime(component, str(root), callback=callback, max_workers=workers)
        return resolve_java(root, metadata, install=False)
    raise RuntimeError(f'Java {major} x64 не найдена. Восстановите версию или укажите путь к Java.')

def load_metadata(root, version):
    from .paths import identifier
    identifier(version)
    data = json.loads((Path(root) / 'versions' / version / (version + '.json')).read_text('utf-8'))
    if 'inheritsFrom' in data:
        return load_metadata(root, data['inheritsFrom'])
    return data
