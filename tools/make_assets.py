"""Original vector landscapes. No Minecraft textures or third-party screenshots."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt
from PIL import Image
root = Path(__file__).resolve().parents[1] / 'assets'
for name, sky, hill, light in [('emerald', '#142e35', '#245b55', '#76d6ac'), ('amethyst', '#282441', '#51416a', '#ad9fe9')]:
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="680" viewBox="0 0 1440 680">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="{sky}"/><stop offset="1" stop-color="#111b26"/></linearGradient><linearGradient id="fade"><stop stop-color="#10191f"/><stop offset="1" stop-color="#10191f" stop-opacity="0"/></linearGradient></defs>
    <rect width="1440" height="680" fill="url(#sky)"/><circle cx="1120" cy="155" r="65" fill="{light}" opacity=".75"/>
    <path d="M400 480 650 220 790 340 1000 130 1250 390 1440 220V680H400Z" fill="{hill}" opacity=".55"/>
    <path d="m850 286 150-156 100 104-80-15-27 17-30-13z" fill="{light}" opacity=".25"/>
    <path d="M600 560 840 370 960 435 1170 280 1440 450V680H600Z" fill="{hill}"/>
    <path d="M720 600h90v-40h110v-35h90v-40h150v-40h100v40h80v45h100v150H720Z" fill="#10282c"/>
    <path d="M1000 680h120l-32-120 100-60h-40l-110 55z" fill="{light}" opacity=".18"/>
    <g fill="#102126"><path d="m1190 390-28 60h17l-30 55h29v35h23v-35h29l-30-55h18z"/><path d="m1330 420-40 80h24l-37 65h40v48h26v-48h38l-37-65h25z"/><path d="m930 465-20 45h12l-24 40h24v25h16v-25h24l-24-40h12z"/></g>
    <rect width="1100" height="680" fill="url(#fade)"/>
    <g fill="{light}" opacity=".4"><circle cx="950" cy="90" r="2"/><circle cx="1260" cy="100" r="2"/><circle cx="1360" cy="230" r="2"/><circle cx="810" cy="140" r="2"/></g></svg>'''
    (root / 'backgrounds' / (name + '.svg')).write_text(svg, 'utf-8')
app = QGuiApplication.instance() or QGuiApplication([])
img = QImage(256, 256, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
painter = QPainter(img)
QSvgRenderer(str(root / 'logo.svg')).render(painter)
painter.end()
bits = img.convertToFormat(QImage.Format.Format_RGBA8888)
pil = Image.frombytes('RGBA', (256,256), bytes(bits.bits()))
pil.save(root / 'icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
