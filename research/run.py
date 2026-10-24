"""Reproducible screening sweep and representative convergence/sensitivity study."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[key]='1'
import argparse,json,time,platform
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from color2gds.optics import WL,spectrum,color,ROOT
FAMILIES=['m1_grating','m2_grating','m2_m1_mirror']
def candidates():
    out=[]
    for f in FAMILIES:
        for pitch in [.28,.32,.36,.40,.44,.48,.56,.64,.72,.80]:
            widths=sorted(set(round(round((.14+(pitch-.28)*x)/.005)*.005,3) for x in [0,.25,.5,.75,1]))
            for w in widths:
                out.append(dict(id=f'{f}_p{round(pitch*1000)}_w{round(w*1000)}',family=f,pitch=pitch,width=w))
    return out
def job(args):
    cell,modes=args
    a=spectrum(cell['pitch'],cell['width'],cell['family'],modes=modes)
    r=a[:,:,0].mean(axis=1)
    c={**cell,**color(r),'R0_s':a[:,0,0].tolist(),'R0_p':a[:,1,0].tolist(),
       'R0':r.tolist(),'Rtotal':a[:,:,1].mean(axis=1).tolist(),'T':a[:,:,2].mean(axis=1).tolist()}
    # Substrate absorption is NOT included in A; T is flux entering absorbing Si.
    c['min_absorption_above_substrate']=float((1-a[:,:,1]-a[:,:,2]).min())
    return c
def main():
    p=argparse.ArgumentParser(); p.add_argument('--modes',type=int,default=31); p.add_argument('--workers',type=int,default=4)
    p.add_argument('--limit',type=int); p.add_argument('--study',action='store_true'); args=p.parse_args()
    dest=ROOT/'research/results'; dest.mkdir(exist_ok=True); t=time.time()
    if not args.study:
        cells=candidates()[:args.limit]; out=[]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for i,c in enumerate(pool.map(job,[(c,args.modes) for c in cells])):
                out.append(c)
                if (i+1)%10==0 or i==0: print(f'{i+1}/{len(cells)}  {time.time()-t:.1f}s',flush=True)
                (dest/'palette.json').write_text(json.dumps(dict(wavelength_nm=WL.tolist(),modes=args.modes,cells=out),indent=2))
        print(f'Completed {len(out)} cells in {time.time()-t:.1f}s',flush=True)
    else:
        palette=json.loads((dest/'palette.json').read_text())
        chosen=[]
        for family in FAMILIES:
            subset=[c for c in palette['cells'] if c['family']==family]
            chosen.append(max(subset,key=lambda c:np.linalg.norm(c['Lab'][1:])))
        studies=[]
        for c in chosen:
            base=dict(pitch=c['pitch'],width=c['width'],family=c['family'])
            variants=[(f'modes_{n}',dict(modes=n)) for n in [31,51,71]]
            variants += [(f'angle_{a}',dict(modes=51,theta=a)) for a in [5,15,30]]
            variants += [(f'cap_{v}',dict(modes=51,cap=v)) for v in [4.255,4.455]]
            variants += [('polyimide',dict(modes=51,pi=4.7846)),('metal_340',dict(modes=51,metal=.34)),('metal_380',dict(modes=51,metal=.38))]
            variants += [('gap_250',dict(modes=51,gap=.25)),('gap_290',dict(modes=51,gap=.29))]
            for name,kw in variants:
                a=spectrum(**base,**kw); r=a[:,:,0].mean(axis=1)
                studies.append(dict(id=c['id'],variant=name,settings=kw,**color(r),R0=r.tolist(),R0_s=a[:,0,0].tolist(),R0_p=a[:,1,0].tolist()))
                (dest/'studies.json').write_text(json.dumps(studies,indent=2))
                print(c['id'],name,f'{time.time()-t:.1f}s',flush=True)
if __name__=='__main__': main()

