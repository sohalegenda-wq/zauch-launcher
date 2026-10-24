"""Explicit live diagnostics. An HTTP failure is a failure, never a fixture success."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.version_manager import Versions
from core.download_manager import get_json

def main():
    result={}
    for name,url in [('mojang_manifest','https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'),
                     ('fabric_catalog','https://meta.fabricmc.net/v2/versions/loader')]:
        try:
            data=get_json(url)
            result[name]={'ok':True,'entries':len(data['versions'] if isinstance(data,dict) else data)}
        except Exception as exc:
            result[name]={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if all(r['ok'] for r in result.values()) else 1

if __name__=='__main__':
    raise SystemExit(main())
