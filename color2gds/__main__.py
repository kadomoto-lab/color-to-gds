import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import argparse
import json
import math
from pathlib import Path
from .model import load_stack
from .compiler import compile_image,render_gds

def main():
    parser=argparse.ArgumentParser(description='Image and layer stack -> verified GDS and predicted appearance')
    subs=parser.add_subparsers(dest='command',required=True)
    c=subs.add_parser('compile');c.add_argument('image');c.add_argument('--stack',required=True)
    c.add_argument('--min-width-um',type=float,required=True);c.add_argument('--min-space-um',type=float,required=True)
    c.add_argument('--gds-layer',type=int,required=True);c.add_argument('--pixel-size-um',type=float,default=7.815)
    c.add_argument('--columns',type=int,default=128);c.add_argument('--modes',type=int,default=31)
    c.add_argument('--step-nm',type=float,default=1.);c.add_argument('--angle-deg',type=float,default=0.)
    c.add_argument('--mapping',choices=['color','contrast'],default='color')
    c.add_argument('--refine-rounds',type=int,default=1);c.add_argument('--workers',type=int,default=4)
    c.add_argument('--cache',default='.cache/color2gds');c.add_argument('--out',required=True)
    s=subs.add_parser('simulate');s.add_argument('gds');s.add_argument('--manifest',required=True)
    s.add_argument('--out',required=True);s.add_argument('--cache',default='.cache/color2gds');s.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    try:
        if args.command=='simulate':
            manifest=json.loads(Path(args.manifest).read_text());render_gds(args.gds,manifest,args.out,args.cache,args.workers);return
        cfg=load_stack(args.stack)
        for key in ['min_width_um','min_space_um','pixel_size_um','step_nm']:
            if not math.isfinite(getattr(args,key)) or getattr(args,key)<=0:raise ValueError(key+' must be finite and positive')
        if args.min_width_um<cfg['rules']['min_width_um'] or args.min_space_um<cfg['rules']['min_space_um']:
            raise ValueError('Requested width/space violates stack minimum rules')
        if args.columns<1 or args.workers<1 or args.refine_rounds<0 or args.modes<1 or args.modes%2!=1:raise ValueError('Invalid count or mode setting')
        if not 0<=args.gds_layer<=65535:raise ValueError('Invalid GDS layer')
        if cfg['gds'].get('fixed_layer') and args.gds_layer!=cfg['gds']['layer']:
            raise ValueError('GDS layer conflicts with physical stack; choose/edit the matching stack')
        grid=cfg['rules']['grid_um']
        if abs(args.pixel_size_um/grid-round(args.pixel_size_um/grid))>1e-7:raise ValueError('Pixel size must lie on process grid')
        if not math.isfinite(args.angle_deg) or not 0<=args.angle_deg<80:raise ValueError('angle must be in [0,80) degrees')
        if args.step_nm>5 or abs(400/args.step_nm-round(400/args.step_nm))>1e-7:raise ValueError('Step must divide 400 nm and be <=5 nm')
        compile_image(args,cfg)
    except (ValueError,FileNotFoundError) as error:parser.exit(2,'error: '+str(error)+'\n')

if __name__=='__main__':main()
