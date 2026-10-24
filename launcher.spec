# Build on Windows for Windows. One-file, windowed, dynamically linked Qt.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata
root = Path(SPECPATH)
datas = [(str(root / 'assets'), 'assets'), (str(root / 'ui' / 'styles.qss'), 'ui'),
         (str(root / 'docs'), 'docs'), (str(root / 'README.md'), '.'),
         (str(root / 'THIRD_PARTY.md'), '.'), (str(root / 'LICENSE'), '.'),
         (str(root / 'licenses'), 'licenses')]
for package in ('minecraft-launcher-lib','requests','keyring','psutil','PySide6'):
    datas += copy_metadata(package)
hidden = collect_submodules('minecraft_launcher_lib')
if sys.platform == 'win32':
    hidden += ['keyring.backends.Windows', 'win32ctypes.pywin32.win32cred', 'win32ctypes.pywin32.win32api']
a = Analysis([str(root / 'main.py')], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=hidden, hookspath=[], runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Zauch Launcher', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon=str(root / 'assets' / 'icon.ico') if sys.platform == 'win32' else None)
