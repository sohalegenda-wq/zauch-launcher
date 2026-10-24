import base64
import hashlib
import threading
import urllib.parse
import pytest
from minecraft_launcher_lib.microsoft_account import get_secure_login_data
from core.auth_manager import Auth,AuthError,SERVICE
from core.profile_manager import Database
from core.settings_manager import Settings

class Vault:
    def __init__(self): self.data={}
    def set_password(self,s,k,v): self.data[(s,k)]=v
    def get_password(self,s,k): return self.data.get((s,k))
    def delete_password(self,s,k): self.data.pop((s,k),None)

def make_auth(tmp_path):
    s=Settings(tmp_path/'settings')
    return Auth(s,Database(tmp_path/'db'),Vault())

def test_pkce_challenge_and_state():
    url,state,verifier=get_secure_login_data('test-client','http://localhost:53682/callback')
    q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    expected=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    assert q['code_challenge']==[expected]
    assert q['code_challenge_method']==['S256']
    assert q['state']==[state]
    assert len(state)>=16

def test_unconfigured_oauth_fails_honestly(tmp_path):
    auth=make_auth(tmp_path)
    with pytest.raises(AuthError,match='не настроен'): auth.configured()

def test_no_entitlement_no_saved_account(tmp_path,monkeypatch):
    auth=make_auth(tmp_path)
    def api(url,**kw):
        if 'user.auth' in url: return {'Token':'xbl-secret'}
        if 'xsts' in url: return {'Token':'xsts-secret','DisplayClaims':{'xui':[{'uhs':'hash'}]}}
        if 'login_with_xbox' in url: return {'access_token':'mc-secret'}
        if 'entitlements' in url: return {'items':[]}
        raise AssertionError(url)
    monkeypatch.setattr(auth,'_request',api)
    with pytest.raises(AuthError,match='не подтверждён'): auth._finish({'access_token':'ms-secret','refresh_token':'refresh-secret'})
    assert auth.db.accounts()==[]
    assert auth.vault.data=={}

def test_complete_exchange_stores_only_refresh_in_vault(tmp_path,monkeypatch):
    auth=make_auth(tmp_path)
    def api(url,**kw):
        if 'user.auth' in url: return {'Token':'xbl-secret'}
        if 'xsts' in url: return {'Token':'xsts-secret','DisplayClaims':{'xui':[{'uhs':'hash'}]}}
        if 'login_with_xbox' in url: return {'access_token':'mc-secret','expires_in':3600}
        if 'entitlements' in url: return {'items':[{'name':'game_minecraft'}]}
        if 'minecraft/profile' in url: return {'id':'a'*32,'name':'UnitUser','skins':[]}
        raise AssertionError(url)
    monkeypatch.setattr(auth,'_request',api)
    result=auth._finish({'access_token':'ms-secret','refresh_token':'refresh-secret'})
    assert result['name']=='UnitUser'
    assert list(auth.vault.data.values())==['refresh-secret']
    assert 'secret' not in str(auth.db.accounts())
    text=auth.redact('ms-secret xbl-secret xsts-secret mc-secret refresh-secret')
    assert 'secret' not in text
    auth.logout('a'*32)
    assert not auth.db.accounts() and not auth.vault.data

def test_browser_callback_rejects_wrong_state(tmp_path,monkeypatch):
    import socket
    import urllib.request
    import urllib.error
    import core.auth_manager as am
    auth=make_auth(tmp_path)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    auth.settings.save({'oauth_client_id':'11111111-2222-3333-4444-555555555555','oauth_port':port})
    observed=[]
    threads=[]
    def browser(url):
        q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        def send():
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for state in ('incorrect',q['state'][0]):
                target=f'http://127.0.0.1:{port}/callback?'+urllib.parse.urlencode({'code':'unit-code','state':state})
                try:
                    with opener.open(target,timeout=5) as response: observed.append(response.status)
                except urllib.error.HTTPError as exc: observed.append(exc.code)
        t=threading.Thread(target=send)
        threads.append(t);t.start()
        return True
    monkeypatch.setattr(am.webbrowser,'open',browser)
    captured={}
    def exchange(url,**kw):
        captured.update(kw['data'])
        return {'unit':'response'}
    monkeypatch.setattr(auth,'_request',exchange)
    monkeypatch.setattr(auth,'_finish',lambda result:result)
    assert auth.login(threading.Event(),lambda e:None)=={'unit':'response'}
    for t in threads:t.join(timeout=5)
    assert observed==[400,200]
    assert captured['code']=='unit-code'
    assert len(captured['code_verifier'])>=43
    assert 'client_secret' not in captured
