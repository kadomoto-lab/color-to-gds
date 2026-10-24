"""Geometry generation and strict readback for the supported GDS grammar."""
import math
from pathlib import Path
import numpy as np
import gdstk

def snap_up(value,grid):return round(math.ceil(value/grid-1e-9)*grid,12)

def candidates(cfg,min_width,min_space,pixel_size):
    rule=cfg['rules'];grid=rule['grid_um']
    width=snap_up(max(min_width,rule['min_width_um']),grid)
    space=snap_up(max(min_space,rule['min_space_um']),grid)
    margin=snap_up(max(.28,space),grid)
    base=width+space
    pitches=sorted(set(snap_up(base*x,grid) for x in [1,1.15,1.3,1.5,1.75,2,2.4,2.85]))
    out=[]
    for p in pitches:
        for w in sorted(set([width,snap_up(p/2,grid),round(p-space,12)])):
            n=int((pixel_size-2*margin+1e-9)/p)
            if w<width-1e-9 or p-w<space-1e-9 or n<8:continue
            length=round(pixel_size-2*margin,12)
            if w*length<rule['min_area_um2']:continue
            # Rectangle edges are snapped; all stripe widths remain exact grid multiples.
            left=round(((pixel_size-n*p)/2+(p-w)/2)/grid)*grid
            out.append({'pitch':round(p,12),'width':round(w,12),'count':n,'length':length,
                        'x0':round(left,12),'y0':margin})
    if not out:raise ValueError('No legal cell fits: enlarge pixel size (at least 8 periods)')
    return out

def write_gds(path,geometries,ids,pixel_size,layer,datatype):
    lib=gdstk.Library(unit=1e-6,precision=1e-9);top=lib.new_cell('COLOR_IMAGE');cells=[]
    for i,g in enumerate(geometries):
        cell=lib.new_cell(f'PIXEL_{i:03d}')
        for j in range(g['count']):
            x=round(g['x0']+j*g['pitch'],12)
            cell.add(gdstk.rectangle((x,g['y0']),(round(x+g['width'],12),round(g['y0']+g['length'],12)),layer=layer,datatype=datatype))
        cells.append(cell)
    rows,cols=ids.shape
    for y,x in zip(*np.nonzero(ids>=0)):
        top.add(gdstk.Reference(cells[int(ids[y,x])],(round(x*pixel_size,12),round((rows-1-y)*pixel_size,12))))
    final=gdstk.Library(unit=1e-6,precision=1e-9);final.add(top,*top.dependencies(True));final.write_gds(path)

def read_gds(path,manifest):
    lib=gdstk.read_gds(path)
    if not np.isclose(lib.unit,1e-6,rtol=0,atol=1e-15):raise ValueError('GDS unit must be 1 um')
    tops=lib.top_level()
    if len(tops)!=1 or tops[0].polygons or tops[0].paths or tops[0].labels:raise ValueError('Expected one reference-only image top cell')
    cfg=manifest['stack'];grid=cfg['rules']['grid_um'];tile=manifest['pixel_size_um']
    cols,rows=manifest['grid'];ids=np.full((rows,cols),-1,dtype=int);geos=[];names={}
    layer=manifest['gds_layer'];datatype=manifest['gds_datatype']
    for ref in tops[0].references:
        if ref.rotation not in [None,0] or ref.x_reflection or ref.magnification not in [None,1] or ref.repetition.size>0:
            raise ValueError('Transforms or reference arrays are unsupported')
        cell=ref.cell
        if cell.name not in names:
            if cell.references or cell.paths or cell.labels or len(cell.polygons)<8:raise ValueError('Expected >=8 parallel rectangles per pixel')
            bounds=[]
            for poly in cell.polygons:
                pts=poly.points;b=np.array(poly.bounding_box())
                if poly.layer!=layer or poly.datatype!=datatype:raise ValueError('GDS layer does not match physical stack mapping')
                if len(pts)!=4 or set(map(tuple,np.round(pts,9)))!={(round(x,9),round(y,9)) for x in b[:,0] for y in b[:,1]}:
                    raise ValueError('Non-rectangular polygon is unsupported')
                if np.max(abs(pts/grid-np.round(pts/grid)))>1e-5:raise ValueError('Off-grid polygon')
                if poly.area()<cfg['rules']['min_area_um2']-1e-9:raise ValueError('Minimum area violation')
                bounds.append(b)
            bounds=np.array(sorted(bounds,key=lambda b:b[0,0]))
            widths=bounds[:,1,0]-bounds[:,0,0];pitch=np.diff(bounds[:,0,0])
            if np.ptp(widths)>1e-7 or np.ptp(pitch)>1e-7 or np.ptp(bounds[:,0,1])>1e-7 or np.ptp(bounds[:,1,1])>1e-7:
                raise ValueError('Pixel must be a uniform 1D line grating')
            p,w=round(float(pitch[0]),12),round(float(widths[0]),12)
            if w<manifest['min_width_um']-1e-7 or p-w<manifest['min_space_um']-1e-7:raise ValueError('Width/spacing violation')
            # This boundary margin guarantees minimum spacing between neighboring pixel cells.
            margin=manifest['min_space_um']/2
            if bounds.min()<margin-1e-7 or bounds.max()>tile-margin+1e-7:raise ValueError('Pixel boundary keepout violated')
            geo={'pitch':p,'width':w,'count':len(bounds),'length':round(float(bounds[0,1,1]-bounds[0,0,1]),12),
                 'x0':round(float(bounds[0,0,0]),12),'y0':round(float(bounds[0,0,1]),12)}
            names[cell.name]=len(geos);geos.append(geo)
        coords=np.asarray(ref.origin)/tile
        if not np.allclose(coords,np.round(coords),rtol=0,atol=1e-7):raise ValueError('Reference outside pixel lattice')
        x,iy=np.round(coords).astype(int);y=rows-1-iy
        if x<0 or x>=cols or y<0 or y>=rows or ids[y,x]>=0:raise ValueError('Duplicate or out-of-bounds pixel reference')
        ids[y,x]=names[cell.name]
    return geos,ids,tops[0]
