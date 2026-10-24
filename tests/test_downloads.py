import hashlib
import threading
import pytest
import requests
from core import download_manager as dm

class Response:
    def __init__(self,content,status=200):
        self.content=content
        self.status_code=status
        self.headers={'Content-Length':str(len(content))}
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def raise_for_status(self):
        if self.status_code>=400: raise requests.HTTPError('test server error')
    def iter_content(self,size):
        for i in range(0,len(self.content),3): yield self.content[i:i+3]

class Session:
    def __init__(self,responses): self.responses=iter(responses);self.calls=0
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def get(self,*a,**kw):
        self.calls+=1
        return next(self.responses)

class NoWait:
    def is_set(self): return False
    def wait(self,t): return False

def transport(monkeypatch,responses):
    s=Session(responses)
    monkeypatch.setattr(dm,'session',lambda:s)
    return s

def test_hash_retry_and_atomic_replacement(tmp_path,monkeypatch):
    content=b'correct payload'
    expected=hashlib.sha1(content).hexdigest()
    s=transport(monkeypatch,[Response(b'corrupt'),Response(content)])
    events=[]
    d=dm.Downloader(tmp_path,NoWait(),events.append)
    target=tmp_path/'client.jar'
    d.download('https://piston-data.mojang.com/test',target,sha1=expected)
    assert s.calls==2
    assert target.read_bytes()==content
    assert not list(tmp_path.glob('*.part'))
    d.save_inventory('unit-test')
    dm.verify_inventory(tmp_path,'unit-test')
    target.write_bytes(b'broken')
    with pytest.raises(RuntimeError): dm.verify_inventory(tmp_path,'unit-test')

def test_http_failure_does_not_replace_file(tmp_path,monkeypatch):
    transport(monkeypatch,[Response(b'bad',503)]*3)
    target=tmp_path/'library.jar'
    target.write_bytes(b'previous')
    d=dm.Downloader(tmp_path,NoWait())
    with pytest.raises(RuntimeError):
        d.download('https://libraries.minecraft.net/test',target,sha1='0'*40)
    assert target.read_bytes()==b'previous'
    assert not list(tmp_path.glob('*.part'))

def test_cache_verified_without_network(tmp_path,monkeypatch):
    target=tmp_path/'asset'
    target.write_bytes(b'asset')
    s=transport(monkeypatch,[])
    d=dm.Downloader(tmp_path)
    assert d.download('https://resources.download.minecraft.net/test',target,sha1=hashlib.sha1(b'asset').hexdigest()) is False
    assert s.calls==0

def test_cancel_mid_stream_removes_partial(tmp_path,monkeypatch):
    stop=threading.Event()
    class Interrupted(Response):
        def iter_content(self,size):
            yield b'first'
            stop.set()
            yield b'second'
    transport(monkeypatch,[Interrupted(b'firstsecond')])
    d=dm.Downloader(tmp_path,stop)
    with pytest.raises(dm.Cancelled):
        d.download('https://piston-data.mojang.com/test',tmp_path/'client.jar')
    assert not (tmp_path/'client.jar').exists()
    assert not list(tmp_path.glob('*.part'))

def test_lzma_runtime_verifies_uncompressed_hash(tmp_path,monkeypatch):
    import lzma
    content=b'java executable test bytes'
    transport(monkeypatch,[Response(lzma.compress(content))])
    d=dm.Downloader(tmp_path)
    d.download('https://piston-data.mojang.com/runtime',tmp_path/'java',sha1=hashlib.sha1(content).hexdigest(),lzma_compressed=True)
    assert (tmp_path/'java').read_bytes()==content

@pytest.mark.parametrize('url',['http://piston-meta.mojang.com/a','https://evil.test/a','https://mojang.com.evil.test/a','https://user:secret@piston-meta.mojang.com/a'])
def test_untrusted_url_rejected(url):
    with pytest.raises(ValueError): dm.validate_url(url)

def test_destination_outside_root(tmp_path):
    d=dm.Downloader(tmp_path/'mc')
    with pytest.raises(ValueError): d.download('https://piston-data.mojang.com/test',tmp_path/'outside')

def test_repair_unhashed_library_uses_previous_inventory(tmp_path,monkeypatch):
    target=tmp_path/'fabric.jar'
    target.write_bytes(b'corrupted-after-install')
    correct=b'official-fabric-library'
    s=transport(monkeypatch,[Response(correct)])
    d=dm.Downloader(tmp_path)
    d.known_hashes['fabric.jar']=hashlib.sha1(correct).hexdigest()
    d.download('https://maven.fabricmc.net/test',target)
    assert s.calls==1
    assert target.read_bytes()==correct
