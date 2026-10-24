"""Fetch pinned, unmodified KLayout WASM assets; no Python kwasm import needed."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / '.cache' / 'web-vendor'
VERSION = '0.2.26'
SHA256 = 'c07af2bbf27335777ad604041c4c78752bf07c21c77a685a26c0de098dc47e4a'

def prepare():
    target = VENDOR / 'viewer.html'
    if target.exists():
        return target
    wheel = ROOT / '.tools' / f'kwasm-{VERSION}-py3-none-any.whl'
    if wheel.exists():
        data = wheel.read_bytes()
    else:
        with urllib.request.urlopen(f'https://pypi.org/pypi/kwasm/{VERSION}/json', timeout=30) as r:
            info = json.load(r)
        url = next(x['url'] for x in info['urls'] if x['filename'].endswith('.whl'))
        with urllib.request.urlopen(url, timeout=90) as r:
            data = r.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError('kwasm wheel checksum mismatch')
    VENDOR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        target.write_bytes(z.read(f'kwasm/kwasm-{VERSION}-bundled.html'))
        (VENDOR / 'LICENSE.txt').write_bytes(z.read(f'kwasm-{VERSION}.dist-info/licenses/LICENSE'))
    return target

if __name__ == '__main__':
    print(prepare())
