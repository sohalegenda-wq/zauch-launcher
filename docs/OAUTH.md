# Настройка Microsoft OAuth

Zauch — публичное настольное приложение, Authorization Code Flow + PKCE S256 и случайный `state`. Client Secret не нужен и не поддерживается. Встроенного общего Client ID нет.

1. Откройте Microsoft Entra admin center → Identity → Applications → App registrations → New registration.
2. Зарегистрируйте приложение, поддерживающее **личные Microsoft Accounts**. Код использует tenant `consumers`. Вариант «только аккаунты организации» не подойдёт.
3. Authentication → Add a platform → **Mobile and desktop applications**. Добавьте пользовательский Redirect URI:

   ```text
   http://localhost:53682/callback
   ```

   Это loopback URI для системного браузера. Не регистрируйте его как SPA или конфиденциальное Web-приложение. При необходимости включите public client flows согласно требованиям регистрации Entra. Implicit grant не нужен.
4. Скопируйте **Application (client) ID**, а не Object ID. Он имеет вид UUID. Не создавайте Client Secret для лаунчера.
5. Учитывайте отдельную политику Minecraft Services: регистрация в Entra сама по себе **не гарантирует разрешение стороннего приложения на Xbox/Minecraft API**. Ознакомьтесь с текущими требованиями Microsoft/Minecraft и получите необходимое одобрение для своего приложения. Лаунчер не может выдать его автоматически.
6. В лаунчере откройте «Настройки → Microsoft OAuth», укажите Client ID и порт 53682, сохраните. Либо скопируйте `config.example.json`, впишите значения и импортируйте его кнопкой в настройках. Импорт изменяет форму; после него нажмите «Сохранить».
7. Перейдите в «Аккаунты → Войти через Microsoft». Лаунчер откроет браузер и будет ждать callback до 3 минут. Listener привязан к `127.0.0.1`, принимает только `/callback` и проверяет `state` через constant-time сравнение. Неожиданный state даёт HTTP 400 и не завершает вход.
8. После Microsoft token exchange выполняются Xbox Live RPS → XSTS → Minecraft Services, запрос entitlements и игрового профиля. Отсутствие прав или Java-профиля приводит к ошибке, а не к фиктивному входу.

При занятом порте выберите другой свободный порт в настройках **и измените регистрацию Redirect URI**. Путь `/callback` должен оставаться тем же. Callback по `https` не требуется для loopback native client; все внешние токенные запросы идут по HTTPS.

## Хранение и обновление

Refresh token записывается через `keyring.backends.Windows.WinVaultKeyring` в Windows Credential Manager. Ошибка системного хранилища прерывает сохранение аккаунта; plaintext fallback отсутствует. В SQLite сохраняются UUID, игровой ник и URL скина. Access token хранится в памяти, обновляется перед истечением срока; после перезапуска лаунчера новый Minecraft token получается через Microsoft refresh flow.

«Выйти» удаляет локальную запись и refresh token. Это не глобальный выход из Microsoft в системном браузере. Не публикуйте свой `settings.json`, SQLite или системное хранилище. Client ID сам по себе не является секретом; пароли, refresh/access tokens являются.

## Диагностика

- HTTP 400 при token exchange: проверьте тип public client, Redirect URI, соответствие Client ID и tenant, повторите вход. Старый authorization code использовать повторно нельзя.
- Xbox/XSTS HTTP 401/403: может отсутствовать Xbox-профиль, действовать детские/семейные ограничения, региональная политика либо запрет доступа приложения. Настройте аккаунт Xbox и разрешения приложения.
- Minecraft Services HTTP 401/403: проверьте допуск вашего приложения к API. Не подставляйте Client ID другого лаунчера.
- Пустые entitlements или профиль недоступен: требуется законный доступ к Java Edition и созданный игровой профиль. Демо/offline обхода нет.
- Windows vault недоступен: используйте обычную интерактивную сессию Windows того пользователя, которому принадлежит Credential Manager. Не запускайте лаунчер от другого администратора.

В этой сессии не предоставлены Client ID, одобрение API или аккаунт; реальный Microsoft вход не выполнялся.

Источники: [Microsoft: Authorization Code Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [Redirect URI restrictions](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url), [minecraft-launcher-lib Microsoft account](https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/microsoft_login.html). Требования доступа Minecraft API могут меняться независимо от исходного кода лаунчера.
