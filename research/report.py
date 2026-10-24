"""Static scientific plots, research GDS and offline interactive HTML."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json,csv,base64
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import colour,gdstk
from color2gds.optics import ROOT,WL,color,planar_reflectance
R=ROOT/'research/results'
P=json.loads((R/('palette_refined.json' if (R/'palette_refined.json').exists() else 'palette.json')).read_text()); cells=P['cells']
WL=np.array(P['wavelength_nm'])
F=['m1_grating','m2_grating','m2_m1_mirror']
LABEL=['M1 grating','M2 grating','M2 grating + M1 mirror']
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f5f7fb','axes.facecolor':'white','savefig.facecolor':'#f5f7fb'})
def save(fig,name):
    fig.savefig(R/f'{name}.png',dpi=160,bbox_inches='tight');plt.close(fig)
fig,axs=plt.subplots(3,1,figsize=(13,7.5),layout='constrained')
for ax,f,label in zip(axs,F,LABEL):
    for j,c in enumerate([c for c in cells if c['family']==f]):
        x=j%23;y=1-j//23
        ax.add_patch(Rectangle((x,y),1,.9,facecolor=c['rgb'],edgecolor='white'))
        ax.text(x+.5,y+.45,f"{c['pitch']*1000:.0f}/{c['width']*1000:.0f}",ha='center',va='center',fontsize=6.5,color='black' if c['XYZ'][1]>.28 else 'white')
    ax.set(xlim=(0,23),ylim=(-.1,2.1),title=label);ax.axis('off')
fig.suptitle('SKY130-inspired structural color | 138 simulated geometries\nD65, normal incidence, unpolarized specular reflection | pitch / width (nm)',fontsize=14)
save(fig,'palette')
fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
loc=colour.XYZ_to_xy(colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].values)
axs[0].plot(loc[:,0],loc[:,1],c='.6',lw=1)
srgb=np.array([[.64,.33],[.3,.6],[.15,.06],[.64,.33]])
axs[0].plot(*srgb.T,'--',c='.5',label='sRGB triangle')
for f,marker,label in zip(F,['o','s','^'],LABEL):
    sub=[c for c in cells if c['family']==f];xy=np.array([c['xy'] for c in sub]);lab=np.array([c['Lab'] for c in sub])
    axs[0].scatter(*xy.T,c=[c['rgb'] for c in sub],marker=marker,edgecolor='#202530',lw=.4,s=40,label=label)
    axs[1].scatter(lab[:,1],lab[:,2],c=[c['rgb'] for c in sub],marker=marker,edgecolor='#202530',lw=.4,s=40)
axs[0].set(xlim=(.05,.75),ylim=(0,.85),xlabel='CIE x',ylabel='CIE y',title='Chromaticity of sampled palette')
axs[0].legend(fontsize=8)
axs[1].axhline(0,c='.8');axs[1].axvline(0,c='.8')
axs[1].set(xlabel='CIELAB a*',ylabel='CIELAB b*',title='Color spread (D65 white reference)')
fig.suptitle('Finite sampled palette: not proof of full-color coverage')
save(fig,'gamut')
screening=json.loads((R/'palette.json').read_text())['cells']
chosen_ids=[max([c for c in screening if c['family']==f],key=lambda c:np.linalg.norm(c['Lab'][1:]))['id'] for f in F]
selected=[next(c for c in cells if c['id']==i) for i in chosen_ids]
fig,axs=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
for ax,c,label in zip(axs,selected,LABEL):
    for key,name,style in [('R0_s','TE / s','-'),('R0_p','TM / p','-'),('R0','Unpolarized R0','-'),('Rtotal','Total reflection',':')]:
        ax.plot(WL,c[key],style,label=name,lw=1)
    ax.set(ylim=(0,1),xlabel='Wavelength (nm)',ylabel='Reflectance',title=f"{label}\np={c['pitch']*1000:.0f}, w={c['width']*1000:.0f} nm")
axs[0].legend(fontsize=8);save(fig,'spectra')
flat=np.array([planar_reflectance(w) for w in WL])
fig,ax=plt.subplots(figsize=(9,4),layout='constrained')
ax.plot(WL,flat,label='Flat M1 control')
for c in selected:ax.plot(WL,c['R0'],label=c['id'])
ax.set(xlabel='Wavelength (nm)',ylabel='Specular reflectance',ylim=(0,1),title='Patterned structures versus planar-stack control')
ax.legend(fontsize=8);save(fig,'controls')
fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
segments=[('Silicon',0,.3,'#657086'),('Lower dielectric (silica proxy)',.3,1.3761,'#d9edf6'),('M1 Al mirror',1.6761,.36,'#8093a7'),('Intermetal oxide',2.0361,.27,'#bcdcea'),('M2 grating in oxide',2.3061,.36,'#d9edf6'),('Upper dielectrics (silica proxy)',2.6661,4.355,'#d9edf6'),('Nitride proxy',7.0211,.3777,'#b5a9db')]
for name,z,d,col in segments:
    ax.add_patch(Rectangle((0,z),2,d,facecolor=col,edgecolor='white'))
    ax.text(2.2,z+d/2,('Silicon (semi-infinite)' if name=='Silicon' else f'{name} | {d:.4g} um'),va='center')
for x in np.arange(0,2,.4):ax.add_patch(Rectangle((x,2.3061),.2,.36,facecolor='#627d91'))
ax.text(0,7.65,'Incident light from air',fontsize=12)
ax.set(xlim=(-.1,7),ylim=(0,8),title='Optical model: M2 grating / M1 mirror\nM3-M5 absent; baseline excludes polyimide; barriers omitted')
ax.axis('off');save(fig,'stack')
lib=gdstk.Library(unit=1e-6,precision=1e-9);top=lib.new_cell('COLOR_COUPON')
manifest=[]
for i,c in enumerate(cells):
    cell=lib.new_cell(f'SC_{i:03d}');side=8.;margin=.28
    p=c['pitch'];w=c['width'];n=int((side-2*margin)/p)
    x0=round((side-n*p)/2/.005)*.005
    layer=68 if c['family']=='m1_grating' else 69
    for j in range(n):
        x=round((x0+j*p)/.005)*.005
        cell.add(gdstk.rectangle((x,margin),(round(x+w,3),side-margin),layer=layer,datatype=20))
    if c['family']=='m2_m1_mirror':
        cell.add(gdstk.rectangle((margin,margin),(side-margin,side-margin),layer=68,datatype=20))
    origin=((i%12)*10,(i//12)*10);top.add(gdstk.Reference(cell,origin))
    manifest.append(dict(index=i,id=c['id'],cell=cell.name,x_um=origin[0],y_um=origin[1],periods=n,mirror_requires_slotting_review=c['family']=='m2_m1_mirror'))
lib.write_gds(R/'color_coupon_research.gds')
readback=gdstk.read_gds(R/'color_coupon_research.gds')
assert len(readback.cells)==len(cells)+1
assert len(readback.top_level()[0].references)==len(cells)
for cell in readback.cells:
    for poly in cell.polygons:
        assert np.max(abs(poly.points/.005-np.round(poly.points/.005)))<1e-7
(R/'gds_manifest.json').write_text(json.dumps(manifest,indent=2))
fig,ax=plt.subplots(figsize=(9,9),layout='constrained')
for i,c in enumerate(cells):
    x=i%12*10;y=i//12*10
    ax.add_patch(Rectangle((x,y),8,8,facecolor=c['rgb'],edgecolor='.6'))
    ax.text(x+4,y+4,str(i),ha='center',va='center',fontsize=6,color='black' if c['XYZ'][1]>.28 else 'white')
ax.set(xlim=(-1,120),ylim=(-1,120),xlabel='x (um)',ylabel='y (um)',aspect='equal',title='Research coupon: simulated color key\nNot a finite-array EM simulation')
save(fig,'coupon')
with (R/'palette.csv').open('w',newline='') as f:
    wr=csv.writer(f);wr.writerow(['id','family','pitch_nm','width_nm','space_nm','L','a','b','R','G','B','Y'])
    for c in cells:wr.writerow([c['id'],c['family'],c['pitch']*1000,c['width']*1000,(c['pitch']-c['width'])*1000,*c['Lab'],*c['rgb'],c['XYZ'][1]])
with (R/'spectra.csv').open('w',newline='') as f:
    wr=csv.writer(f);wr.writerow(['id','wavelength_nm','R0_s','R0_p','R0_unpolarized','Rtotal_unpolarized','T_into_Si'])
    for c in cells:
        for i,w in enumerate(WL):wr.writerow([c['id'],w,c['R0_s'][i],c['R0_p'][i],c['R0'][i],c['Rtotal'][i],c['T'][i]])
stats={'cells':len(cells),'modes':P['modes'],'wavelength_points':len(WL),
'min_absorption_above_substrate':min(c['min_absorption_above_substrate'] for c in cells),
'max_Rtotal_plus_T':max(max(np.array(c['Rtotal'])+c['T']) for c in cells),
'max_chroma':max(np.linalg.norm(c['Lab'][1:]) for c in cells),
'min_Y':min(c['XYZ'][1] for c in cells),'max_Y':max(c['XYZ'][1] for c in cells),
'out_of_srgb_count':sum(c['out_of_srgb'] for c in cells),'flat_m1_color':color(flat,WL)}
studies=json.loads((R/'studies.json').read_text()) if (R/'studies.json').exists() else []
if studies:
    conv=[];sensitivity=[]
    fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
    for ax,c in zip(axs,selected):
        sub=[s for s in studies if s['id']==c['id']];d={s['variant']:s for s in sub}
        for s in sub:
            if s['variant'].startswith('modes_'):ax.plot(np.linspace(380,780,len(s['R0'])),s['R0'],label=s['variant'])
        ax.set(title=c['id'],xlabel='Wavelength (nm)',ylabel='R0',ylim=(0,1))
        if sub:ax.legend(fontsize=8)
        if 'modes_71' in d:
            for n in [31,51]:
                x=d[f'modes_{n}'];y=d['modes_71']
                conv.append(dict(id=c['id'],comparison=f'{n} vs 71',deltaE00=float(colour.delta_E(x['Lab'],y['Lab'],method='CIE 2000')),max_R0_diff=float(np.max(abs(np.array(x['R0'])-y['R0'])))))
    save(fig,'convergence');stats['convergence']=conv
    fig,axs=plt.subplots(3,1,figsize=(13,7),layout='constrained')
    for ax,c in zip(axs,selected):
        sub=[s for s in studies if s['id']==c['id'] and s['variant'] not in ['modes_31','modes_71']]
        if not sub:ax.axis('off');continue
        base=next(s for s in sub if s['variant']=='modes_51')
        for i,s in enumerate(sub):
            de=float(colour.delta_E(s['Lab'],base['Lab'],method='CIE 2000'))
            sensitivity.append(dict(id=c['id'],variant=s['variant'],deltaE00=de))
            ax.add_patch(Rectangle((i,0),.9,1,facecolor=s['rgb']))
            ax.text(i+.45,-.08,s['variant'].replace('_','\n'),ha='center',va='top',fontsize=8)
            ax.text(i+.45,1.05,f'{de:.1f}',ha='center',fontsize=9)
        ax.set(xlim=(-.1,len(sub)),ylim=(-.55,1.4),title=c['id']);ax.axis('off')
    fig.suptitle('Sensitivity of representative colors | numbers: Delta E00 from 51-mode baseline\n5 nm screening spectra; angle cases follow specular observation')
    save(fig,'sensitivity');stats['sensitivity']=sensitivity
stats['spectral_refinement']={'step_nm':float(WL[1]-WL[0]),'max_deltaE00_vs_5nm':max(c.get('deltaE00_vs_5nm',0) for c in cells)}
(R/'summary.json').write_text(json.dumps(stats,indent=2))
images=['palette','gamut','spectra','stack','controls','coupon']+(['convergence','sensitivity'] if studies else [])
body=''.join('<figure><img src="data:image/png;base64,'+base64.b64encode((R/f'{n}.png').read_bytes()).decode()+'"><figcaption>'+n+'</figcaption></figure>' for n in images)
head="""<!doctype html><html lang="ja"><meta charset="utf-8"><title>SKY130 Structural Color</title>
<style>body{font:16px system-ui;background:#eef2f8;color:#182738;max-width:1180px;margin:40px auto;padding:0 24px}h1{font-size:36px}p{line-height:1.8}.card,figure{background:white;border-radius:16px;padding:24px;margin:24px 0}img{width:100%}.badge{color:#784b13;background:#fff0d3;padding:12px;border-radius:8px}select{font-size:16px;padding:8px;max-width:100%}#swatch{width:100px;height:100px;border-radius:12px;float:right}svg{width:100%;height:auto}figcaption{color:#607185}a{color:#2264ab}</style>
<h1>SKY130 構造色シミュレーション</h1><p>Met1 / Met2 · 138 geometries · 380–780 nm (1 nm) · D65 / CIE 1931 2°</p>
<p class="badge">探索段階の光学モデル。製造色・フルカラー再現・DRC合格を保証する結果ではありません。</p>
<div class="card"><h2>今回の結果</h2><p><strong>色の違いは得られましたが、淡い色が中心で、鮮やかなフルカラーを再現する色域には達していません。</strong>
最大Lab彩度 C*ab は約CHROMA_VALUE、相対輝度YはY_MIN_VALUE–Y_MAX_VALUEです。角度や膜構造の条件を固定して探索を進める必要があります。</p>
<p>全138セルを1 nm刻みで再計算しました。5 nmからの変化が大きかった6セルを0.5 nmでも確認し、1 nmとの差はΔE00で0.05–0.55でした。全候補の誤差上限を保証する検証ではありません。</p></div>
<div class="card"><h2>計算条件と読み方</h2><p>垂直平面波、TE/TM平均の正反射（0次光）を色に変換。全反射強度とは区別しています。
Met1/Met2厚さ360 nm、間隔270 nm。上部誘電体は酸化膜4.355 µmと窒化膜377.7 nmで近似し、基準条件ではポリイミドなし。
Al・Siは文献の分散データ、酸化膜は溶融シリカの近似、窒化膜はn=2.0の仮定です。PDKの静的誘電率を光学屈折率に流用していません。</p>
<p>上部誘電体の材質差、金属バリア、表面粗さ、金属合金、周囲のダミーメタルは未モデル化。
最終パレットは1 nm刻み、代表構造の感度・次数比較は5 nm刻みの探索値です。色パレットは無限周期モデルです。8 µm有限タイルの端部・隣接セル結合は計算していません。角度比較は正反射方向に観察を追従させた場合です。</p>
<p>GDSは68/20 (Met1)、69/20 (Met2)、5 nmグリッド。最小線幅・周期内間隔140 nmの候補です。
全PDK DRC未実施。特に連続M1反射板はスロット・最大幅・密度ルールの検討が必要です。</p></div>
<div class="card"><h2>セルのスペクトルを調べる</h2><div id="swatch"></div><select id="cell"></select><p id="detail"></p><svg id="chart" viewBox="0 0 1000 340"></svg></div>
"""
tail="""<div class="card"><h2>一次資料・再現性</h2><p>
<a href="https://skywater-pdk.readthedocs.io/en/main/rules/assumptions.html">SKY130断面・寸法</a> /
<a href="https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html">設計ルール</a> /
<a href="https://doi.org/10.1364/AO.34.004755">Al: Rakić 1995</a> /
<a href="https://doi.org/10.1016/j.solmat.2008.06.009">Si: Green 2008</a> /
<a href="https://doi.org/10.1364/JOSA.55.001205">SiO2: Malitson 1965</a> /
<a href="https://github.com/weiliangjinca/grcwa">grcwa</a></p>
<p>READMEに実行方法・モデルの限界・検証結果を記録。数値データはpalette.json / spectra.csv、研究用レイアウトはcolor_coupon_research.gds。</p></div>
<script>const data=DATA;const sel=document.querySelector('#cell');data.cells.forEach((c,i)=>sel.add(new Option(c.id,i)));
function update(){const c=data.cells[sel.value];document.querySelector('#swatch').style.background='rgb('+c.rgb.map(v=>255*v).join(',')+')';
document.querySelector('#detail').textContent='pitch '+Math.round(c.pitch*1000)+' nm / width '+Math.round(c.width*1000)+' nm / space '+Math.round((c.pitch-c.width)*1000)+' nm / Y '+c.XYZ[1].toFixed(3);
let s='';for(let i=0;i<=5;i++){let y=280-i*48;s+='<line x1="65" x2="970" y1="'+y+'" y2="'+y+'" stroke="#d9e1eb"/><text x="20" y="'+(y+5)+'">'+(i*.2).toFixed(1)+'</text>'}
[400,500,600,700,780].forEach(w=>{let x=65+(w-380)/400*900;s+='<text x="'+x+'" y="309" text-anchor="middle">'+w+'</text>'});
[['R0_s','#377bb4'],['R0_p','#d27025'],['R0','#172430'],['Rtotal','#a9a9a9']].forEach(([k,col],j)=>{let pts=c[k].map((r,i)=>(65+i/(data.wavelength_nm.length-1)*900)+','+(280-r*240)).join(' ');s+='<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2"/><text x="'+(100+j*210)+'" y="24" fill="'+col+'">'+k+'</text>'});
s+='<text x="480" y="338">Wavelength (nm)</text>';document.querySelector('#chart').innerHTML=s}
sel.onchange=update;update();</script></html>"""
head=head.replace('CHROMA_VALUE',f"{stats['max_chroma']:.2f}").replace('Y_MIN_VALUE',f"{stats['min_Y']:.3f}").replace('Y_MAX_VALUE',f"{stats['max_Y']:.3f}")
(R/'report.html').write_text(head+body+tail.replace('DATA',json.dumps(P)),encoding='utf-8')
print(json.dumps(stats,indent=2))



