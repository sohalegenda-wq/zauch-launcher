import json
import sys
import time
from pathlib import Path
from core.paths import data_dir
from core.profile_manager import Database
from core.process_manager import start_supervised

def test_independent_monitor_records_exit_and_redacts():
    root=data_dir()
    db=Database(root)
    pid=db.create_profile('Unit process','test','test','Vanilla',root/'minecraft')
    profile=db.profile(pid)
    # Execute a harmless Python child, never represent it as a real Minecraft launch.
    code="import time; print('token=unit-super-secret',flush=True); time.sleep(.2); raise SystemExit(3)"
    state=start_supervised(profile,[sys.executable,'-c',code],'unit-super-secret',db)
    path=root/'sessions'/(str(state['launch_id'])+'.json')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        current=json.loads(path.read_text())
        if current['status']=='exited': break
        time.sleep(.1)
    assert current['status']=='exited'
    assert current['exit_code']==3
    assert db.history()[0]['exit_code']==3
    log=Path(current['log']).read_text()
    assert '[REDACTED]' in log
    assert 'unit-super-secret' not in log
