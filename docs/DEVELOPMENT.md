# Технические решения

Перед реализацией проверены установленные сигнатуры и исходники minecraft-launcher-lib **8.0** (`install`, `runtime`, `command`, `microsoft_account`, `mod_loader`), документация PyInstaller о `_MEIPASS`/`sys.executable` и Microsoft о PKCE/state/public clients. Qt-виджеты проверяются в реальном offscreen QApplication.

- Список и version JSON приходят через `piston-meta.mojang.com`, SHA-1 JSON сверяется с version manifest. Применяются документированные `install.install_libraries`, `install.install_assets`, `runtime.install_jvm_runtime`, `runtime.get_executable_path`, `command.get_minecraft_command`.
- В библиотеке v8 загрузчик файлов может вернуть False при HTTP ошибке. Поэтому в **изолированном дочернем процессе** зависимости установки адаптированы к собственному загрузчику: raise при ошибке, HTTPS allowlist, таймауты, retries, atomic replace, hash, реальный byte progress, safe extraction. Это локальная адаптация границ модулей `install`/`runtime` для зафиксированной v8, а не подмена установки UI-анимацией. При обновлении библиотеки обязательно перепроверить эти точки.
- Upstream `fabric` deprecated, новый `mod_loader.install` запускает скачанный installer JAR. Zauch использует официальный Fabric Meta profile JSON, устанавливает его Maven-библиотеки через `install_libraries`, сохраняет `inheritsFrom` и копирует проверенный vanilla JAR под ID Fabric, который ожидает сборщик classpath библиотеки. Сторонний код установщика не исполняется.
- Из native ZIP не допускаются symlink и выход из каталога. Каждый сетевой destination проверяется относительно корня Minecraft. Remote game mainClass и JVM-аргументы берутся только из доверенных метаданных Mojang/Fabric; произвольный shell не используется.
- Qt Worker испускает сигналы прогресса, результата, ошибки, отмены. UI не обращается к виджетам из worker. SQLite-соединение создаётся на операцию, в том потоке, где используется.
- Runtime download и file installation отменяются через multiprocessing event; зависший child завершается после grace period. Результат установки подтверждается полным inventory и наличием classpath.
- Для game monitor `PYINSTALLER_RESET_ENVIRONMENT=1` обеспечивает независимую распаковку one-file EXE, когда родительский UI закрывается. Команда и токен передаются по stdin, а не через JSON-файл. Monitor исполняет `subprocess.Popen`, читает stdout/stderr, скрывает access token, обновляет SQLite и state JSON. Включена подстановка официальной logging config.
- Изменяемые данные отделены от `_MEIPASS`. `resource()` работает в исходниках и frozen приложении. `multiprocessing.freeze_support()` вызывается до загрузки UI.

Документация:

- https://minecraft-launcher-lib.readthedocs.io/en/stable/
- https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html
- https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- https://pyinstaller.org/en/stable/runtime-information.html
- https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
- https://wiki.fabricmc.net/documentation:fabric_meta

Рекомендуемый end-to-end Windows acceptance: зарегистрировать собственный public Client ID с допуском Minecraft API; войти законным аккаунтом; установить релиз с Java 8/17/21 по его метаданным; запустить/завершить Vanilla; установить совместимый Fabric; убедиться в его mainClass; прервать загрузку и восстановить; повредить asset и восстановить; создать мир и проверить ZIP backup при закрытой игре; закрыть UI во время игры и проверить запись exit code; повторить основные действия в EXE. Эти проверки не заменяются unit fixtures.
