import json
from pathlib import Path
import pytest
from core.settings_manager import Settings,safe_ram
from core.profile_manager import Database
from core.paths import inside,identifier
from core.worlds_manager import backup_world,worlds

def test_settings_round_trip_and_rejected_unsafe_memory(tmp_path):
    s=Settings(tmp_path)
    s.save({'max_ram':min(2048,safe_ram()),'theme':'light','oauth_client_id':'example'})
    assert Settings(tmp_path)['theme']=='light'
    with pytest.raises(ValueError): s.save({'max_ram':safe_ram()+256})
    assert Settings(tmp_path)['max_ram']==min(2048,safe_ram())

@pytest.mark.parametrize('args',['--accessToken secret','--uuid=bad','--gameDir /tmp','--demo'])
def test_no_account_override(args,tmp_path):
    s=Settings(tmp_path)
    with pytest.raises(ValueError): s.save({'game_args':args})

def test_profiles_persist_and_deletion_keeps_worlds(tmp_path):
    db=Database(tmp_path)
    pid=db.create_profile('Survival','1.21','1.21','Vanilla',tmp_path/'minecraft')
    p=db.profile(pid)
    save=Path(p['game_dir'])/'saves'/'my-world'
    save.mkdir(parents=True)
    (save/'level.dat').write_bytes(b'unit-test-world')
    db.update_profile(pid,'Creative',p['game_dir'],{'max_ram':1024})
    assert Database(tmp_path).profile(pid)['name']=='Creative'
    db.delete_profile(pid)
    assert (save/'level.dat').read_bytes()==b'unit-test-world'
    assert db.profiles()==[]

def test_backup_world_archive(tmp_path):
    import zipfile
    world=tmp_path/'saves'/'World'
    world.mkdir(parents=True)
    (world/'level.dat').write_bytes(b'world-data')
    (world/'region').mkdir()
    (world/'region'/'r.0.0.mca').write_bytes(b'region')
    archive=backup_world(tmp_path,'World')
    with zipfile.ZipFile(archive) as z:
        assert z.read('World/level.dat')==b'world-data'
        assert z.read('World/region/r.0.0.mca')==b'region'

@pytest.mark.parametrize('name',['../escape','/etc/passwd','folder/../../escape'])
def test_path_traversal_rejected(tmp_path,name):
    with pytest.raises(ValueError): inside(tmp_path,name)

@pytest.mark.parametrize('name',['..','a/b','a\\b','C:evil'])
def test_identifiers_reject_paths(name):
    with pytest.raises(ValueError): identifier(name)

def test_profile_cannot_put_worlds_inside_version_directory(tmp_path):
    db=Database(tmp_path/'data')
    root=tmp_path/'minecraft'
    with pytest.raises(ValueError):
        db.create_profile('Unsafe','test','test','Vanilla',root,root/'versions'/'test')
