import json
import subprocess
import sys
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from core.paths import resource

def run(report):
    app = QApplication.instance() or QApplication([])
    from ui.main_window import MainWindow
    window = MainWindow(startup_network=False)
    window.show()
    for index in range(window.stack.count()):
        window.navigate(index)
        app.processEvents()
    window.settings.save({'animations':False})
    window.navigate(0)
    loop = QEventLoop()
    QTimer.singleShot(250,loop.quit)
    loop.exec()
    destination = Path(report)
    destination.parent.mkdir(parents=True,exist_ok=True)
    window.grab().save(str(destination.with_suffix('.png')))
    for name in ('assets/icon.ico','assets/logo.svg','assets/backgrounds/emerald.svg','assets/backgrounds/amethyst.svg','ui/styles.qss','docs/OAUTH.md','THIRD_PARTY.md'):
        if not resource(name).is_file():
            raise FileNotFoundError(name)
    pages = window.stack.count()
    window.close()
    import threading
    from core.minecraft_manager import install_in_process
    probe_ok = False
    try:
        install_in_process(dict(root=str(destination.parent / 'probe'), base='..', version='probe'), threading.Event(), lambda e: None)
    except RuntimeError as exc:
        probe_ok = 'Недопустимый' in str(exc)
    if not probe_ok:
        raise RuntimeError('Installer subprocess smoke-test failed')
    vault_status = 'not-windows'
    if sys.platform == 'win32':
        import uuid
        from keyring.backends.Windows import WinVaultKeyring
        vault = WinVaultKeyring()
        key = uuid.uuid4().hex
        try:
            vault.set_password('ZauchLauncher.Smoke', key, 'smoke-test-value')
            if vault.get_password('ZauchLauncher.Smoke', key) != 'smoke-test-value':
                raise RuntimeError('Credential Manager smoke-test failed')
            vault_status = 'passed'
        finally:
            vault.delete_password('ZauchLauncher.Smoke', key)
    result = {'credential_vault':vault_status, 'pages':pages,'resources':True,'settings_saved':True,'frozen':bool(getattr(sys,'frozen',False)), 'installer_subprocess':probe_ok}
    destination.write_text(json.dumps(result,indent=2),'utf-8')
    return 0
