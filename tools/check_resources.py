from pathlib import Path
root = Path(__file__).resolve().parents[1]
required = ['assets/icon.ico','assets/logo.svg','assets/backgrounds/emerald.svg',
    'assets/backgrounds/amethyst.svg','assets/icons/folder-open.svg','assets/icons/LUCIDE-LICENSE',
    'ui/styles.qss','README.md','docs/OAUTH.md','THIRD_PARTY.md','licenses/LGPL-3.0.txt']
for name in required:
    path = root/name
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit('Missing resource: '+name)
print('Resources OK')
