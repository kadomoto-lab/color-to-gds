import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json
from concurrent.futures import ProcessPoolExecutor
import numpy as np,colour
from optics import ROOT,spectrum,color
def job(c):
    w=np.arange(380.,780.01,.5)
    a=spectrum(c['pitch'],c['width'],c['family'],wavelengths=w,modes=31)[:,:,0].mean(axis=1)
    col=color(a,w)
    return dict(id=c['id'],deltaE00_5nm_to_1nm=c['deltaE00_vs_5nm'],deltaE00_1nm_to_half_nm=float(colour.delta_E(c['Lab'],col['Lab'],method='CIE 2000')),fine_Lab=col['Lab'])
if __name__=='__main__':
    p=json.loads((ROOT/'results/palette_refined.json').read_text())
    chosen=sorted(p['cells'],key=lambda c:c['deltaE00_vs_5nm'],reverse=True)[:6]
    with ProcessPoolExecutor(max_workers=4) as pool:out=list(pool.map(job,chosen))
    (ROOT/'results/half_nm_validation.json').write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))

