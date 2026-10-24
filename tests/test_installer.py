import json
from pathlib import Path
import pytest
from core import minecraft_manager as mm
from core.download_manager import sha1_file, verify_inventory

def test_install_pipeline_inventory_and_fabric_profile(tmp_path,monkeypatch):
    """Unit fixture for orchestration, not a successful real Minecraft installation."""
    base={'id':'unit-base','libraries':[], 'assets':'unit-assets',
          'downloads':{'client':{'url':'https://piston-data.mojang.com/unit','sha1':'unused-in-unit-transport'}},
          'javaVersion':{'majorVersion':21,'component':'java-runtime-delta'},
          'mainClass':'net.minecraft.client.main.Main','arguments':{'jvm':[],'game':[]}}
    version='fabric-loader-0.16.14-unit-base'
    mod={'id':version,'inheritsFrom':'unit-base','mainClass':'net.fabricmc.loader.impl.launch.knot.KnotClient','libraries':[], 'arguments':{'jvm':[],'game':[]}}
    class Stop:
        def is_set(self):return False
    def metadata(version,dl):
        path=dl.root/'versions'/version/(version+'.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(base))
        dl.record(path)
        return base
    monkeypatch.setattr(mm.Versions,'metadata',metadata)
    monkeypatch.setattr(mm.Versions,'fabric_loaders',lambda v:[{'loader':{'version':'0.16.14'}}])
    monkeypatch.setattr(mm,'get_json',lambda url:mod)
    monkeypatch.setattr(mm.install,'install_libraries',lambda *a,**kw:None)
    monkeypatch.setattr(mm.install,'install_assets',lambda *a,**kw:None)
    monkeypatch.setattr(mm.runtime,'install_jvm_runtime',lambda *a,**kw:None)
    monkeypatch.setattr(mm,'resolve_java',lambda *a,**kw:{'path':'unit-java','major':21})
    def download(self,url,path,**kw):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        Path(path).write_bytes(b'unit-client-data')
        self.record(path)
    monkeypatch.setattr(mm.Downloader,'download',download)
    # Preserve patched module boundaries after the isolated-process implementation replaces them.
    monkeypatch.setattr(mm.install,'download_file',mm.install.download_file)
    monkeypatch.setattr(mm.install,'extract_natives_file',mm.install.extract_natives_file)
    monkeypatch.setattr(mm.runtime,'download_file',mm.runtime.download_file)
    monkeypatch.setattr(mm.runtime,'requests',mm.runtime.requests)
    base['downloads']['client']['sha1']=__import__('hashlib').sha1(b'unit-client-data').hexdigest()
    mm._install({'root':str(tmp_path),'base':'unit-base','version':version,'kind':'Fabric','loader':'0.16.14','workers':1},lambda e:None,Stop())
    verify_inventory(tmp_path,version)
    assert (tmp_path/'versions'/version/(version+'.jar')).read_bytes()==b'unit-client-data'
    assert json.loads((tmp_path/'versions'/version/(version+'.json')).read_text())['inheritsFrom']=='unit-base'
