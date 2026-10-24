"""Compile, adaptively refine, emit GDS, re-simulate its actual geometry."""
import base64
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import colour
from PIL import Image, ImageDraw
from .model import simulate, color, digest
from .layout import candidates, write_gds, read_gds

def forward(cfg,geos,settings,cache,workers):
    tasks=[(cfg,{'pitch':g['pitch'],'width':g['width']},settings,str(cache)) for g in geos]
    blank=simulate((cfg,{'pitch':.4,'width':0.,'blank':True},settings,str(cache)))
    if workers==1:raw=[simulate(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:raw=list(pool.map(simulate,tasks))
    wl=np.array(blank['wavelength_nm']);bg=np.array(blank['spectra'])[:,:,0].mean(axis=1)
    spectra=[];colors=[]
    for g,r in zip(geos,raw):
        weight=g['count']*g['pitch']*g['length']/settings['pixel_size_um']**2
        if not 0<weight<=1:raise ValueError('Invalid patterned area')
        spec=weight*np.array(r['spectra'])[:,:,0].mean(axis=1)+(1-weight)*bg
        spectra.append(spec);colors.append(color(spec,wl))
    return wl,np.array(spectra).reshape((-1,len(wl))),colors,bg,color(bg,wl)

def nearest(target,lab):
    flat=target.reshape(-1,3);result=[]
    for start in range(0,len(flat),2048):
        result.append(np.sum((flat[start:start+2048,None,:]-lab[None,:,:])**2,axis=2).argmin(axis=1))
    return np.concatenate(result).reshape(target.shape[:2])

def assign_cells(target, lab, mask):
    # The final palette row is the unpatterned substrate, reserved for transparent pixels.
    ids = nearest(target, lab[:-1])
    ids[~mask] = -1
    return ids

def objective(target,lab,ids,mask):return float(np.mean(np.linalg.norm(target[mask]-lab[ids[mask]],axis=1)))

def refine(geos,ids,target,lab,mask,manifest):
    grid=manifest['stack']['rules']['grid_um'];tile=manifest['pixel_size_um']
    unique,counts=np.unique(ids[mask],return_counts=True);added=[]
    for index in unique[np.argsort(-counts)][:4]:
        if index>=len(geos):continue
        src=geos[int(index)]
        for step in [-grid,grid]:
            g=dict(src);g['width']=round(g['width']+step,12)
            if g['width']<manifest['min_width_um']-1e-9 or g['pitch']-g['width']<manifest['min_space_um']-1e-9:continue
            if g['width']*g['length']<manifest['stack']['rules']['min_area_um2']:continue
            g['x0']=round(round(((tile-g['count']*g['pitch'])/2+(g['pitch']-g['width'])/2)/grid)*grid,12)
            if not any(g==x for x in geos+added):added.append(g)
    return geos+added

def render_gds(gds,manifest,out,cache,workers=4):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    geos,ids,top=read_gds(gds,manifest)
    wl,spectra,colors,bg,bgcolor=forward(manifest['stack'],geos,manifest['settings'],cache,workers)
    table=np.array([c['rgb'] for c in colors]+[bgcolor['rgb']])
    pixels=ids.copy();pixels[pixels<0]=len(colors)
    rgb=table[pixels]
    # Preview colors are computed from read-back GDS geometry, not source-image recoloring.
    image=Image.fromarray(np.uint8(np.clip(rgb,0,1)*255+.5))
    image.save(out/'appearance.png');image.resize((image.width*6,image.height*6),Image.Resampling.NEAREST).save(out/'appearance_large.png')
    Image.fromarray(np.uint8(ids>=0)*255).convert('1').save(out/'image.bmp')
    np.savez_compressed(out/'appearance.npz',wavelength_nm=wl,cell_reflectance=np.vstack([spectra,bg]),
                        pixel_cell_indices=pixels,cell_srgb=table,cell_Lab=np.array([c['Lab'] for c in colors]+[bgcolor['Lab']]))
    layout=Image.new('RGB',(image.width,image.height),'#e8e4e2');draw=ImageDraw.Draw(layout)
    for y,x in zip(*np.nonzero(ids>=0)):draw.point((int(x),int(y)),fill='#3276b2')
    layout.resize((image.width*6,image.height*6),Image.Resampling.NEAREST).save(out/'layout_pixels.png')
    # Layout crop from flattened GDS coordinates, centered on a nonempty pixel.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    yy,xx=np.nonzero(ids>=0);tile=manifest['pixel_size_um']
    if len(xx):
        k=len(xx)//2;x0=max(0,int(xx[k])-1)*tile;y0=max(0,image.height-1-int(yy[k])-1)*tile
        verts=[]
        for p in top.get_polygons():
            b=np.array(p.bounding_box())
            if b[1,0]>=x0 and b[0,0]<=x0+3*tile and b[1,1]>=y0 and b[0,1]<=y0+3*tile:verts.append(p.points)
        fig,ax=plt.subplots(figsize=(7,6),layout='constrained');ax.add_collection(PolyCollection(verts,facecolor='#3276b2',edgecolor='none'))
        ax.set(xlim=(x0,x0+3*tile),ylim=(y0,y0+3*tile),aspect='equal',xlabel='x (um)',ylabel='y (um)',title='Actual GDS geometry: 3 x 3 pixel crop')
        fig.savefig(out/'layout_detail.png',dpi=160);plt.close(fig)
    checks={'gds_sha256':hashlib.sha256(Path(gds).read_bytes()).hexdigest(),'unique_drawn_cells':len(geos),
            'references':int((ids>=0).sum()),'verified':['rectangles','layer/datatype','width','spacing','minimum area','grid','boundary keepout','pixel placement'],
            'global_density_and_foundry_signoff':'not covered by geometry checks','geometries':geos}
    (out/'readback.json').write_text(json.dumps(checks,indent=2))
    return rgb,np.array([c['Lab'] for c in colors]+[bgcolor['Lab']])[pixels],checks

def compile_image(args,cfg):
    start=time.time();out=Path(args.out)
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory is not empty; choose a new run directory')
    out.mkdir(parents=True,exist_ok=True)
    source=Image.open(args.image)
    if source.format not in ['PNG','JPEG','PPM','BMP']:raise ValueError('Supported inputs: jpeg/jpg/png/pbm/pgm/bmp')
    source=source.convert('RGBA');rows=max(1,round(args.columns*source.height/source.width))
    rgba=np.array(source.resize((args.columns,rows),Image.Resampling.LANCZOS))/255.
    mask=rgba[:,:,3]>=.5
    if not mask.any():raise ValueError('Image has no opaque pixels')
    target=colour.XYZ_to_Lab(colour.sRGB_to_XYZ(rgba[:,:,:3]))
    source.save(out/'input.png')
    geos=candidates(cfg,args.min_width_um,args.min_space_um,args.pixel_size_um)
    settings={'step_nm':args.step_nm,'modes':args.modes,'theta':args.angle_deg,'pixel_size_um':args.pixel_size_um}
    manifest={'schema_version':1,'stack':cfg,'settings':settings,'grid':[args.columns,rows],'pixel_size_um':args.pixel_size_um,
              'min_width_um':max(args.min_width_um,cfg['rules']['min_width_um']),
              'min_space_um':max(args.min_space_um,cfg['rules']['min_space_um']),
              'gds_layer':args.gds_layer,'gds_datatype':cfg['gds']['datatype'],'mapping':args.mapping,
              'source_sha256':hashlib.sha256(Path(args.image).read_bytes()).hexdigest(),
              'opaque_pixels_allow_blank':False}
    history=[];adjusted=None
    for round_no in range(args.refine_rounds+1):
        # Compile the calibration library, then derive the optical LUT from its actual polygons.
        calibration=out/f'calibration_{round_no}.gds';cal_manifest={**manifest,'grid':[len(geos),1]}
        write_gds(calibration,geos,np.arange(len(geos))[None,:],args.pixel_size_um,args.gds_layer,cfg['gds']['datatype'])
        geos,_,_=read_gds(calibration,cal_manifest)
        wl,spec,colors,bg,bgcolor=forward(cfg,geos,settings,args.cache,args.workers)
        lab=np.array([c['Lab'] for c in colors]+[bgcolor['Lab']])
        if adjusted is None:
            adjusted=target.copy()
            if args.mapping=='contrast':
                lo,hi=np.percentile(target[:,:,0][mask],[1,99]);pmin,pmax=lab[:,0].min(),lab[:,0].max()
                adjusted[:,:,0]=pmin+np.clip((target[:,:,0]-lo)/max(hi-lo,1e-9),0,1)*(pmax-pmin)
                scale=min(1.,np.max(np.linalg.norm(lab[:,1:],axis=1))/max(np.percentile(np.linalg.norm(target[:,:,1:],axis=-1)[mask],99),1e-9))
                adjusted[:,:,1:]*=scale
                manifest['tone_map']={'input_L':[float(lo),float(hi)],'output_L':[float(pmin),float(pmax)],'chroma_scale':float(scale)}
        ids=assign_cells(adjusted,lab,mask)
        score=objective(adjusted,lab,ids,mask)
        history.append({'round':round_no,'candidate_count':len(geos),'mean_deltaE76_mapping_target':score})
        print(f'round {round_no}: {len(geos)} candidates, mean DeltaE76 {score:.3f}',flush=True)
        if round_no==args.refine_rounds:break
        new=refine(geos,ids,adjusted,lab,mask,manifest)
        if len(new)==len(geos):break
        geos=new
    predicted=lab[ids].copy()
    write_gds(out/'image.gds',geos,ids,args.pixel_size_um,args.gds_layer,cfg['gds']['datatype'])
    manifest['optimization_history']=history
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rgb,readlab,checks=render_gds(out/'image.gds',manifest,out,args.cache,args.workers)
    # The empty pixel and the blank palette entry must yield the same substrate spectrum.
    max_error=float(np.max(abs(readlab[mask]-predicted[mask])))
    if max_error>1e-7:raise RuntimeError('Emitted GDS appearance differs from optimization model')
    error=colour.delta_E(target[mask],readlab[mask],method='CIE 2000')
    final_score=float(np.mean(np.linalg.norm(adjusted[mask]-readlab[mask],axis=1)))
    if abs(final_score-history[-1]['mean_deltaE76_mapping_target'])>1e-7:raise RuntimeError('Closed-loop objective mismatch')
    summary={'stack':cfg['name'],'canvas_um':[round(args.columns*args.pixel_size_um,9),round(rows*args.pixel_size_um,9)],
             'pixel_grid':[args.columns,rows],'foreground_pixels':int(mask.sum()),'elapsed_seconds':time.time()-start,
             'mean_deltaE00_source':float(error.mean()),'median_deltaE00_source':float(np.median(error)),
             'closed_loop_max_Lab_difference':max_error,'optimization_history':history,'readback':checks,
             'assumptions':cfg.get('assumptions',[]),'limitations':['Infinite 1D periodic local solver; finite-pixel edges and neighboring-cell coupling omitted',
             'Active region and guard region combined as an incoherent area average','No foundry signoff; density/fill/antenna and actual optical constants need process integration']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    np.savez_compressed(out/'palette.npz',wavelength_nm=wl,reflectance=spec,blank=bg,Lab=lab)
    white=Image.new('RGBA',source.size,'white');white.alpha_composite(source);white.convert('RGB').save(out/'input_white.png')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(13,4.6),layout='constrained')
    for ax,img,title in zip(axs,[np.array(white),rgb,Image.open(out/'layout_pixels.png')],['Input','Predicted from emitted GDS','Drawn-pixel map']):
        ax.imshow(img);ax.set_title(title);ax.axis('off')
    fig.suptitle(cfg['name']+' | '+args.mapping+' mapping | model prediction, not a measurement')
    fig.savefig(out/'comparison.png',dpi=160);plt.close(fig)
    from .palette import palette_png
    (out/'palette.png').write_bytes(palette_png(out))
    report(out,summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['readback','assumptions','limitations']},indent=2),flush=True)
    return summary

def report(out,summary):
    import html
    def embed(name):return 'data:image/png;base64,'+base64.b64encode((out/name).read_bytes()).decode()
    s=summary
    content='<!doctype html><html lang="en"><meta charset="utf-8"><title>Color2GDS report</title><style>body{font:16px system-ui;max-width:1150px;margin:40px auto;padding:20px;background:#f1f4f9;color:#233447}img{max-width:100%}section{background:white;padding:24px;border-radius:14px;margin:20px 0}p,li{line-height:1.8}pre{white-space:pre-wrap}</style>'
    content+='<h1>Color2GDS — '+html.escape(s['stack'])+'</h1><p>Image → GDS → GDS read-back → optical simulation → color difference</p>'
    content+='<section><p>Size '+str(s['canvas_um'])+' µm / pixels '+str(s['pixel_grid'])+'</p><p>Mean ΔE00 vs. input: '+f"{s['mean_deltaE00_source']:.2f}"+'. Displayed colors depend on the assumed stack and do not guarantee reproduction of the input colors.</p>'
    content+='<p>Model difference after GDS read-back (max Lab component difference): '+str(s['closed_loop_max_Lab_difference'])+'</p></section>'
    for name in ['comparison.png','appearance_large.png','layout_detail.png']:
        if (out/name).exists():content+='<section><img alt="'+name+'" src="'+embed(name)+'"></section>'
    content+='<section><h2>Search and evaluation</h2><pre>'+html.escape(json.dumps(s['optimization_history'],indent=2))+'</pre></section>'
    content+='<section><h2>Model assumptions and limitations</h2><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in s['assumptions']+s['limitations'])+'</ul></section></html>'
    (out/'report.html').write_text(content,encoding='utf-8')
