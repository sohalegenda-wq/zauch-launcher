"""Independent game supervisor survives closing the launcher window."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from .profile_manager import Database
from .paths import data_dir
from .java_manager import FLAGS

def write_state(path, state):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state), 'utf-8')
    os.replace(temp, path)

def read_payload():
    if sys.stdin is not None:
        return sys.stdin.buffer.read()
    if sys.platform == 'win32':
        # pythonw/PyInstaller windowed may leave sys.stdin=None even with a pipe.
        # Read the explicitly inherited standard-input HANDLE, without a console.
        import ctypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        handle = kernel.GetStdHandle(-10 & 0xffffffff)
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise RuntimeError('Не передан защищённый канал запуска')
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        with os.fdopen(fd, 'rb') as stream:
            return stream.read()
    raise RuntimeError('Не передан канал запуска')

def monitor_main():
    payload = json.loads(read_payload())
    root = data_dir()
    sessions = root / 'sessions'
    sessions.mkdir(exist_ok=True)
    state_path = sessions / (str(int(payload['launch_id'])) + '.json')
    log_path = root / 'logs' / ('game-' + str(int(payload['launch_id'])) + '.log')
    log_path.parent.mkdir(exist_ok=True)
    db = Database(root)
    # Keep secrets exclusively in this process' memory; never serialize them.
    secrets = payload['secrets']
    def redact(line):
        import re
        for token in secrets:
            if token:
                line = line.replace(token, '[REDACTED]')
        return re.sub(r'(?i)(--accessToken\s+|Bearer\s+)[^\s]+', r'\1[REDACTED]', line)
    game = None
    state = dict(status='starting', log=str(log_path), launch_id=payload['launch_id'])
    code = -1
    try:
        game = subprocess.Popen(payload['command'], cwd=payload['cwd'], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
            creationflags=FLAGS, close_fds=True)
        import psutil
        state.update(status='running', pid=game.pid, process_created=psutil.Process(game.pid).create_time())
        write_state(state_path, state)
        with log_path.open('a', encoding='utf-8', buffering=1) as log:
            for line in game.stdout:
                log.write(redact(line))
        code = game.wait()
        state.update(status='exited', exit_code=code)
    except Exception as exc:
        state.update(status='failed', exit_code=-1, error=redact(f'{type(exc).__name__}: {exc}'))
        with log_path.open('a', encoding='utf-8') as log:
            log.write(state['error'] + '\n')
        if game and game.poll() is None:
            code = game.wait()
    finally:
        db.finish_launch(payload['launch_id'], code)
        write_state(state_path, state)

def start_supervised(profile, args, token, db):
    root = data_dir()
    sessions = root / 'sessions'
    sessions.mkdir(exist_ok=True)
    lid = db.start_launch(profile)
    entry = [sys.executable, '--game-monitor'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'), '--game-monitor']
    monitor = subprocess.Popen(entry, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=FLAGS | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0), close_fds=True,
        env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1'))
    payload = dict(launch_id=lid, command=args, cwd=profile['game_dir'], secrets=[token])
    try:
        monitor.stdin.write(json.dumps(payload).encode('utf-8'))
        monitor.stdin.close()
    except (OSError, BrokenPipeError):
        db.finish_launch(lid, -1)
        raise RuntimeError('Процесс сопровождения не принял параметры запуска') from None
    state_path = sessions / (str(lid) + '.json')
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if state_path.exists():
            state = json.loads(state_path.read_text('utf-8'))
            if state['status'] == 'failed':
                raise RuntimeError(state['error'])
            if state['status'] in ('running', 'exited'):
                return state
        if monitor.poll() is not None:
            db.finish_launch(lid, -1)
            raise RuntimeError('Не удалось запустить процесс сопровождения игры')
        time.sleep(.1)
    raise RuntimeError('Запуск игры не подтверждён за 25 секунд. Проверьте журнал и историю перед повтором.')
