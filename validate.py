"""Additional wavelength-resolution and large-period checks."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json
import numpy as np
import colour
from optics import ROOT,WL,spectrum,color
p=json.loads((ROOT/'results/palette.json').read_text())
out=[]
for family in ['m1_grating','m2_grating','m2_m1_mirror']:
    subset=[c for c in p['cells'] if c['family']==family]
    chosen=max(subset,key=lambda c:np.linalg.norm(c['Lab'][1:]))
    fine=np.arange(380.,781.,1.)
    r=spectrum(chosen['pitch'],chosen['width'],family,wavelengths=fine,modes=51)[:,:,0].mean(axis=1)
    shape=colour.SpectralShape(380,780,1)
    cmf=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(shape).values
    d65=colour.SDS_ILLUMINANTS['D65'].copy().align(shape).values
    xyz=np.trapezoid(r[:,None]*d65[:,None]*cmf,fine,axis=0)/np.trapezoid(d65*cmf[:,1],fine)
    lab=colour.XYZ_to_Lab(xyz,colour.CCS_ILLUMINANTS['CIE 1931 2 Degree Standard Observer']['D65'])
    coarse=color(r[::5])
    out.append(dict(id=chosen['id'],check='1 nm versus 5 nm integration, 51 modes',deltaE00=float(colour.delta_E(lab,coarse['Lab'],method='CIE 2000')),fine_XYZ=xyz.tolist(),fine_R0=r.tolist()))
    wide=next(c for c in subset if c['pitch']==.8 and c['width']==.14)
    hi=spectrum(.8,.14,family,modes=71)[:,:,0].mean(axis=1)
    out.append(dict(id=wide['id'],check='large pitch 31 vs 71 modes',deltaE00=float(colour.delta_E(color(hi)['Lab'],wide['Lab'],method='CIE 2000')),max_R0_difference=float(max(abs(hi-wide['R0'])))))
    (ROOT/'results/extra_validation.json').write_text(json.dumps(out,indent=2))
    print(family,out[-2]['deltaE00'],out[-1]['deltaE00'],flush=True)

