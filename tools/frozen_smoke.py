"""Run a built launcher, native UI and its independent packaged process mode."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.profile_manager import Database

def main():
    exe=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='zauch-frozen-') as folder:
        root=Path(folder)
        env=dict(os.environ,ZAUCH_DATA_DIR=str(root),QT_QPA_PLATFORM='offscreen',PYINSTALLER_RESET_ENVIRONMENT='1')
        report=root/'smoke.json'
        completed=subprocess.run([str(exe),'--self-test',str(report)],env=env,check=False,timeout=120)
        if completed.returncode:
            error=report.with_suffix('.error.txt')
            detail=error.read_text('utf-8') if error.exists() else 'no error report'
            raise RuntimeError('Packaged self-test failed: '+detail)
        result=json.loads(report.read_text('utf-8'))
        assert result['frozen'] and result['pages']==10 and result['resources'] and result['installer_subprocess']
        db=Database(root)
        pid=db.create_profile('Packaged unit child','test','test','Vanilla',root/'mc')
        profile=db.profile(pid)
        lid=db.start_launch(profile)
        payload=dict(launch_id=lid,command=[sys.executable,'-c',"print('unit-token-secret',flush=True); raise SystemExit(7)"],
                     cwd=profile['game_dir'],secrets=['unit-token-secret'])
        process=subprocess.Popen([str(exe),'--game-monitor'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        stdout,stderr=process.communicate(json.dumps(payload).encode(),timeout=120)
        assert process.returncode==0,(stdout.decode(errors='replace'),stderr.decode(errors='replace'))
        state=json.loads((root/'sessions'/(str(lid)+'.json')).read_text('utf-8'))
        assert state['exit_code']==7 and db.history()[0]['exit_code']==7
        log=Path(state['log']).read_text('utf-8')
        assert '[REDACTED]' in log and 'unit-token-secret' not in log
        result['independent_monitor']=True
        print(json.dumps(result,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
