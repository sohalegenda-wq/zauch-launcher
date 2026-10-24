# Фактическая проверка — 24 октября 2026

## Windows: сборка выполнена успешно

[GitHub Actions: Build Windows launcher, запуск № 1](https://github.com/sohalegenda-wq/zauch-launcher/actions/runs/40070540317)

Коммит исполняемого кода: `0823b926ec94387ac0d782eaa680a8164957cd82`.

- Windows runner, Python 3.12 x64: **42 теста прошли за 3,57 с**.
- PyInstaller создал настоящий `dist/Zauch Launcher.exe` с оконной подсистемой.
- Упакованный EXE прошёл smoke-test: **10 страниц** Qt, ресурсы, сохранение настроек.
- `multiprocessing spawn` проверен в собранном EXE; тест намеренно отклоняет недопустимый ID версии до сетевого запроса.
- **Windows Credential Manager: passed** — временная тестовая запись создана, прочитана и удалена через WinVaultKeyring.
- Независимый упакованный game monitor проверен безопасным Python-процессом: тестовый токен скрыт, код завершения сохранён в SQLite.
- Артефакт **Zauch-Launcher-Windows-x64**: ZIP около 54 МБ, содержит `Zauch Launcher.exe`.

[Скачать ZIP с Windows EXE](https://github.com/sohalegenda-wq/zauch-launcher/actions/runs/40070540317/artifacts/12551385809). Для артефактов GitHub может потребоваться вход в аккаунт. Артефакт хранится до 22 января 2027; затем запустите workflow повторно. Authenticode-подпись не настроена.

Результаты: `docs/evidence/windows-ci.json`, `docs/evidence/windows-ci.txt`. Последующие изменения документации и архива исходников не изменяют исполняемый код.

## Linux: предыдущие проверки

CPython 3.12.14, Linux x86_64: **42 теста прошли**, реальный Qt offscreen UI, SHA-1/atomic downloads/cancellation/retries/LZMA, SQLite, профили, ZIP backup, запрет небезопасных путей, Java major/x64, Vanilla/Fabric command generation через minecraft-launcher-lib.

Локальный OAuth callback реально проверен по HTTP: неверный state → 400, верный → 200; PKCE S256 verifier/challenge соответствуют друг другу. Внешние токенные ответы в unit-тестах — явные fixtures, не реальная авторизация.

Также собран и проверен Linux ELF one-file: frozen UI/resources, installer subprocess и независимый monitor. ELF не выдаётся за Windows EXE. Скриншот: `docs/ui-preview.png`; отчёты: `docs/evidence/*linux*`.

## Что ещё не проверено

В этой сессии не предоставлены Microsoft Client ID с необходимыми разрешениями Minecraft API и лицензированный аккаунт. Поэтому **настоящие вход/refresh/logout, загрузка Minecraft/Java/Fabric и фактический игровой процесс не проверены end-to-end**.

В Linux-среде live-запросы к Mojang и Fabric заблокированы облачным прокси: CONNECT **403 Forbidden**, см. `docs/evidence/network-linux.json`. Windows CI выполняет unit/smoke-проверки и сборку; он не имитирует успешную сетевую установку или запуск игры.

Для end-to-end acceptance настройте OAuth по `docs/OAUTH.md`, войдите законным аккаунтом, установите Vanilla/Fabric на разрешённой сети, запустите игру, проверьте отмену/восстановление, повреждённый asset и backup закрытого мира.

Автообновление лаунчера не реализовано: нет подписанного канала релизов; UI сообщает об этом. Quilt/NeoForge не заявлены.
