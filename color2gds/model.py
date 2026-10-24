"""Validated single-mask lamellar stacks and the RCWA forward model."""
import hashlib
import json
from pathlib import Path
import numpy as np
import yaml
import grcwa
from grcwa.rcwa import MakeKPMatrix, SolveLayerEigensystem
from optics import eps as literature_eps, color, ROOT

BUILTINS = {'air', 'Al', 'Si', 'TiN', 'SiO2', 'Si3N4'}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()

def load_stack(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(cfg, dict) or cfg.get('schema_version') != 1 or cfg.get('units') != 'um':
        raise ValueError('Expected schema_version: 1 and units: um')
    allowed={'schema_version','name','units','gds','rules','materials','layers','assumptions','sources'}
    if set(cfg)-allowed: raise ValueError('Unknown stack keys: '+str(set(cfg)-allowed))
    cfg.setdefault('materials', {})
    for name, mat in cfg['materials'].items():
        if name in BUILTINS: raise ValueError('Cannot override built-in material '+name)
        if set(mat)!={'n','k'} or not np.isfinite([mat['n'],mat['k']]).all() or mat['n']<=0 or mat['k']<0:
            raise ValueError('Custom materials need finite n>0, k>=0')
    layers=cfg.get('layers', [])
    if len(layers)<3: raise ValueError('Need incident half-space, finite layers, substrate')
    for i,layer in enumerate(layers):
        if set(layer)-{'material','thickness_um','patterned','background'}: raise ValueError('Unsupported layer fields')
        for mat in [layer.get('material'), layer.get('background', 'air')]:
            if mat not in BUILTINS and mat not in cfg['materials']: raise ValueError('Unknown material '+str(mat))
        d=layer.get('thickness_um', -1)
        if not np.isfinite(d) or (d!=0 if i in [0,len(layers)-1] else d<=0):
            raise ValueError('Only first/last half-spaces have zero thickness')
        if layer.get('patterned',False) not in [True,False]: raise ValueError('patterned must be boolean')
        if layer.get('patterned') and (i in [0,len(layers)-1] or 'background' not in layer):
            raise ValueError('Patterned finite layers require a background material')
    if not any(x.get('patterned') for x in layers): raise ValueError('At least one patterned layer is required')
    if layers[0]['material']!='air': raise ValueError('This version supports incidence from air only')
    rule=cfg.get('rules',{})
    for key in ['grid_um','min_width_um','min_space_um','min_area_um2']:
        if not np.isfinite(rule.get(key,0)) or rule.get(key,0)<=0:raise ValueError('Missing positive rule '+key)
    gds=cfg.get('gds',{})
    for key in ['layer','datatype']:
        if not isinstance(gds.get(key),int) or not 0<=gds[key]<=65535:raise ValueError('Invalid GDS '+key)
    return cfg

def epsilon(cfg,name,w):
    if name=='air':return 1.
    if name=='Si3N4':
        l=w/1000
        return 1+2.8939*l*l/(l*l-.13967**2)
    if name=='SiO2':return literature_eps('oxide',w)
    if name in cfg['materials']:
        m=cfg['materials'][name];return (m['n']+1j*m['k'])**2
    return literature_eps(name,w)

def one_wavelength(cfg,w,pitch,width,modes=31,theta=0.,blank=False):
    modes=1 if blank else modes
    if modes<1 or modes%2!=1:raise ValueError('modes must be a positive odd number')
    if not 0<=width<=pitch or pitch<=0:raise ValueError('Invalid grating geometry')
    o=grcwa.obj(modes+1,[pitch,0],[0,pitch/(4*modes)],(1+1e-10j)/(w/1000),np.deg2rad(theta),0,verbose=0)
    for layer in cfg['layers']:
        if layer.get('patterned') and not blank:o.Add_LayerGrid(layer['thickness_um'],1,1)
        else:
            mat=layer['background'] if blank and layer.get('patterned') else layer['material']
            o.Add_LayerUniform(layer['thickness_um'],epsilon(cfg,mat,w))
    o.Init_Setup()
    if o.nG!=modes or np.any(o.G[:,1]):raise RuntimeError('Unexpected reciprocal lattice')
    dm=o.G[:,0,None]-o.G[None,:,0];fill=width/pitch
    shape=fill*np.sinc(dm*fill)*np.exp(-1j*np.pi*dm);eye=np.eye(modes)
    for i,layer in enumerate(cfg['layers']):
        if blank or not layer.get('patterned'):continue
        a=epsilon(cfg,layer['material'],w);b=epsilon(cfg,layer['background'],w)
        conv=b*eye+(a-b)*shape;inverse=eye/b+(1/a-1/b)*shape
        epinv=np.linalg.inv(conv);ex=np.linalg.inv(inverse);z=np.zeros_like(conv)
        ep2=np.block([[conv,z],[z,ex]]) # grcwa coordinates: (-Ey, Ex)
        j=o.id_list[i][2];o.Patterned_epinv_list[j]=epinv;o.Patterned_ep2_list[j]=ep2
        kp=MakeKPMatrix(o.omega,1,epinv,o.kx,o.ky)
        o.kp_list[i]=kp;o.q_list[i],o.phi_list[i]=SolveLayerEigensystem(o.omega,o.kx,o.ky,kp,ep2)
    vals=[]
    for pol in ['s','p']:
        o.MakeExcitationPlanewave(p_amp=int(pol=='p'),p_phase=0,s_amp=int(pol=='s'),s_phase=0)
        r,t=o.RT_Solve(normalize=1,byorder=1);zero=np.flatnonzero(np.all(o.G==0,axis=1))[0]
        vals.append([float(np.real(r[zero])),float(np.real(np.sum(r))),float(np.real(np.sum(t)))])
    a=np.array(vals)
    if not np.isfinite(a).all() or a.min()<-1e-6 or np.max(a[:,1]+a[:,2])>1.00001:
        raise RuntimeError('Non-passive or invalid RCWA solution')
    return a

def simulate(task):
    cfg,geo,settings,cache=task
    # Cache invalidates on model/source/material changes, not only user settings.
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    material_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('*.yml')}
    key=digest([cfg,geo,settings,source_hash,material_hashes])
    path=Path(cache)/(key+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return json.loads(path.read_text())
    wl=np.arange(380.,780.0001,settings['step_nm'])
    spectra=np.array([one_wavelength(cfg,w,geo['pitch'],geo['width'],settings['modes'],settings['theta'],geo.get('blank',False)) for w in wl])
    result={'key':key,'wavelength_nm':wl.tolist(),'spectra':spectra.tolist(),**geo}
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result));temp.replace(path)
    return result
