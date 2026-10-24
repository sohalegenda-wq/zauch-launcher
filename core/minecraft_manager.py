"""Minecraft installation runs in a disposable process; Qt owns its lifecycle."""
import json
import multiprocessing
import os
import queue
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from minecraft_launcher_lib import command, install, runtime
from .download_manager import Downloader, Cancelled, get_json, verify_inventory
from .java_manager import resolve_java, load_metadata, FLAGS
from .paths import inside, identifier
from .version_manager import Versions

def fabric_version(base, loader):
    return f'fabric-loader-{identifier(loader)}-{identifier(base)}'

def effective_metadata(base, fabric_data=None):
    if fabric_data is None:
        return base
    merged = dict(base)
    merged.update({k: v for k, v in fabric_data.items() if k not in ('libraries', 'arguments')})
    overrides = {':'.join(x['name'].split(':')[:2]) for x in fabric_data.get('libraries', [])}
    merged['libraries'] = fabric_data.get('libraries', []) + [x for x in base['libraries'] if ':'.join(x['name'].split(':')[:2]) not in overrides]
    merged['arguments'] = {k: base.get('arguments', {}).get(k, []) + fabric_data.get('arguments', {}).get(k, []) for k in ('game', 'jvm')}
    return merged

def install_child(payload, events, cancel):
    """Patch only download boundaries in this isolated process, never in GUI threads."""
    try:
        _install(payload, events.put, cancel)
        events.put(dict(type='result', version=payload['version']))
    except Cancelled:
        events.put(dict(type='cancelled', text='Установка отменена; файлы можно восстановить повторной установкой.'))
    except Exception as exc:
        events.put(dict(type='error', text=f'{type(exc).__name__}: {exc}'))

def _install(p, emit, cancel):
    root = Path(p['root']).resolve()
    base_id = identifier(p['base'])
    version = identifier(p['version'])
    dl = Downloader(root, cancel, emit)
    previous = root / '.zauch' / (version + '.json')
    if previous.is_file():
        try:
            dl.known_hashes = {name: info['sha1'] for name, info in json.loads(previous.read_text('utf-8')).items()}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    state = {'maximum': 1}
    def status(text):
        dl.check()
        emit(dict(type='status', text=str(text)))
    def maximum(value):
        state['maximum'] = max(1, value + 1)
        emit(dict(type='progress', value=0, maximum=state['maximum']))
    def progress(value):
        dl.check()
        emit(dict(type='progress', value=min(value, state['maximum']), maximum=state['maximum']))
    cb = {'setStatus': status, 'setMax': maximum, 'setProgress': progress}
    install.download_file = dl.download
    runtime.download_file = dl.download
    from types import SimpleNamespace
    from .download_manager import validate_url, session
    def metadata_get(url, **kwargs):
        validate_url(url)
        response = session().get(url, timeout=(15, 45), allow_redirects=False, **kwargs)
        response.raise_for_status()
        if response.status_code != 200:
            response.close()
            raise RuntimeError('Неожиданный HTTP статус runtime')
        return response
    runtime.requests = SimpleNamespace(get=metadata_get, session=session)
    def safe_extract(filename, extract_path, extract_data):
        target = inside(root, str(Path(extract_path).resolve().relative_to(root)))
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(filename) as z:
            for entry in z.infolist():
                dl.check()
                if any(entry.filename.startswith(e) for e in extract_data.get('exclude', [])):
                    continue
                destination = inside(target, entry.filename)
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Символьная ссылка в архиве native')
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(entry) as source, destination.open('wb') as out:
                        shutil.copyfileobj(source, out)
                    dl.record(destination)
    install.extract_natives_file = safe_extract
    status('Получение официальных метаданных Mojang')
    base = Versions.metadata(base_id, dl)
    effective = base
    if p['kind'] == 'Fabric':
        loader = identifier(p['loader'])
        available = Versions.fabric_loaders(base_id)
        if loader not in [v['loader']['version'] for v in available]:
            raise ValueError('Fabric Loader несовместим с выбранной версией')
        mod = get_json(f'https://meta.fabricmc.net/v2/versions/loader/{base_id}/{loader}/profile/json')
        if mod.get('id') != version or mod.get('inheritsFrom') != base_id:
            raise ValueError('Неожиданные метаданные Fabric')
        target = inside(root, f'versions/{version}/{version}.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(mod, indent=2), 'utf-8')
        os.replace(temp, target)
        dl.record(target)
        effective = effective_metadata(base, mod)
    dl.check()
    install.install_libraries(version, effective['libraries'], str(root), cb, max_workers=p['workers'])
    install.install_assets(base, str(root), cb, max_workers=p['workers'])
    if base.get('logging', {}).get('client'):
        log = base['logging']['client']['file']
        dl.download(log['url'], inside(root, 'assets/log_configs/' + log['id']), sha1=log['sha1'])
    client = base['downloads']['client']
    dl.download(client['url'], inside(root, f'versions/{base_id}/{base_id}.jar'), sha1=client['sha1'])
    if version != base_id:
        destination = inside(root, f'versions/{version}/{version}.jar')
        temp = destination.with_suffix('.tmp')
        shutil.copyfile(root / 'versions' / base_id / (base_id + '.jar'), temp)
        os.replace(temp, destination)
        dl.record(destination, client['sha1'])
    # Legacy virtual/resources layouts are still referenced by older clients.
    if 'assetIndex' in base:
        index = json.loads((root / 'assets' / 'indexes' / (base['assets'] + '.json')).read_text('utf-8'))
        virtual_roots = []
        if index.get('virtual'):
            virtual_roots.append(inside(root, 'assets/virtual/' + base['assets']))
        if index.get('map_to_resources'):
            virtual_roots.append(inside(root, 'resources'))
        for target_root in virtual_roots:
            for name, info in index['objects'].items():
                dl.check()
                target = inside(target_root, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = inside(root, f'assets/objects/{info["hash"][:2]}/{info["hash"]}')
                shutil.copyfile(source, target)
                dl.record(target, info['hash'])
    status('Проверка и подготовка Java Runtime')
    # Always repair the managed runtime, including damaged supporting DLLs.
    if not p.get('java'):
        from .java_manager import requirements
        runtime.install_jvm_runtime(requirements(base)['component'], str(root), callback=cb, max_workers=p['workers'])
    resolve_java(root, base, p.get('java', ''), install=False)
    # Check actual launch classpath: the upstream library tolerates some optional URL failures.
    for entry in command.get_libraries(effective, str(root)).split(os.pathsep):
        if entry and not Path(entry).is_file():
            raise RuntimeError('Отсутствует библиотека: ' + Path(entry).name)
    dl.check()
    dl.save_inventory(version)
    verify_inventory(root, version, cancel, emit)
    status('Установка и проверка завершены')

def install_in_process(payload, cancel, emit):
    context = multiprocessing.get_context('spawn')
    events = context.Queue()
    stop = context.Event()
    child = context.Process(target=install_child, args=(payload, events, stop))
    child.start()
    result = None
    cancelled_at = None
    try:
        while child.is_alive() or not result:
            if cancel.is_set():
                stop.set()
                cancelled_at = cancelled_at or time.monotonic()
                if time.monotonic() - cancelled_at > 3 and child.is_alive():
                    child.terminate()
            try:
                event = events.get(timeout=.1)
                if event['type'] in ('result', 'error', 'cancelled'):
                    result = event
                    break
                emit(event)
            except queue.Empty:
                if not child.is_alive():
                    # Drain any final buffered result once the process exits.
                    try:
                        event = events.get(timeout=.3)
                        if event['type'] in ('result', 'error', 'cancelled'):
                            result = event
                            break
                        emit(event)
                        continue
                    except queue.Empty:
                        break
        child.join(timeout=5)
        if cancel.is_set() or (result and result['type'] == 'cancelled'):
            raise Cancelled('Установка отменена. Повторите установку для восстановления.')
        if not result or result['type'] != 'result':
            raise RuntimeError(result['text'] if result else f'Установщик завершился с кодом {child.exitcode}')
        return payload['version']
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=3)
        events.close()

def launch_options(profile, settings, account, java):
    import shlex
    from .settings_manager import Settings
    options = dict(settings, **json.loads(profile['options']))
    Settings.validate(options)
    return dict(username=account['name'], uuid=account['id'], token=account['access_token'],
                executablePath=java, gameDirectory=profile['game_dir'],
                jvmArguments=[f'-Xms{options["min_ram"]}M', f'-Xmx{options["max_ram"]}M'] + shlex.split(options['jvm_args']),
                launcherName='Zauch Launcher', launcherVersion='0.1.0', customResolution=True,
                resolutionWidth=str(options['width']), resolutionHeight=str(options['height']),
                enableLoggingConfig=True)

def build_command(profile, settings, account, java):
    import shlex
    args = command.get_minecraft_command(profile['version'], profile['root'], launch_options(profile, settings, account, java))
    effective = dict(settings, **json.loads(profile['options']))
    if effective['fullscreen']:
        args.append('--fullscreen')
    args.extend(shlex.split(effective['game_args']))
    return args
