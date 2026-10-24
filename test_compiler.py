from pathlib import Path
import copy
import numpy as np
import pytest
import gdstk
from color2gds.model import load_stack,epsilon,one_wavelength
from color2gds.layout import candidates,write_gds,read_gds

ROOT=Path(__file__).parent

@pytest.mark.parametrize('preset',['sky130','soi_al'])
def test_homogeneous_limit_against_fresnel(preset):
    cfg=load_stack(ROOT/'presets'/f'{preset}.yaml')
    for w in [407,553,731]:
        n=[np.sqrt(epsilon(cfg,x['material'],w)+0j) for x in cfg['layers']]
        r=0j
        for i in range(len(n)-2,-1,-1):
            f=(n[i]-n[i+1])/(n[i]+n[i+1]);p=np.exp(4j*np.pi*n[i+1]*cfg['layers'][i+1]['thickness_um']/(w/1000))
            r=(f+r*p)/(1+f*r*p)
        observed=one_wavelength(cfg,w,.4,.4,modes=11)
        assert np.max(abs(observed[:,0]-abs(r)**2))<2e-6

def fixture_layout(tmp_path):
    cfg=load_stack(ROOT/'presets/soi_al.yaml');geos=candidates(cfg,.14,.14,7.815)
    m={'stack':cfg,'pixel_size_um':7.815,'grid':[2,2],'min_width_um':.14,'min_space_um':.14,'gds_layer':1,'gds_datatype':0}
    path=tmp_path/'image.gds';write_gds(path,geos,np.array([[0,1],[-1,0]]),7.815,1,0)
    return path,m,geos

def test_gds_roundtrip_and_orientation(tmp_path):
    path,m,geos=fixture_layout(tmp_path);actual,ids,top=read_gds(path,m)
    assert np.array_equal(ids,[[0,1],[-1,0]])
    assert actual==geos[:2]

def test_tampered_geometry_rejected(tmp_path):
    path,m,_=fixture_layout(tmp_path);lib=gdstk.read_gds(path)
    pixel=next(c for c in lib.cells if c.polygons)
    p=pixel.polygons[0];b=np.array(p.bounding_box());pixel.remove(p)
    pixel.add(gdstk.rectangle(b[0],(b[0,0]+.05,b[1,1]),layer=1,datatype=0));lib.write_gds(path)
    with pytest.raises(ValueError):read_gds(path,m)

def test_wrong_layer_rejected(tmp_path):
    path,m,_=fixture_layout(tmp_path);m['gds_layer']=2
    with pytest.raises(ValueError,match='layer'):read_gds(path,m)

def test_material_schema_rejects_unknown(tmp_path):
    src=(ROOT/'presets/soi_al.yaml').read_text().replace('material: Al','material: Mystery')
    p=tmp_path/'bad.yaml';p.write_text(src)
    with pytest.raises(ValueError,match='Unknown material'):load_stack(p)


def test_opaque_pixels_keep_grating_when_blank_is_closest(tmp_path, monkeypatch):
    """A blank-colored target must still emit stripes; transparency remains blank."""
    from argparse import Namespace
    from PIL import Image
    from color2gds import compiler

    cfg = load_stack(ROOT/'presets/soi_al.yaml')
    source = tmp_path/'target.png'
    image = Image.new('RGBA', (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (0, 0, 0, 255))
    image.save(source)

    def fake_forward(_cfg, geos, _settings, _cache, _workers):
        wavelengths = np.arange(380., 781., 5.)
        white = {'Lab': [100., 0., 0.], 'rgb': [1., 1., 1.]}
        blank = {'Lab': [0., 0., 0.], 'rgb': [0., 0., 0.]}
        return wavelengths, np.zeros((len(geos), len(wavelengths))), [white] * len(geos), np.zeros(len(wavelengths)), blank

    monkeypatch.setattr(compiler, 'forward', fake_forward)
    args = Namespace(image=str(source), out=str(tmp_path/'output'), min_width_um=.14,
                     min_space_um=.14, pixel_size_um=7.815, columns=8,
                     gds_layer=1, angle_deg=0., modes=11, step_nm=5.,
                     refine_rounds=0, mapping='color', cache=str(tmp_path/'cache'), workers=1)
    compiler.compile_image(args, cfg)
    out = tmp_path/'output'
    manifest = __import__('json').loads((out/'manifest.json').read_text())
    geos, ids, _ = read_gds(out/'image.gds', manifest)
    rgba = np.array(image.resize((8, 4), Image.Resampling.LANCZOS))
    opaque = rgba[:, :, 3] >= 128
    assert opaque.any() and (~opaque).any()
    assert np.all(ids[opaque] >= 0)
    assert np.all(ids[~opaque] == -1)
    assert manifest['opaque_pixels_allow_blank'] is False
    with np.load(out/'palette.npz') as palette:
        assert len(palette['Lab']) == manifest['optimization_history'][-1]['candidate_count'] + 1
    assert (out/'palette.png').is_file()
