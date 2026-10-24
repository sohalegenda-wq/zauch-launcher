"""Public-client PKCE OAuth. Only refresh tokens enter Windows Credential Manager."""
import hmac
import json
import re
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import keyring
import requests
from minecraft_launcher_lib.microsoft_account import get_secure_login_data
from .download_manager import Cancelled

SERVICE = 'ZauchLauncher.Microsoft'
TOKEN_URL = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/token'
SCOPE = 'XboxLive.signin offline_access'

class AuthError(RuntimeError):
    pass

class Auth:
    def __init__(self, settings, db, vault=None):
        self.settings = settings
        self.db = db
        if vault is not None:
            self.vault = vault
        else:
            import sys
            if sys.platform == 'win32':
                from keyring.backends.Windows import WinVaultKeyring
                self.vault = WinVaultKeyring()
            else:
                self.vault = keyring.get_keyring()
        self.memory = {}
        self._secrets = set()

    def redact(self, text):
        for secret in sorted(self._secrets, key=len, reverse=True):
            if secret:
                text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'(?i)(--accessToken\s+|Bearer\s+)[^\s]+', r'\1[REDACTED]', text)
        text = re.sub(r'(?i)("?(?:access_token|refresh_token|authorization)"?\s*[:=]\s*"?)[^"\s,}]+', r'\1[REDACTED]', text)
        return text

    def configured(self):
        value = self.settings['oauth_client_id'].strip()
        if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
            raise AuthError('Microsoft OAuth не настроен. Укажите Client ID в Настройках. Инструкция: docs/OAUTH.md')
        return value

    def _request(self, url, data=None, json_body=None, bearer=None, get=False):
        headers = {'Authorization': 'Bearer ' + bearer} if bearer else {}
        try:
            if get:
                r = requests.get(url, headers=headers, timeout=(15, 45))
            else:
                r = requests.post(url, data=data, json=json_body, headers=headers, timeout=(15, 45))
            with r:
                if not r.ok:
                    # Do not propagate raw OAuth responses, request bodies or tokens into logs.
                    raise AuthError(f'Сервис авторизации {urlparse(url).hostname}: HTTP {r.status_code}. Проверьте разрешения приложения, аккаунт Xbox и лицензию Java Edition.')
                return r.json()
        except requests.RequestException:
            raise AuthError('Сеть авторизации недоступна. Проверьте соединение и повторите вход.') from None

    def _finish(self, microsoft):
        refresh = microsoft.get('refresh_token')
        token = microsoft.get('access_token')
        if not token or not refresh:
            raise AuthError('Microsoft не вернул токены; проверьте offline_access')
        self._secrets.update((token, refresh))
        xbl = self._request('https://user.auth.xboxlive.com/user/authenticate', json_body={
            'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com', 'RpsTicket': 'd=' + token},
            'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT'})
        self._secrets.add(xbl['Token'])
        xsts = self._request('https://xsts.auth.xboxlive.com/xsts/authorize', json_body={
            'Properties': {'SandboxId': 'RETAIL', 'UserTokens': [xbl['Token']]},
            'RelyingParty': 'rp://api.minecraftservices.com/', 'TokenType': 'JWT'})
        self._secrets.add(xsts['Token'])
        uhs = xsts['DisplayClaims']['xui'][0]['uhs']
        mc = self._request('https://api.minecraftservices.com/authentication/login_with_xbox', json_body={
            'identityToken': f'XBL3.0 x={uhs};{xsts["Token"]}'})
        access = mc.get('access_token')
        if not access:
            raise AuthError('Приложение не получило разрешение Minecraft API')
        self._secrets.add(access)
        ownership = self._request('https://api.minecraftservices.com/entitlements/mcstore', bearer=access, get=True)
        if not ownership.get('items'):
            raise AuthError('Для этого аккаунта не подтверждён доступ к Minecraft Java Edition')
        profile = self._request('https://api.minecraftservices.com/minecraft/profile', bearer=access, get=True)
        if not profile.get('id') or not profile.get('name'):
            raise AuthError('Профиль Java Edition не найден')
        aid = profile['id']
        # This can fail if the OS vault is unavailable: never fall back to plaintext.
        self.vault.set_password(SERVICE, aid, refresh)
        skin = next((s['url'] for s in profile.get('skins', []) if s.get('state') == 'ACTIVE'), '')
        self.db.account(aid, profile['name'], skin)
        profile.update(access_token=access, expires_at=time.time() + int(mc.get('expires_in', 3600)) - 90)
        self.memory[aid] = profile
        return profile

    def login(self, cancel, emit):
        client = self.configured()
        port = self.settings['oauth_port']
        redirect = f'http://localhost:{port}/callback'
        url, state, verifier = get_secure_login_data(client, redirect)
        result = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != '/callback':
                    self.send_error(404)
                    return
                params = parse_qs(parsed.query)
                received = params.get('state', [''])[0]
                if not hmac.compare_digest(received, state):
                    self.send_error(400, 'Invalid OAuth state')
                    return
                if params.get('error'):
                    result['error'] = True
                elif params.get('code'):
                    result['code'] = params['code'][0]
                else:
                    self.send_error(400)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write('Можно вернуться в Zauch Launcher.'.encode('utf-8'))
        try:
            server = HTTPServer(('127.0.0.1', port), Handler)
        except OSError:
            raise AuthError(f'Порт {port} занят. Измените OAuth порт и Redirect URI в Entra.') from None
        server.timeout = .3
        with server:
            emit(dict(type='status', text='Ожидание входа в системном браузере (до 3 минут)'))
            if not webbrowser.open(url):
                raise AuthError('Не удалось открыть браузер. Настройте системный браузер и повторите вход.')
            deadline = time.monotonic() + 180
            while not result and time.monotonic() < deadline:
                if cancel.is_set():
                    raise Cancelled('Вход отменён')
                server.handle_request()
        if result.get('error'):
            raise AuthError('Вход отклонён пользователем или Microsoft')
        if 'code' not in result:
            raise AuthError('Время ожидания входа истекло')
        if cancel.is_set():
            raise Cancelled('Вход отменён')
        microsoft = self._request(TOKEN_URL, data={'client_id': client, 'grant_type': 'authorization_code',
            'code': result['code'], 'redirect_uri': redirect, 'code_verifier': verifier, 'scope': SCOPE})
        return self._finish(microsoft)

    def refresh(self, aid, force=False):
        if not force and aid in self.memory and self.memory[aid]['expires_at'] > time.time():
            return self.memory[aid]
        client = self.configured()
        refresh = self.vault.get_password(SERVICE, aid)
        if not refresh:
            raise AuthError('Войдите в Microsoft Account заново')
        self._secrets.add(refresh)
        microsoft = self._request(TOKEN_URL, data={'client_id': client, 'grant_type': 'refresh_token',
            'refresh_token': refresh, 'scope': SCOPE})
        # Some Microsoft responses retain the previous refresh token.
        microsoft.setdefault('refresh_token', refresh)
        return self._finish(microsoft)

    def logout(self, aid):
        try:
            self.vault.delete_password(SERVICE, aid)
        except keyring.errors.PasswordDeleteError:
            pass
        self.memory.pop(aid, None)
        self.db.remove_account(aid)
