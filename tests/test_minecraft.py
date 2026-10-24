import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from core.minecraft_manager import build_command,effective_metadata,fabric_version
from core.settings_manager import Settings
from core.java_manager import inspect_java,requirements

@pytest.fixture
def installation(tmp_path):
    version='test-version'
    root=tmp_path/'mc'
    target=root/'versions'/version
    target.mkdir(parents=True)
    (target/(version+'.jar')).write_bytes(b'not-a-real-client-unit-test-only')
    metadata={'id':version,'type':'release','mainClass':'net.minecraft.client.main.Main',
      'libraries':[], 'assets':'test-assets', 'releaseTime':'2024-01-01T00:00:00+00:00',
      'arguments':{'jvm':['-cp','${classpath}','-Djava.library.path=${natives_directory}'],
      'game':['--username','${auth_player_name}','--uuid','${auth_uuid}','--accessToken','${auth_access_token}','--gameDir','${game_directory}']}}
    (target/(version+'.json')).write_text(json.dumps(metadata),'utf-8')
    p={'id':'test','name':'Unit profile','version':version,'base':version,'root':str(root),
       'game_dir':str(tmp_path/'separate-game'),'kind':'Vanilla','options':'{}'}
    return p,metadata

def test_real_library_command_generation(installation,tmp_path):
    p,_=installation
    s=Settings(tmp_path/'settings')
    s.save({'fullscreen':True,'game_args':'--server example.org','jvm_args':'-Dexample=true'})
    args=build_command(p,s.values,{'id':'0'*32,'name':'UnitUser','access_token':'unit-token'},'C:/Java/bin/java.exe')
    assert args[0]=='C:/Java/bin/java.exe'
    assert args[args.index('--username')+1]=='UnitUser'
    assert args[args.index('--gameDir')+1]==p['game_dir']
    assert args[args.index('--accessToken')+1]=='unit-token'
    assert '-Xmx'+str(s['max_ram'])+'M' in args
    assert '--fullscreen' in args
    assert args[-2:]==['--server','example.org']
    assert 'net.minecraft.client.main.Main' in args

def test_fabric_inheritance_real_command(installation,tmp_path):
    p,base=installation
    base['javaVersion']={'majorVersion':21,'component':'java-runtime-delta'}
    modid=fabric_version(p['base'],'0.16.14')
    mod={'id':modid,'inheritsFrom':p['base'],'mainClass':'net.fabricmc.loader.impl.launch.knot.KnotClient',
         'libraries':[],'arguments':{'game':[],'jvm':['-Dfabric=true']}}
    merged=effective_metadata(base,mod)
    assert merged['javaVersion']['majorVersion']==21
    target=Path(p['root'])/'versions'/modid
    target.mkdir()
    (target/(modid+'.json')).write_text(json.dumps(mod))
    (target/(modid+'.jar')).write_bytes(b'unit-client')
    p['version']=modid
    args=build_command(p,Settings(tmp_path/'settings').values,{'id':'0'*32,'name':'Unit','access_token':'unit-token'},'/java')
    assert mod['mainClass'] in args
    assert '-Dfabric=true' in args

@pytest.mark.parametrize('text,major', [('java.version = 1.8.0_442\nos.arch = amd64',8),('java.version = 21.0.7\nos.arch = x86_64',21)])
def test_java_detection(monkeypatch,text,major):
    import core.java_manager as jm
    monkeypatch.setattr(jm.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='',stderr=text,returncode=0))
    assert inspect_java('java')['major']==major

def test_java_rejects_32bit(monkeypatch):
    import core.java_manager as jm
    monkeypatch.setattr(jm.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='',stderr='java.version = 21.0.7\nos.arch = x86',returncode=0))
    with pytest.raises(RuntimeError,match='x64'): inspect_java('java')

def test_runtime_requirement_uses_metadata():
    assert requirements({'javaVersion':{'majorVersion':25,'component':'future-runtime'}})['majorVersion']==25
    assert requirements({})['majorVersion']==8
