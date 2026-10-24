import json
import os
import shutil
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QPushButton, QFrame,
    QComboBox, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QSpinBox, QCheckBox, QFormLayout, QGroupBox, QProgressBar, QPlainTextEdit,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QInputDialog, QApplication,
    QAbstractItemView, QGraphicsOpacityEffect,
)
from core.paths import data_dir, resource, inside, identifier, VERSION
from core.settings_manager import Settings, safe_ram, set_autostart
from core.profile_manager import Database
from core.version_manager import Versions
from core.auth_manager import Auth
from core.download_manager import verify_inventory, Cancelled
from core.minecraft_manager import install_in_process, fabric_version, build_command
from core.java_manager import load_metadata, resolve_java, inspect_java
from core.process_manager import start_supervised
from core.worlds_manager import worlds, backup_world
from .workers import Worker
from .widgets import label, button, row, page, Hero, TitleBar

class MainWindow(QMainWindow):
    def __init__(self, startup_network=True):
        super().__init__()
        self.settings = Settings()
        self.db = Database()
        self.auth = Auth(self.settings, self.db)
        self.catalog = []
        self.worker = None
        self.install_payload = None
        self.game = None
        self.log_offset = 0
        self.log_file = None
        self._closing = False
        self.setWindowTitle('Zauch Launcher')
        self.setWindowIcon(QIcon(str(resource('assets/icon.ico'))))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1120, 760)
        self.setMinimumSize(1000, 680)
        shell = QWidget()
        shell.setObjectName('shell')
        self.setCentralWidget(shell)
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(1,1,1,1)
        outer.setSpacing(0)
        outer.addWidget(TitleBar(self))
        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14,24,14,20)
        logo = label()
        logo.setPixmap(QPixmap(str(resource('assets/logo.svg'))).scaled(48,48,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        side.addWidget(row(logo, label('ZAUCH', 'brand')))
        side.addWidget(label('       LAUNCHER  /  JAVA', 'muted'))
        side.addSpacing(28)
        self.nav = []
        for i, name in enumerate(['Главная', 'Играть', 'Установленные версии', 'Установка версий', 'Модификации', 'Аккаунты', 'Настройки', 'Журнал ошибок', 'О программе']):
            b = button(name, lambda checked=False, i=i: self.navigate(i))
            b.setObjectName('nav')
            b.setCheckable(True)
            self.nav.append(b)
            side.addWidget(b)
        side.addStretch()
        side.addWidget(label('ТВОЁ СЛЕДУЮЩЕЕ\nПРИКЛЮЧЕНИЕ', 'eyebrow'))
        side.addWidget(label(f'Zauch {VERSION}', 'muted'))
        body.addWidget(sidebar)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.make_home()
        self.make_play()
        self.make_installed()
        self.make_versions()
        self.make_mods()
        self.make_accounts()
        self.make_settings()
        self.make_logs()
        self.make_about()
        self.make_downloads()
        self.status = label('Готов к приключениям', 'muted')
        self.status.setContentsMargins(230,8,18,8)
        outer.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_game)
        self.timer.start(700)
        self.apply_theme()
        self.refresh()
        self.restore_session()
        self.navigate(0)
        if startup_network:
            QTimer.singleShot(250, self.initial_catalog)

    def notify(self, text, error=False):
        text = self.auth.redact(str(text))
        self.status.setText(text[:180])
        self.append_log(text)
        if error:
            QMessageBox.warning(self, 'Zauch Launcher', text)

    def append_log(self, text):
        text = self.auth.redact(str(text))
        if hasattr(self, 'console'):
            self.console.appendPlainText(text)
        path = data_dir() / 'logs' / 'launcher.log'
        path.parent.mkdir(exist_ok=True)
        if path.exists() and path.stat().st_size > 4 * 1024**2:
            path.replace(path.with_suffix('.previous.log'))
        with path.open('a', encoding='utf-8') as f:
            f.write(text + '\n')

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav):
            b.setChecked(i == index)
        if self.settings['animations']:
            effect = QGraphicsOpacityEffect(self.stack.currentWidget())
            self.stack.currentWidget().setGraphicsEffect(effect)
            self.animation = QPropertyAnimation(effect, b'opacity', self)
            self.animation.setDuration(160)
            self.animation.setStartValue(.45)
            self.animation.setEndValue(1.)
            self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.animation.start()
        if index == 1:
            self.refresh_worlds()

    def open_dir(self, path):
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.resolve()))):
            self.notify('Не удалось открыть папку: ' + str(p), True)

    def open_document(self, relative):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(resource(relative))))

    def selected_profile(self):
        return self.db.profile(self.profile_combo.currentData())

    def profile_changed(self):
        pid = self.profile_combo.currentData() or ''
        if self.settings['remember']:
            self.settings.save({'selected_profile': pid})
        self.refresh_home()
        self.refresh_worlds()

    def make_home(self):
        p, layout = page('Добро пожаловать в Zauch', 'Твой лаунчер. Твои миры. Твои правила.')
        self.stack.addWidget(p)
        self.hero = Hero()
        self.hero.action.clicked.connect(self.home_action)
        layout.addWidget(self.hero)
        layout.addWidget(label('ТВОЯ УСТАНОВКА', 'eyebrow'))
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self.profile_changed)
        layout.addWidget(self.profile_combo)
        card = QFrame()
        card.setObjectName('card')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20,16,20,16)
        self.home_details = label('', wrap=True)
        card_layout.addWidget(self.home_details)
        layout.addWidget(card)
        layout.addWidget(row(button('Quick Play  →', self.quick_play), button('Управлять профилями', lambda: self.navigate(2)), button('Проверить Java', self.diagnose_java)))
        self.stats = label('', 'muted', True)
        layout.addWidget(self.stats)
        layout.addStretch()

    def refresh_home(self):
        p = self.selected_profile()
        account = next((a['name'] for a in self.db.accounts() if a['id'] == self.settings['active_account']), 'не выбран')
        self.hero.background = self.settings['background']
        self.hero.update()
        installed = any(i['status'] == 'ready' and p and i['version'] == p['version'] and i['root'] == p['root'] for i in self.db.installations())
        self.hero.action.setText('ИГРАТЬ' if installed else 'УСТАНОВИТЬ')
        if p:
            options = dict(self.settings.values, **json.loads(p['options']))
            self.home_details.setText(f'{p["name"]}  •  Minecraft {p["version"]}  •  {p["kind"]}\n'
                f'Статус: {"установлена" if installed else "нужна установка / восстановление"}    |    Аккаунт: {account}\n'
                f'RAM: {options["min_ram"]}–{options["max_ram"]} МБ    |    Java: {options["java"] or "авто · проверка при запуске"}')
            self.hero.detail.setText(f'{p["kind"]}  /  {p["base"]}  /  {p["name"]}')
        else:
            self.home_details.setText(f'Профиль пока не создан. Установи первую версию Minecraft.\nАккаунт: {account}  •  RAM: {self.settings["max_ram"]} МБ')
            self.hero.detail.setText('Выбери версию. Создай свою историю.')
        history = self.db.history()
        count = sum(i['status'] == 'ready' for i in self.db.installations())
        last = history[0] if history else None
        self.stats.setText(f'Установок: {count}    •    Последний запуск: ' +
            (f'{last["version"]} · {self.display_time(last["started"])} · ' + ('игра работает' if last['ended'] is None else f'код {last["exit_code"]}') if last else 'ещё не было') +
            f'\nЗагрузки: {"идёт операция" if self.worker else "нет активных"}    •    Записей в истории: {len(history)} (последние 20)')

    @staticmethod
    def display_time(value):
        from datetime import datetime
        return datetime.fromisoformat(value).astimezone().strftime('%d.%m.%Y %H:%M') if value else '—'

    def home_action(self):
        p = self.selected_profile()
        if p and any(i['root'] == p['root'] and i['version'] == p['version'] and i['status'] == 'ready' for i in self.db.installations()):
            self.launch()
        elif p:
            self.repair(p)
        else:
            self.navigate(3)

    def quick_play(self):
        history = self.db.history()
        p = self.db.profile(history[0]['profile']) if history else self.selected_profile()
        if p:
            self.profile_combo.setCurrentIndex(self.profile_combo.findData(p['id']))
            self.launch()
        else:
            self.navigate(3)

    def make_play(self):
        p, layout = page('Играть', 'Запусти выбранный на главной странице профиль или сохрани свои миры.')
        self.stack.addWidget(p)
        self.play_details = label('', wrap=True)
        layout.addWidget(self.play_details)
        layout.addWidget(row(button('ИГРАТЬ', self.launch, True), button('Папка игры', self.open_game_dir), button('Папка модов', self.open_mods)))
        layout.addWidget(label('ZAUCH WORLDS', 'eyebrow'))
        self.world_list = QListWidget()
        layout.addWidget(self.world_list)
        layout.addWidget(row(button('Обновить миры', self.refresh_worlds), button('Открыть сохранения', self.open_saves), button('Резервная копия мира', self.backup)))
        self.history_label = label('', 'muted', True)
        layout.addWidget(self.history_label)

    def open_game_dir(self):
        if p := self.selected_profile():
            self.open_dir(p['game_dir'])
        else:
            self.notify('Сначала выберите профиль', True)

    def open_mods(self):
        if p := self.selected_profile():
            self.open_dir(Path(p['game_dir']) / 'mods')
        else:
            self.notify('Сначала выберите профиль', True)

    def open_saves(self):
        if p := self.selected_profile():
            self.open_dir(Path(p['game_dir']) / 'saves')

    def refresh_worlds(self):
        if not hasattr(self, 'world_list'):
            return
        self.world_list.clear()
        p = self.selected_profile()
        self.play_details.setText((p['name'] + '  /  ' + p['version']) if p else 'На главной странице выбери профиль для запуска.')
        if p:
            self.world_list.addItems([w.name for w in worlds(p['game_dir'])])
        history = self.db.history()
        self.history_label.setText('\n'.join(f'{self.display_time(h["started"])}  ·  {h["name"]}  ·  {h["version"]}  ·  {"работает" if h["ended"] is None else "код " + str(h["exit_code"])}' for h in history[:5]) or 'Запусков ещё не было')

    def backup(self):
        p = self.selected_profile()
        item = self.world_list.currentItem()
        if not p or not item:
            return self.notify('Выберите мир', True)
        if self.game:
            return self.notify('Закройте Minecraft перед резервным копированием, чтобы сохранить согласованные файлы мира.', True)
        name = item.text()
        self.start_job(lambda c,e: backup_world(p['game_dir'], name, c, e), lambda path: self.notify('Резервная копия: ' + path), 'Резервное копирование мира')

    def make_installed(self):
        p, layout = page('Установленные версии', 'Профили разделяют библиотеки, а миры и моды хранят в собственных папках.')
        self.stack.addWidget(p)
        self.profile_table = QTableWidget(0,4)
        self.profile_table.setHorizontalHeaderLabels(['Профиль', 'Версия', 'Тип', 'Статус'])
        self.profile_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.profile_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.profile_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.profile_table)
        layout.addWidget(row(button('Выбрать', self.choose_profile), button('Новый профиль', self.new_profile), button('Изменить', self.edit_profile), button('Удалить профиль', self.delete_profile)))
        layout.addWidget(row(button('Играть', self.launch_table_profile, True), button('Восстановить', self.repair_selected), button('Папка установки', self.open_install_root), button('Удалить версию', self.delete_version)))
        self.installations_text = label('', 'muted', True)
        layout.addWidget(self.installations_text)

    def table_profile(self):
        r = self.profile_table.currentRow()
        item = self.profile_table.item(r, 0) if r >= 0 else None
        return self.db.profile(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def choose_profile(self):
        if p := self.table_profile():
            self.profile_combo.setCurrentIndex(self.profile_combo.findData(p['id']))
            self.notify('Выбран профиль: ' + p['name'])

    def launch_table_profile(self):
        self.choose_profile()
        if self.table_profile():
            self.launch()

    def new_profile(self):
        ready = [i for i in self.db.installations() if i['status'] == 'ready']
        if not ready:
            return self.navigate(3)
        choices = [i['version'] + '  ·  ' + i['root'] for i in ready]
        choice, ok = QInputDialog.getItem(self, 'Новый профиль', 'Установка', choices, editable=False)
        if not ok:
            return
        name, ok = QInputDialog.getText(self, 'Новый профиль', 'Название профиля')
        if ok and name.strip():
            i = ready[choices.index(choice)]
            old = next((p for p in self.db.profiles() if p['root'] == i['root'] and p['version'] == i['version']), None)
            if old:
                pid = self.db.create_profile(name, i['version'], old['base'], old['kind'], i['root'])
            else:
                pid = self.db.create_profile(name, i['version'], i['version'], 'Vanilla', i['root'])
            self.refresh(pid)

    def edit_profile(self):
        p = self.table_profile()
        if not p:
            return self.notify('Выберите профиль в таблице', True)
        dialog = QDialog(self)
        dialog.setWindowTitle('Настройки профиля')
        dialog.resize(580,330)
        layout = QFormLayout(dialog)
        name = QLineEdit(p['name'])
        directory = QLineEdit(p['game_dir'])
        opts = dict(self.settings.values, **json.loads(p['options']))
        low = self.spin(256, safe_ram(), opts['min_ram'], 256)
        high = self.spin(256, safe_ram(), opts['max_ram'], 256)
        java = QLineEdit(opts['java'])
        layout.addRow('Название', name)
        layout.addRow('Папка игры', row(directory, button('…', lambda: self.pick_directory(directory))))
        layout.addRow('Минимум RAM, МБ', low)
        layout.addRow('Максимум RAM, МБ', high)
        layout.addRow('Java (пусто = авто)', row(java, button('…', lambda: self.pick_file(java))))
        layout.addRow(label('Изменение папки не переносит сохранения автоматически.', 'muted', True))
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(actions)
        def save():
            try:
                overrides = dict(min_ram=low.value(), max_ram=high.value(), java=java.text().strip())
                Settings.validate(dict(self.settings.values, **overrides))
                self.db.update_profile(p['id'], name.text(), directory.text(), overrides)
                dialog.accept()
                self.refresh(p['id'])
            except Exception as exc:
                self.notify(str(exc), True)
        actions.accepted.connect(save)
        actions.rejected.connect(dialog.reject)
        dialog.exec()

    def delete_profile(self):
        if self.worker or self.game:
            return self.notify('Дождитесь завершения операции или игры', True)
        p = self.table_profile()
        if p and QMessageBox.question(self, 'Удалить профиль?', f'Удалить запись «{p["name"]}»? Миры и игровые файлы останутся на диске.') == QMessageBox.StandardButton.Yes:
            self.db.delete_profile(p['id'])
            self.refresh()

    def open_install_root(self):
        if p := self.table_profile():
            self.open_dir(p['root'])

    def delete_version(self):
        if self.worker or self.game:
            return self.notify('Дождитесь завершения операции или игры', True)
        p = self.table_profile()
        if not p:
            return self.notify('Выберите профиль', True)
        text = f'Удалить файлы версии {p["version"]}? Профили и миры сохранятся. Общие библиотеки и ассеты останутся для других версий.'
        if QMessageBox.question(self, 'Удаление версии', text) != QMessageBox.StandardButton.Yes:
            return
        try:
            target = inside(Path(p['root']), 'versions/' + identifier(p['version']))
            if any(Path(other['game_dir']).resolve().is_relative_to(target) for other in self.db.profiles()) or any(target.rglob('level.dat')):
                raise RuntimeError('В каталоге версии найдены пользовательские данные. Перенесите миры и папки профилей перед удалением.')
            if target.exists():
                shutil.rmtree(target, ignore_errors=False)
            inventory = inside(Path(p['root']), '.zauch/' + identifier(p['version']) + '.json')
            inventory.unlink(missing_ok=True)
            self.db.remove_installation(p['root'], p['version'])
            self.refresh()
        except Exception as exc:
            self.notify(str(exc), True)

    def make_versions(self):
        p, layout = page('Установка версий', 'Реальные версии Minecraft из официального манифеста Mojang.')
        self.stack.addWidget(p)
        self.version_type = QComboBox()
        for title, value in [('Релизы', 'release'), ('Снапшоты', 'snapshot'), ('Старые beta / alpha', 'old'), ('Все версии', 'all')]:
            self.version_type.addItem(title, value)
        self.version_type.currentIndexChanged.connect(self.filter_versions)
        self.version_search = QLineEdit()
        self.version_search.setPlaceholderText('Найти версию…')
        self.version_search.textChanged.connect(self.filter_versions)
        layout.addWidget(row(self.version_type, self.version_search, button('Обновить список', self.fetch_catalog)))
        self.catalog_note = label('Список ещё не загружен', 'muted', True)
        layout.addWidget(self.catalog_note)
        self.version_list = QListWidget()
        self.version_list.setMinimumHeight(260)
        layout.addWidget(self.version_list)
        layout.addWidget(button('Установить выбранную версию', self.install_selected, True))
        layout.addWidget(label('Клиент, ресурсы и Java скачиваются отдельно при установке. Старые версии могут требовать совместимых драйверов и настроек.', 'muted', True))

    def initial_catalog(self):
        try:
            self.catalog = Versions(self.settings['cache_dir']).cached()
            if self.catalog:
                self.catalog_note.setText('Сохранённый официальный список; обновление…')
                self.filter_versions()
        except Exception as exc:
            self.append_log('Кэш манифеста: ' + str(exc))
        self.fetch_catalog()

    def fetch_catalog(self):
        cache = self.settings['cache_dir']
        def done(versions):
            self.catalog = versions
            self.catalog_note.setText(f'Получено из Mojang: {len(versions)} версий')
            self.filter_versions()
        self.start_job(lambda c,e: Versions(cache).fetch(), done, 'Получение списка Mojang')

    def filter_versions(self):
        if not hasattr(self, 'version_list'):
            return
        self.version_list.clear()
        kind = self.version_type.currentData()
        search = self.version_search.text().strip().lower()
        for v in self.catalog:
            if search not in v['id'].lower():
                continue
            if kind != 'all' and not (v['type'] == kind or kind == 'old' and v['type'] in ('old_beta', 'old_alpha')):
                continue
            item = QListWidgetItem(f'{v["id"]}    /    {v["type"]}    /    {v.get("releaseTime", "")[:10]}')
            item.setData(Qt.ItemDataRole.UserRole, v)
            self.version_list.addItem(item)
        if self.version_list.count():
            self.version_list.setCurrentRow(0)
        old = self.fabric_base.currentText() if hasattr(self, 'fabric_base') else ''
        if hasattr(self, 'fabric_base'):
            self.fabric_base.blockSignals(True)
            self.fabric_base.clear()
            self.fabric_base.addItems([v['id'] for v in self.catalog if v['type'] in ('release', 'snapshot')])
            if old:
                self.fabric_base.setCurrentText(old)
            self.fabric_base.blockSignals(False)

    def install_selected(self):
        item = self.version_list.currentItem()
        if not item:
            return self.notify('Загрузите список версий и выберите версию', True)
        v = item.data(Qt.ItemDataRole.UserRole)
        payload = dict(base=v['id'], version=v['id'], kind='Vanilla', loader='', root=self.settings['minecraft_dir'])
        self.begin_install(payload)

    def make_mods(self):
        p, layout = page('Модификации', 'Fabric Loader · официальные метаданные и отдельные игровые профили.')
        self.stack.addWidget(p)
        form = QFormLayout()
        self.fabric_base = QComboBox()
        self.fabric_base.currentTextChanged.connect(lambda: self.fabric_loader.clear())
        self.fabric_loader = QComboBox()
        form.addRow('Minecraft', self.fabric_base)
        form.addRow('Fabric Loader', self.fabric_loader)
        layout.addLayout(form)
        layout.addWidget(row(button('Получить совместимые загрузчики', self.fetch_loaders), button('Установить Fabric', self.install_fabric, True)))
        layout.addWidget(label('Моды устанавливаются в папку mods выбранного профиля. Лаунчер не скачивает моды из непроверенных каталогов.', 'muted', True))
        layout.addWidget(button('Открыть папку модов', self.open_mods))
        layout.addStretch()

    def fetch_loaders(self):
        base = self.fabric_base.currentText()
        if not base:
            return self.notify('Сначала получите список Minecraft', True)
        self.fabric_loader.clear()
        def done(data):
            if base != self.fabric_base.currentText():
                return
            for v in data:
                loader = v['loader']
                self.fabric_loader.addItem(loader['version'] + ('  · stable' if loader.get('stable') else ''), loader['version'])
            if not data:
                self.notify('Для этой версии Fabric не найден')
        self.start_job(lambda c,e: Versions.fabric_loaders(base), done, 'Получение загрузчиков Fabric')

    def install_fabric(self):
        base = self.fabric_base.currentText()
        loader = self.fabric_loader.currentData()
        if not base or not loader:
            return self.notify('Получите и выберите совместимый Fabric Loader', True)
        self.begin_install(dict(base=base, loader=loader, version=fabric_version(base,loader), kind='Fabric', root=self.settings['minecraft_dir']))

    def repair_selected(self):
        if p := self.table_profile():
            self.repair(p)

    def repair(self, p):
        loader = p['version'][len('fabric-loader-'):-(len(p['base'])+1)] if p['kind'] == 'Fabric' else ''
        self.begin_install(dict(root=p['root'], version=p['version'], base=p['base'], kind=p['kind'], loader=loader), p)

    def begin_install(self, payload, profile=None):
        if self.worker or self.game:
            return self.notify('Дождитесь завершения текущей операции или игры', True)
        payload.update(workers=self.settings['workers'], java=(dict(self.settings.values, **json.loads(profile['options']))['java'] if profile else payload.get('java', self.settings['java'])))
        payload['root'] = str(Path(payload['root']).resolve())
        self.install_payload = payload
        self.db.installation(payload['root'], payload['version'], 'installing')
        self.download_title.setText('Установка Minecraft ' + payload['version'])
        self.download_bar.setRange(0,0)
        self.download_file.setText('Ожидание метаданных')
        self.download_bytes.setText('Размер всей установки пока неизвестен')
        self.navigate(9)
        def done(version):
            self.db.installation(payload['root'], version, 'ready')
            existing = next((p for p in self.db.profiles() if p['version'] == version and p['root'] == payload['root']), None)
            pid = existing['id'] if existing else self.db.create_profile(payload['kind'] + ' ' + payload['base'], version, payload['base'], payload['kind'], payload['root'])
            self.install_payload = None
            self.refresh(pid)
            self.download_bar.setRange(0,1)
            self.download_bar.setValue(1)
            self.download_status.setText('Установка и проверка файлов завершены')
            self.notify('Версия готова к запуску: ' + version)
        self.start_job(lambda c,e: install_in_process(payload,c,e), done, 'Установка Minecraft', is_install=True)

    def make_accounts(self):
        p, layout = page('Аккаунты', 'Microsoft Account · вход в системном браузере · токены в защищённом хранилище Windows.')
        self.stack.addWidget(p)
        self.account_list = QListWidget()
        self.account_list.currentItemChanged.connect(self.show_account_skin)
        layout.addWidget(self.account_list)
        self.skin_label = label('Выберите аккаунт для просмотра профиля', 'muted', True)
        layout.addWidget(self.skin_label)
        layout.addWidget(row(button('Войти через Microsoft', self.login, True), button('Сделать активным', self.activate_account), button('Обновить токен', self.refresh_account), button('Выйти', self.logout)))
        layout.addWidget(row(button('Настройка Microsoft OAuth', lambda: self.open_document('docs/OAUTH.md')), button('Загрузить скин', self.load_skin)))
        layout.addWidget(label('Для запуска требуется подтверждённый доступ к Minecraft Java Edition. Client ID задаётся в настройках. Пароли не сохраняются.', 'muted', True))

    def current_account(self):
        item = self.account_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def show_account_skin(self):
        a = self.current_account()
        self.skin_label.clear()
        self.skin_label.setText(a['name'] + ('  · активный' if a['id'] == self.settings['active_account'] else '') if a else 'Аккаунтов пока нет')
        if a and a['skin']:
            path = Path(self.settings['cache_dir']) / 'skins' / (a['id'] + '.png')
            if path.is_file():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    # Show actual downloaded skin texture, preserving all player pixels.
                    self.skin_label.setPixmap(pix.scaled(256,256,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))

    def login(self):
        def done(profile):
            self.settings.save({'active_account': profile['id']})
            self.refresh()
            self.notify('Вход выполнен: ' + profile['name'])
        self.start_job(self.auth.login, done, 'Вход Microsoft')

    def activate_account(self):
        if a := self.current_account():
            self.settings.save({'active_account': a['id']})
            self.refresh()
            self.notify('Активный аккаунт: ' + a['name'])

    def refresh_account(self):
        if a := self.current_account():
            self.start_job(lambda c,e: self.auth.refresh(a['id'],force=True), lambda p: (self.refresh(),self.notify('Токен обновлён: ' + p['name'])), 'Обновление Microsoft Account')

    def logout(self):
        if self.worker:
            return self.notify('Дождитесь завершения операции', True)
        if a := self.current_account():
            try:
                self.auth.logout(a['id'])
                if self.settings['active_account'] == a['id']:
                    self.settings.save({'active_account': ''})
                self.refresh()
            except Exception as exc:
                self.notify(str(exc), True)

    def load_skin(self):
        a = self.current_account()
        if not a or not a['skin']:
            return self.notify('Скин аккаунта отсутствует', True)
        url = a['skin'].replace('http://textures.minecraft.net/', 'https://textures.minecraft.net/')
        root = Path(self.settings['cache_dir']) / 'skins'
        def task(c,e):
            from core.download_manager import Downloader
            Downloader(root,c,e).download(url, root / (identifier(a['id']) + '.png'))
        self.start_job(task, lambda _: self.show_account_skin(), 'Загрузка скина')

    @staticmethod
    def spin(low, high, value, step=1):
        box = QSpinBox()
        box.setRange(low,high)
        box.setSingleStep(step)
        box.setValue(value)
        return box

    def make_settings(self):
        p, layout = page('Настройки', 'Параметры сохраняются в AppData. Отдельные профили могут переопределять Java и RAM.')
        self.stack.addWidget(p)
        self.controls = {}
        def group(title):
            box = QGroupBox(title)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.addWidget(box)
            return form
        def text(form, key, title, pick=None):
            widget = QLineEdit(str(self.settings[key]))
            self.controls[key] = widget
            if pick:
                form.addRow(title, row(widget, button('…', lambda: self.pick_directory(widget) if pick == 'dir' else self.pick_file(widget))))
            else:
                form.addRow(title, widget)
        def number(form,key,title,low,high,step=1):
            widget = self.spin(low,high,self.settings[key],step)
            self.controls[key] = widget
            form.addRow(title,widget)
        def check(form,key,title):
            widget = QCheckBox(title)
            widget.setChecked(self.settings[key])
            self.controls[key] = widget
            form.addRow(widget)
        def choice(form,key,title,values):
            widget = QComboBox()
            for name,value in values:
                widget.addItem(name,value)
            widget.setCurrentIndex(max(0,widget.findData(self.settings[key])))
            self.controls[key] = widget
            form.addRow(title,widget)
        game = group('Игра и производительность')
        preset = QComboBox()
        preset.addItems(['Пользовательский', 'Экономный', 'Сбалансированный', 'Производительный'])
        def change_preset(index):
            if index:
                self.controls['max_ram'].setValue(min(safe_ram(), [0,2048,4096,8192][index]))
                self.controls['min_ram'].setValue(min(512,self.controls['max_ram'].value()))
        preset.currentIndexChanged.connect(change_preset)
        game.addRow('Zauch Performance',preset)
        number(game,'min_ram','Минимум RAM, МБ',256,safe_ram(),256)
        number(game,'max_ram','Максимум RAM, МБ',256,safe_ram(),256)
        game.addRow(label(f'Безопасный предел для этого компьютера: {safe_ram()} МБ', 'muted'))
        number(game,'width','Ширина',640,16384)
        number(game,'height','Высота',480,16384)
        check(game,'fullscreen','Полноэкранный режим')
        text(game,'jvm_args','Параметры JVM')
        text(game,'game_args','Параметры игры')
        text(game,'minecraft_dir','Общие игровые файлы','dir')
        text(game,'java','Путь к Java (пусто = авто)','file')
        launcher = group('Лаунчер')
        choice(launcher,'launch_behavior','После запуска',[('Оставить открытым','open'),('Свернуть','minimize'),('Закрыть лаунчер','close')])
        check(launcher,'autostart','Автозапуск с Windows')
        check(launcher,'verify','Проверять все файлы перед запуском')
        check(launcher,'remember','Запоминать выбранный профиль')
        launcher.addRow(label('Автообновление лаунчера недоступно: официальный сервер релизов пока не настроен. Обновления устанавливаются вручную.', 'muted', True))
        visual = group('Внешний вид')
        choice(visual,'theme','Тема',[('Тёмная','dark'),('Светлая','light')])
        choice(visual,'accent','Акцент',[('Изумрудный','green'),('Фиолетовый','purple')])
        choice(visual,'background','Фон',[('Изумрудная долина','emerald'),('Аметистовые горы','amethyst')])
        check(visual,'animations','Плавные переходы страниц')
        downloads = group('Загрузки')
        number(downloads,'workers','Одновременные файлы',1,16)
        text(downloads,'cache_dir','Папка кэша','dir')
        downloads.addRow(label('Доступные SHA-1 при установке проверяются всегда.', 'muted'))
        downloads.addRow(button('Очистить кэш и временные файлы', self.clear_cache))
        oauth = group('Microsoft OAuth · публичное приложение')
        text(oauth,'oauth_client_id','Client ID')
        number(oauth,'oauth_port','Локальный порт',1024,65535)
        oauth.addRow(label('Redirect URI: http://localhost:<порт>/callback', 'muted'))
        oauth.addRow(row(button('Инструкция OAuth',lambda: self.open_document('docs/OAUTH.md')),button('Импортировать OAuth JSON',self.import_oauth)))
        layout.addWidget(button('Сохранить настройки', self.save_settings, True))
        layout.addStretch()

    def pick_directory(self, control):
        if path := QFileDialog.getExistingDirectory(self,'Выберите папку',control.text()):
            control.setText(path)

    def pick_file(self, control):
        path,_ = QFileDialog.getOpenFileName(self,'Выберите Java',control.text(),'Java (java.exe javaw.exe java);;Все файлы (*)')
        if path:
            control.setText(path)

    def import_oauth(self):
        path,_ = QFileDialog.getOpenFileName(self,'Конфигурация OAuth','','JSON (*.json)')
        if not path:
            return
        try:
            config = json.loads(Path(path).read_text('utf-8'))
            self.controls['oauth_client_id'].setText(config['oauth_client_id'])
            self.controls['oauth_port'].setValue(int(config.get('oauth_port',53682)))
            self.notify('Конфигурация загружена в форму. Нажмите «Сохранить настройки».')
        except Exception as exc:
            self.notify(str(exc),True)

    def save_settings(self):
        if self.worker:
            return self.notify('Дождитесь завершения операции перед изменением настроек', True)
        values = {}
        for key,w in self.controls.items():
            if isinstance(w,QCheckBox):
                values[key] = w.isChecked()
            elif isinstance(w,QSpinBox):
                values[key] = w.value()
            elif isinstance(w,QComboBox):
                values[key] = w.currentData()
            else:
                values[key] = w.text().strip()
        try:
            Settings.validate(dict(self.settings.values, **values))
            if values['autostart'] != self.settings['autostart']:
                set_autostart(values['autostart'])
            self.settings.save(values)
            self.apply_theme()
            self.refresh_home()
            self.notify('Настройки сохранены')
        except Exception as exc:
            self.notify(str(exc),True)

    def clear_cache(self):
        if self.worker:
            return self.notify('Сначала дождитесь завершения загрузки',True)
        # Delete only known launcher-owned cache files; never recurse through a custom folder.
        root = Path(self.settings['cache_dir'])
        for name in ('manifest.json','manifest.tmp'):
            (root / name).unlink(missing_ok=True)
        skins = root / 'skins'
        if skins.is_dir() and not skins.is_symlink():
            for f in skins.glob('*.png'):
                if f.is_file():
                    f.unlink()
        mc = Path(self.settings['minecraft_dir'])
        count = 0
        if mc.is_dir():
            for f in mc.rglob('*.zauch.part'):
                if f.is_file() and not f.is_symlink():
                    f.unlink()
                    count += 1
        self.notify(f'Кэш лаунчера очищен; временных файлов: {count}')

    def apply_theme(self):
        dark = self.settings['theme'] == 'dark'
        values = dict(BG='#11171e' if dark else '#edf2f1', PANEL='#182129' if dark else '#ffffff',
            TEXT='#eaf2ef' if dark else '#182a28', MUTED='#8b9da9' if dark else '#5d716f',
            BORDER='#2b3742' if dark else '#d4dfdc', HOVER='#233b37' if dark else '#dcece5',
            ACCENT='#6ce5b1' if self.settings['accent'] == 'green' else '#b5a3ff')
        qss = resource('ui/styles.qss').read_text('utf-8')
        for k,v in values.items():
            qss = qss.replace('@'+k,v)
        self.setStyleSheet(qss)

    def make_logs(self):
        p, layout = page('Zauch Console', 'Диагностика лаунчера, Java и вывода игрового процесса. Токены скрываются.')
        self.stack.addWidget(p)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(6000)
        self.console.setStyleSheet('font-family: Consolas, monospace; font-size: 12px;')
        layout.addWidget(self.console,1)
        layout.addWidget(row(button('Папка журналов',lambda: self.open_dir(data_dir()/'logs')),button('Очистить экран',self.console.clear),button('Сохранить показанный журнал',self.export_log),button('Диагностика Java',self.diagnose_java)))

    def export_log(self):
        path,_ = QFileDialog.getSaveFileName(self,'Сохранить журнал','zauch-log.txt','Текст (*.txt)')
        if path:
            try:
                Path(path).write_text(self.auth.redact(self.console.toPlainText()),'utf-8')
                self.notify('Журнал сохранён')
            except OSError as exc:
                self.notify(str(exc),True)

    def diagnose_java(self):
        p = self.selected_profile()
        if p:
            opts = dict(self.settings.values,**json.loads(p['options']))
            def task(c,e):
                return resolve_java(p['root'],load_metadata(p['root'],p['version']),opts['java'])
        else:
            custom = self.settings['java']
            def task(c,e):
                import shutil
                path = custom or shutil.which('java')
                if not path:
                    raise RuntimeError('Java пока не найдена. Установите версию Minecraft для загрузки runtime.')
                return inspect_java(path)
        self.start_job(task,lambda info:self.notify(f'Java {info["version"]} {info["arch"]}\n{info["path"]}'),'Диагностика Java')

    def make_about(self):
        p, layout = page('Zauch Launcher', 'Независимый лаунчер Minecraft Java Edition для Windows 10/11 x64.')
        self.stack.addWidget(p)
        layout.addWidget(label(f'Версия {VERSION}\n\nНативный интерфейс PySide6. Установка из официальных метаданных Mojang и Fabric.\n\nНе является продуктом Mojang или Microsoft и не связан с ними. Для игры требуется законный доступ к Java Edition.\n\nЛаунчер не содержит игровых файлов, рекламы или телеметрии.',wrap=True))
        layout.addWidget(row(button('README',lambda:self.open_document('README.md')),button('Лицензии и источники',lambda:self.open_document('THIRD_PARTY.md')),button('Папка данных',lambda:self.open_dir(data_dir()))))
        layout.addStretch()

    def make_downloads(self):
        p, layout = page('Центр загрузок', 'Реальный прогресс текущего этапа и объём переданных по сети данных.')
        self.stack.addWidget(p)
        self.download_title = label('Нет активной установки','heading',True)
        self.download_status = label('Готов к загрузке',wrap=True)
        self.download_file = label('', 'muted',True)
        self.download_bytes = label('', 'muted',True)
        self.download_bar = QProgressBar()
        self.download_bar.setRange(0,1)
        layout.addWidget(self.download_title)
        layout.addWidget(self.download_status)
        layout.addWidget(self.download_bar)
        layout.addWidget(self.download_file)
        layout.addWidget(self.download_bytes)
        layout.addWidget(label('Процент относится к текущему этапу: библиотеки, ассеты или runtime. Общий размер заранее неизвестен. Повторно используются только проверенные файлы.', 'muted',True))
        layout.addWidget(row(button('Отменить операцию',self.cancel_job),button('Повторить установку',self.retry_install),button('Открыть журнал',lambda:self.navigate(7))))
        layout.addStretch()

    def retry_install(self):
        if self.install_payload:
            self.begin_install(dict(self.install_payload))
        elif p := self.selected_profile():
            self.repair(p)
        else:
            self.navigate(3)

    def handle_progress(self,event):
        kind = event.get('type')
        if kind == 'status':
            self.download_status.setText(event['text'])
            self.status.setText(event['text'][:180])
        elif kind == 'progress':
            self.download_bar.setRange(0,max(1,int(event['maximum'])))
            self.download_bar.setValue(int(event['value']))
            if event.get('text'):
                self.download_status.setText(event['text'])
        elif kind == 'bytes':
            self.download_file.setText('Файл: ' + event['file'])
            current = event['current']/1024**2
            total = f'{event["total"]/1024**2:.2f} МБ' if event['total'] else 'неизвестен'
            self.download_bytes.setText(f'Файл: {current:.2f} / {total}  ·  Передано: {event["transferred"]/1024**2:.1f} МБ  ·  Средняя скорость: {event["speed"]/1024**2:.2f} МБ/с')

    def start_job(self,fn,done,title,is_install=False):
        if self.worker:
            self.notify('Уже выполняется операция. Дождитесь её завершения или отмените.',True)
            return False
        self.status.setText(title)
        self.job_is_install = is_install
        worker = Worker(fn,self)
        self.worker = worker
        worker.event.connect(self.handle_progress)
        worker.result.connect(done)
        worker.failed.connect(self.job_failed)
        worker.cancelled.connect(self.job_cancelled)
        worker.finished.connect(self.job_finished)
        worker.start()
        self.refresh_home()
        return True

    def job_failed(self,text):
        if getattr(self, 'job_is_install', False) and self.install_payload:
            p = self.install_payload
            self.db.installation(p['root'],p['version'],'failed')
            self.download_status.setText('Ошибка. Повторная установка восстановит недостающие файлы.')
        self.notify(text,True)

    def job_cancelled(self,text):
        if getattr(self, 'job_is_install', False) and self.install_payload:
            p = self.install_payload
            self.db.installation(p['root'],p['version'],'incomplete')
        self.download_status.setText(text)
        self.notify(text)

    def job_finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.deleteLater()
        self.refresh()
        if self._closing:
            self.close()

    def cancel_job(self):
        if self.worker:
            self.worker.cancel.set()
            self.status.setText('Отмена операции…')

    def launch(self):
        if self.game or self.worker:
            return self.notify('Уже выполняется операция или игра',True)
        profile = self.selected_profile()
        if not profile:
            return self.notify('Сначала создайте и выберите профиль',True)
        ready = any(i['root']==profile['root'] and i['version']==profile['version'] and i['status']=='ready' for i in self.db.installations())
        if not ready:
            return self.notify('Версия не установлена полностью. Нажмите «Восстановить».',True)
        settings = dict(self.settings.values)
        account_id = settings['active_account']
        if not account_id:
            self.navigate(5)
            return self.notify('Войдите в Microsoft Account с доступом к Java Edition',True)
        def task(cancel,emit):
            emit(dict(type='status',text='Проверка авторизации Microsoft'))
            account = self.auth.refresh(account_id)
            if cancel.is_set():
                raise Cancelled('Запуск отменён')
            options = dict(settings,**json.loads(profile['options']))
            if settings['verify']:
                verify_inventory(profile['root'],profile['version'],cancel,emit)
            metadata = load_metadata(profile['root'],profile['version'])
            java = resolve_java(profile['root'],metadata,options['java'])
            args = build_command(profile,settings,account,java['path'])
            if cancel.is_set():
                raise Cancelled('Запуск отменён')
            return start_supervised(profile,args,account['access_token'],self.db)
        self.start_job(task,self.game_started,'Подготовка к запуску Minecraft')

    def game_started(self,state):
        self.game = state
        self.log_offset = 0
        self.log_file = Path(state['log'])
        self.notify('Игровой процесс запущен')
        behavior = self.settings['launch_behavior']
        if behavior == 'minimize':
            self.showMinimized()
        elif behavior == 'close':
            self._closing = True
            # job_finished closes after the preparation QThread has stopped.

    def restore_session(self):
        import psutil
        for launch in self.db.history():
            if launch['ended'] is not None:
                continue
            path = data_dir() / 'sessions' / (str(launch['id']) + '.json')
            try:
                state = json.loads(path.read_text('utf-8'))
                if state['status'] == 'running':
                    proc = psutil.Process(state['pid'])
                    if abs(proc.create_time() - state['process_created']) < 1:
                        self.game = state
                        self.log_file = Path(state['log'])
                        self.log_offset = 0
                        self.status.setText('Minecraft уже запущен · восстановлено наблюдение')
                        return
                self.db.finish_launch(launch['id'], state.get('exit_code', -1))
            except (OSError, KeyError, ValueError, psutil.Error):
                self.db.finish_launch(launch['id'], -1)

    def poll_game(self):
        if not self.game:
            return
        try:
            if self.log_file and self.log_file.is_file():
                with self.log_file.open('r',encoding='utf-8',errors='replace') as f:
                    f.seek(self.log_offset)
                    text = f.read(256*1024)
                    self.log_offset = f.tell()
                if text:
                    self.console.appendPlainText(self.auth.redact(text.rstrip()))
            path = data_dir()/'sessions'/(str(self.game['launch_id'])+'.json')
            state = json.loads(path.read_text('utf-8'))
            if state['status'] in ('exited','failed'):
                code = state.get('exit_code',-1)
                self.game = None
                self.notify('Minecraft завершился с кодом ' + str(code),code != 0)
                self.showNormal()
                self.refresh()
        except (OSError,json.JSONDecodeError):
            pass

    def refresh(self,select=None):
        profiles = self.db.profiles()
        selected = select or self.profile_combo.currentData() or (self.settings['selected_profile'] if self.settings['remember'] else '')
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in profiles:
            self.profile_combo.addItem(p['name']+'  ·  '+p['version'],p['id'])
        index = self.profile_combo.findData(selected)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        if select and self.settings['remember']:
            self.settings.save({'selected_profile':select})
        installations = self.db.installations()
        self.profile_table.setRowCount(len(profiles))
        for row_index,p in enumerate(profiles):
            status = next((i['status'] for i in installations if i['version']==p['version'] and i['root']==p['root']),'не установлена')
            for col,value in enumerate([p['name'],p['version'],p['kind'],status]):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole,p['id'])
                self.profile_table.setItem(row_index,col,item)
        if profiles:
            self.profile_table.selectRow(0)
        self.installations_text.setText('Файлы на диске:\n'+'\n'.join(f'{i["version"]}  ·  {i["status"]}  ·  {i["root"]}' for i in installations))
        aid = self.current_account()['id'] if self.current_account() else self.settings['active_account']
        self.account_list.clear()
        for a in self.db.accounts():
            item = QListWidgetItem(a['name']+('  ✓ активный' if a['id']==self.settings['active_account'] else ''))
            item.setData(Qt.ItemDataRole.UserRole,a)
            self.account_list.addItem(item)
            if a['id']==aid:
                self.account_list.setCurrentItem(item)
        self.refresh_home()
        self.refresh_worlds()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.windowHandle() and not self.isMaximized():
            pos = event.position()
            edges = Qt.Edge(0)
            if pos.x()<7: edges |= Qt.Edge.LeftEdge
            if pos.x()>self.width()-7: edges |= Qt.Edge.RightEdge
            if pos.y()<7: edges |= Qt.Edge.TopEdge
            if pos.y()>self.height()-7: edges |= Qt.Edge.BottomEdge
            if edges:
                self.windowHandle().startSystemResize(edges)
        super().mousePressEvent(event)

    def closeEvent(self,event):
        if self.worker:
            self._closing = True
            self.worker.cancel.set()
            self.status.setText('Завершение фоновой операции…')
            event.ignore()
            return
        # The independent supervisor continues logging and recording the game exit.
        event.accept()
