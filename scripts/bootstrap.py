"""Re-download the bundled optical material tables, optionally copying the SKY130 stack figure.

Not needed for normal use: data/ is already populated. Pass --skywater-pdk to copy
metal_stack.svg from a local checkout of https://github.com/google/skywater-pdk.
"""
from pathlib import Path
import argparse, urllib.request, hashlib, json, shutil
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--skywater-pdk',type=Path,help='local skywater-pdk checkout')
args=parser.parse_args()
(root/'data').mkdir(exist_ok=True)
sources={}
for mat,file in [('Al','Rakic'),('Si','Green-2008')]:
    url=f'https://raw.githubusercontent.com/polyanskiy/refractiveindex.info-database/master/database/data/main/{mat}/nk/{file}.yml'
    p=root/'data'/f'{mat}.yml'
    urllib.request.urlretrieve(url,p)
    sources[mat]={'url':url,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(root/'data'/'sources.json').write_text(json.dumps(sources,indent=2))
if args.skywater_pdk:
    shutil.copy(args.skywater_pdk/'docs/_static/metal_stack.svg',root/'data'/'sky130_stack.svg')
print('Downloaded material data.')
