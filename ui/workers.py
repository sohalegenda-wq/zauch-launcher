import threading
from PySide6.QtCore import QThread, Signal
from core.download_manager import Cancelled

class Worker(QThread):
    event = Signal(dict)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)
    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancel = threading.Event()
    def run(self):
        try:
            result = self.fn(self.cancel, self.event.emit)
            self.result.emit(result)
        except Cancelled as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
