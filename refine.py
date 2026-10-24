"""Refine the entire palette to 1 nm without overwriting 5 nm screening data."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json,time
from concurrent.futures import ProcessPoolExecutor
import numpy as np,colour
from optics import ROOT,spectrum
FINE=np.arange(380.,781.,1.)
shape=colour.SpectralShape(380,780,1)
CMF=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(shape).values
D65=colour.SDS_ILLUMINANTS['D65'].copy().align(shape).values
WHITE=colour.CCS_ILLUMINANTS['CIE 1931 2 Degree Standard Observer']['D65']
def job(c):
    a=spectrum(c['pitch'],c['width'],c['family'],wavelengths=FINE,modes=31)
    r=a[:,:,0].mean(axis=1)
    xyz=np.trapezoid(r[:,None]*D65[:,None]*CMF,FINE,axis=0)/np.trapezoid(D65*CMF[:,1],FINE)
    lab=colour.XYZ_to_Lab(xyz,WHITE);rgb=colour.XYZ_to_sRGB(xyz)
    return dict(**{k:c[k] for k in ['id','family','pitch','width']},XYZ=xyz.tolist(),Lab=lab.tolist(),rgb=np.clip(rgb,0,1).tolist(),
        xy=colour.XYZ_to_xy(xyz).tolist(),out_of_srgb=bool(np.any((rgb<0)|(rgb>1))),
        R0_s=a[:,0,0].tolist(),R0_p=a[:,1,0].tolist(),R0=r.tolist(),Rtotal=a[:,:,1].mean(axis=1).tolist(),
        T=a[:,:,2].mean(axis=1).tolist(),min_absorption_above_substrate=float((1-a[:,:,1]-a[:,:,2]).min()),
        deltaE00_vs_5nm=float(colour.delta_E(c['Lab'],lab,method='CIE 2000')))
if __name__=='__main__':
    cells=json.loads((ROOT/'results/palette.json').read_text())['cells'];out=[];t=time.time()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,c in enumerate(pool.map(job,cells)):
            out.append(c)
            if i%10==0:print(f'{i+1}/{len(cells)} {time.time()-t:.1f}s',flush=True)
    (ROOT/'results/palette_refined.json').write_text(json.dumps(dict(wavelength_nm=FINE.tolist(),modes=31,cells=out),indent=2))
    print('done',len(out),'max dE',max(c['deltaE00_vs_5nm'] for c in out),flush=True)

