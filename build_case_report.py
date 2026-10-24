"""Present the bundled compiler runs and export a small offline comparison."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json,base64,html,hashlib
from pathlib import Path
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).parent;RUNS=ROOT/'runs'
SAMPLES={'zundamon':'Zundamon','metan':'Shikoku Metan'}
STACKS={'sky130':'SKY130 Met1 — assumed optical stack','soi_al':'SOI + Al — 100 / 220 / 2000 nm'}
CASES=[f'{stack}_{sample}' for sample in SAMPLES for stack in STACKS]
fig,axs=plt.subplots(len(SAMPLES),3,figsize=(12,7.5*len(SAMPLES)),layout='constrained')
for row,sample in zip(axs,SAMPLES):
    paths=[RUNS/f'sky130_{sample}'/'input_white.png']+[RUNS/f'{stack}_{sample}'/'appearance_large.png' for stack in STACKS]
    for ax,path,title in zip(row,paths,[f'{SAMPLES[sample]} — input on white']+list(STACKS.values())):
        ax.imshow(Image.open(path));ax.set_title(title,fontsize=11);ax.axis('off')
s0=json.loads((RUNS/CASES[0]/'summary.json').read_text())
fig.suptitle('Predicted from the generated GDS | transparent areas show modeled substrate\n'
             f"{s0['canvas_um'][0]:.2f} um wide | {s0['pixel_grid'][0]} pixel columns | D65, normal incidence, unpolarized",fontsize=13)
fig.savefig(RUNS/'case_comparison.png',dpi=110);plt.close(fig)
def embed(p):return 'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()
def label(name):
    stack=next(s for s in STACKS if name.startswith(s+'_'));sample=name[len(stack)+1:]
    return f"{SAMPLES[sample]} · {'SKY130' if stack=='sky130' else 'SOI + Al'}"
checks=[c['deltaE00'] for name in CASES if (RUNS/name/'numerical_checks.json').exists() for c in json.loads((RUNS/name/'numerical_checks.json').read_text())]
page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Color2GDS case studies</title>
<style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 24px;background:#f2f5fa;color:#213446}section{background:white;border-radius:16px;padding:26px;margin:24px 0}h1{font-size:36px}p,li{line-height:1.8}img{max-width:100%}a{color:#1764a0}pre{overflow:auto;background:#edf1f6;padding:16px}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #dce3eb}select{font-size:16px;padding:8px}</style>
<h1>Color2GDS case studies</h1><p>Image, minimum width and spacing, GDS layer and layer stack → GDS and predicted appearance</p>
<section><h2>Two images on two layer stacks</h2><p>Every prediction is computed from the generated GDS after reading it back. Empty areas show the reflection of each stack's substrate.</p>
'''
page+='<img src="'+embed(RUNS/'case_comparison.png')+'"></section>'
page+='<section><h2>Results</h2><table><tr><th>Case</th><th>GDS</th><th>Mean ΔE00</th><th>Checks</th></tr>'
for name in CASES:
    s=json.loads((RUNS/name/'summary.json').read_text())
    drc=(RUNS/name/'magic_drc.txt')
    check='Geometry check and GDS read-back match'
    if drc.exists() and 'Error categories: 0' in drc.read_text():check+=' / Magic drc(full): 0 errors'
    page+='<tr><td>'+html.escape(label(name))+'</td><td><a href="'+name+'/image.gds">image.gds</a></td><td>'+f"{s['mean_deltaE00_source']:.2f}"+'</td><td>'+check+'</td></tr>'
page+='</table><p>ΔE00 is the color difference from the input RGB image. The Magic check excludes density and antenna rules and is not a manufacturing sign-off.</p>'
if checks:page+=f'<p>For the two most-used cells of each case, we reran with 51 instead of 31 modes and a 0.5 nm instead of 1 nm step. The predicted color changed by at most ΔE00 = {max(checks):.3f}. This is not a convergence guarantee for every cell; see numerical_checks.json in each folder.</p>'
page+='</section><section><h2>GDS and simulation outputs</h2><p>'+' / '.join(f'<a href="{name}/report.html">{html.escape(label(name))}</a>' for name in CASES)+''' / <a href="COMPILER.md">Compiler reference (Japanese)</a></p>
<p>Each folder holds the full output: image.gds, image.bmp, appearance.png, appearance.npz, manifest.json and summary.json. The NPZ stores per-cell reflection spectra and the pixel-to-cell mapping.</p></section>
<section><h2>Compare the metal patterns</h2><select id="case">'''+''.join(f'<option value="{i}">{html.escape(label(name))}</option>' for i,name in enumerate(CASES))+'''</select><p>Close-up of the polygons read back from the GDS.</p><img id="detail"></section>
<section><h2>What the closed loop covers</h2><p>The candidate-cell GDS is read back to compute the palette, and the image is mapped onto it. Line widths of frequently used candidates are searched ±1 grid step, then the final GDS is read back and recomputed to match the prediction made during optimization. This checks consistency within one forward model; it is not a calibration against measurements.</p>
<p>Supported are planar stacks where all patterned films share one 1D rectangular line grating. The SKY130 polyimide optical constants and the TiN cap are assumptions. The SOI stack (Al 100 nm / Si 220 nm / BOX 2 µm) is a comparison setting. Arbitrary 2D shapes, independent multi-layer patterns, coupling between neighboring pixels and dummy fill are out of scope.</p></section>
'''
detail=[embed(RUNS/name/'layout_detail.png') for name in CASES]
page+='<script>const images='+json.dumps(detail)+';let c=document.querySelector("#case");function show(){document.querySelector("#detail").src=images[Number(c.value)]}c.onchange=show;show();</script></html>'
(RUNS/'index.html').write_text(page,encoding='utf-8')
metadata={'compiler_sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'color2gds').glob('*.py'))+sorted((ROOT/'presets').glob('*.yaml'))},
          'input_sha256':{sample:json.loads((RUNS/f'sky130_{sample}'/'manifest.json').read_text())['source_sha256'] for sample in SAMPLES},
          'pdk_version':'bdc9412b3e468c102d01b7cf6337be06ec6e9c9a','magic_version':'8.3.678'}
(RUNS/'case_metadata.json').write_text(json.dumps(metadata,indent=2))
print('Wrote runs/index.html and case_comparison.png')
