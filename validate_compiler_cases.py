"""Representative discretization checks on the most used emitted pixels."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json
from pathlib import Path
import numpy as np
import colour
from color2gds.layout import read_gds
from color2gds.compiler import forward

if __name__=='__main__':
    for case in [f'{stack}_{sample}' for sample in ['zundamon','metan'] for stack in ['sky130','soi_al']]:
        root=Path('runs')/case;m=json.loads((root/'manifest.json').read_text())
        geos,ids,_=read_gds(root/'image.gds',m)
        unique,counts=np.unique(ids[ids>=0],return_counts=True);selected=unique[np.argsort(-counts)][:2]
        selected_geo=[geos[int(i)] for i in selected]
        baseline=np.load(root/'appearance.npz')['cell_Lab'][selected]
        out=[]
        for label,settings in [('51_modes',{**m['settings'],'modes':51}),('half_nm',{**m['settings'],'step_nm':.5})]:
            _,_,colors,_,_=forward(m['stack'],selected_geo,settings,'.cache/color2gds',4)
            for i,c,b in zip(selected,colors,baseline):
                out.append({'cell':int(i),'check':label,'deltaE00':float(colour.delta_E(c['Lab'],b,method='CIE 2000'))})
        (root/'numerical_checks.json').write_text(json.dumps(out,indent=2));print(case,out,flush=True)
