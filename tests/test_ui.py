import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from ui.main_window import MainWindow
from core.settings_manager import Settings

def test_all_pages_and_real_profile_settings_flow(app,monkeypatch):
    messages=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:messages.append(a[-1]))
    w=MainWindow(startup_network=False)
    w.show()
    for i in range(10):
        w.navigate(i)
        app.processEvents()
        assert w.stack.currentIndex()==i
    pid=w.db.create_profile('UI Profile','test','test','Vanilla',Path(w.settings['minecraft_dir']))
    w.refresh(pid)
    assert w.selected_profile()['id']==pid
    assert w.profile_table.rowCount()==1
    assert 'UI Profile' in w.home_details.text()
    w.controls['theme'].setCurrentIndex(w.controls['theme'].findData('light'))
    w.controls['animations'].setChecked(False)
    w.save_settings()
    assert Settings()['theme']=='light'
    w.home_action()
    assert w.stack.currentIndex()==9
    # Stop the real installer thread before teardown; no fixture claims a successful install.
    w.cancel_job()
    while w.worker:
        app.processEvents()
        if w.worker:
            w.worker.wait(50)
    w.close()

def test_version_filters_use_received_data_only(app):
    w=MainWindow(startup_network=False)
    w.catalog=[{'id':'unit-release','type':'release','releaseTime':'2024-01-01'},
               {'id':'unit-snapshot','type':'snapshot','releaseTime':'2024-01-02'}]
    w.filter_versions()
    assert w.version_list.count()==1
    assert w.version_list.item(0).data(Qt.ItemDataRole.UserRole)['id']=='unit-release'
    w.version_type.setCurrentIndex(w.version_type.findData('snapshot'))
    assert w.version_list.count()==1
    assert w.version_list.item(0).data(Qt.ItemDataRole.UserRole)['id']=='unit-snapshot'
    w.version_search.setText('missing')
    assert w.version_list.count()==0
    w.close()

def test_restore_running_session_checks_process_identity(app):
    import os
    import psutil
    from core.paths import data_dir
    w=MainWindow(startup_network=False)
    pid=w.db.create_profile('Session fixture','test','test','Vanilla',data_dir()/'mc')
    lid=w.db.start_launch(w.db.profile(pid))
    directory=data_dir()/'sessions'
    directory.mkdir(exist_ok=True)
    state={'status':'running','pid':os.getpid(),'process_created':psutil.Process().create_time(),
           'log':str(data_dir()/'unit.log'),'launch_id':lid}
    (directory/(str(lid)+'.json')).write_text(json.dumps(state))
    w.restore_session()
    assert w.game['launch_id']==lid
    w.game=None
    # A reused PID cannot attach to an unrelated process.
    state['process_created']-=1000
    (directory/(str(lid)+'.json')).write_text(json.dumps(state))
    w.restore_session()
    assert w.game is None
    assert w.db.history()[0]['exit_code']==-1
    w.close()
