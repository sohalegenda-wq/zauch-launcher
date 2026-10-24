# Лицензии и происхождение ресурсов

Исходный код Zauch и оригинальные `assets/logo.svg`, `assets/icon.ico`, `assets/backgrounds/*.svg`, а также генератор `tools/make_assets.py` предоставляются под MIT (см. LICENSE). Фоны нарисованы векторно специально для проекта. Скриншоты и игровые текстуры Minecraft не копировались. ICO конвертирован из SVG через Qt SVG и Pillow.

`assets/icons/folder-open.svg` загружен из официального репозитория [Lucide](https://github.com/lucide-icons/lucide), путь `icons/folder-open.svg`, 2026-10-24. Цвет stroke адаптирован для тёмного UI. Полный файл лицензий репозитория сохранён как `assets/icons/LUCIDE-LICENSE`; Lucide использует ISC и включает наследуемые MIT notices. Не удаляйте эти notices при распространении.

| Компонент | Лицензия | Источник |
|---|---|---|
| Python | PSF | https://www.python.org/ |
| PySide6, Shiboken, Qt | LGPL-3.0 / GPL / коммерческая, в зависимости от модуля | https://www.qt.io/licensing/ |
| minecraft-launcher-lib | BSD-2-Clause | https://codeberg.org/JakobDev/minecraft-launcher-lib |
| Requests | Apache-2.0 | https://github.com/psf/requests |
| keyring | MIT | https://github.com/jaraco/keyring |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| urllib3 | MIT | https://github.com/urllib3/urllib3 |
| charset-normalizer | MIT | https://github.com/jawah/charset_normalizer |
| idna | BSD-3-Clause | https://github.com/kjd/idna |
| pywin32-ctypes (Windows backend) | BSD-3-Clause | https://github.com/enthought/pywin32-ctypes |
| PyInstaller, build tool | GPL-2.0 with bootloader exception | https://pyinstaller.org/ |
| Pillow, asset build tool | MIT-CMU | https://python-pillow.github.io/ |
| pytest, test tool | MIT | https://pytest.org/ |

Полные доступные notices зависимостей помещены в `licenses/` и metadata пакетов в сборке. Build-инструменты не включаются в runtime намеренно; QtGui/Widgets/Svg используются динамически, WebEngine/QML исключены из сборки.

При распространении бинарной версии сохраните лицензии Qt и исходный проект/инструкции пересборки. Пользователь вправе изменять/заменять LGPL-компоненты и выполнять необходимый для их отладки reverse engineering. Чтобы заменить Qt, установите совместимую изменённую сборку PySide6/Qt в `.venv` и повторите `build.bat`, убрав строку установки зависимостей, если она перезаписывает вашу сборку. Исходники используемой открытой версии Qt/PySide доступны на https://code.qt.io/ и https://download.qt.io/; издатель бинарной сборки отвечает за выполнение условий LGPL для своей поставки и предоставление соответствующего исходного кода.

Minecraft — продукт Mojang/Microsoft. Игровые файлы и Java Runtime скачиваются пользователем отдельно с официальных серверов и подчиняются собственным условиям. Лаунчер не предоставляет лицензию на игру и не распространяет её клиент.
