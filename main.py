import multiprocessing
import sys

def main():
    if '--game-monitor' in sys.argv:
        from core.process_manager import monitor_main
        try:
            monitor_main()
            return 0
        except Exception:
            return 1
    if '--self-test' in sys.argv:
        from tools.self_test import run
        from pathlib import Path
        report = sys.argv[sys.argv.index('--self-test') + 1]
        try:
            return run(report)
        except Exception as exc:
            Path(report).with_suffix('.error.txt').write_text(f'{type(exc).__name__}: {exc}', 'utf-8')
            return 1
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QFont
    app = QApplication(sys.argv)
    app.setApplicationName('Zauch Launcher')
    app.setOrganizationName('Zauch')
    app.setFont(QFont('Segoe UI',10))
    from PySide6.QtCore import QLockFile
    from core.paths import data_dir
    lock = QLockFile(str(data_dir() / 'launcher.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, 'Zauch Launcher', 'Лаунчер уже открыт в другой сессии.')
        return 1
    try:
        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None,'Zauch Launcher',f'Ошибка запуска: {type(exc).__name__}: {exc}\nПроверьте settings.json в AppData/Local/ZauchLauncher.')
        return 1

if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
