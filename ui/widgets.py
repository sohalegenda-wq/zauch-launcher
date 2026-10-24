from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap, QIcon
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea, QSizePolicy
from core.paths import resource

def label(text='', name='', wrap=False):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    w.setTextFormat(Qt.TextFormat.PlainText)
    return w

def button(text, action, primary=False):
    w = QPushButton(text)
    if text.startswith(('Папка', 'Открыть')):
        w.setIcon(QIcon(str(resource('assets/icons/folder-open.svg'))))
    if primary:
        w.setObjectName('primary')
    w.clicked.connect(action)
    return w

def row(*widgets):
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0,0,0,0)
    for w in widgets:
        layout.addWidget(w)
    return box

def page(title, subtitle):
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28,22,28,24)
    layout.setSpacing(16)
    layout.addWidget(label(title, 'heading'))
    layout.addWidget(label(subtitle, 'muted', True))
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll, layout

class Hero(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(290)
        self.background = 'emerald'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30,28,30,28)
        self.top = label('Z A U C H   /   J A V A   E D I T I O N', 'eyebrow')
        layout.addWidget(self.top)
        headline = label('Твой мир\nначинается здесь')
        headline.setStyleSheet('font-size: 36px; font-weight: 800; color: #f0f8f5;')
        layout.addWidget(headline)
        self.detail = label('Выбери версию. Создай свою историю.')
        self.detail.setStyleSheet('color: #b6cdc6;')
        layout.addWidget(self.detail)
        layout.addStretch()
        self.action = QPushButton('УСТАНОВИТЬ')
        self.action.setObjectName('primary')
        self.action.setFixedWidth(210)
        layout.addWidget(self.action)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PySide6.QtGui import QPainterPath
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 16,16)
        painter.setClipPath(clip)
        pix = QPixmap(str(resource('assets/backgrounds/' + self.background + '.svg')))
        painter.drawPixmap(self.rect(), pix)
        painter.end()

class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setFixedHeight(42)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16,3,8,3)
        layout.addWidget(label('Zauch Launcher', 'muted'))
        layout.addStretch()
        for text, action in [('—', window.showMinimized), ('□', self.maximize), ('×', window.close)]:
            b = button(text, action)
            b.setObjectName('window')
            b.setFixedSize(38,30)
            layout.addWidget(b)
    def maximize(self):
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self, event):
        self.maximize()
