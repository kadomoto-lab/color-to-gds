"""Exercise HTTP boundaries and job configuration without launching expensive solvers."""
import io
import json
from types import SimpleNamespace
import pytest
pytest.importorskip('fastapi')
pytest.importorskip('httpx')
from fastapi.testclient import TestClient
from PIL import Image
from webgui import server

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'JOBS', tmp_path)
    monkeypatch.setattr(server, 'STATES', {})
    monkeypatch.setattr(server, 'POOL', SimpleNamespace(submit=lambda *a: None))
    with TestClient(server.app) as c: yield c

def form(client, **options):
    stack=client.get('/api/presets/soi_al').json()['stack']
    return {'stack':json.dumps(stack),'options':json.dumps({'gds_layer':1,**options}),'sample':'zundamon'}

def test_submission_and_cancel(client):
    r=client.post('/api/jobs',data=form(client))
    assert r.status_code==202,r.text
    job=r.json(); d=server.JOBS/job['id']
    assert (d/'input.image').read_bytes()==(server.ROOT/'samples/zundamon.png').read_bytes()
    assert job['label']=='Zundamon'
    assert client.get(f"/api/jobs/{job['id']}/files/image.gds").status_code==409
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()['status']=='cancelled'

@pytest.mark.parametrize('options',[{'min_width_um':.05},{'pixel_size_um':7.813},{'gds_layer':-1},{'columns':1000}])
def test_invalid_constraints_rejected(client,options):
    assert client.post('/api/jobs',data=form(client,**options)).status_code==422
    assert not list(server.JOBS.iterdir())

def test_wrong_physical_layer(client):
    data=form(client);data['stack']=json.dumps(client.get('/api/presets/sky130').json()['stack'])
    assert client.post('/api/jobs',data=data).status_code==422

def test_pbm_preview_and_invalid_upload(client):
    source=io.BytesIO();Image.new('1',(12,8),1).save(source,format='PPM')
    r=client.post('/api/preview',files={'image':('tiny.pbm',source.getvalue())})
    assert r.status_code==200 and Image.open(io.BytesIO(r.content)).size==(12,8)
    assert client.post('/api/preview',files={'image':('bad.png',b'not an image')}).status_code==422

def test_downloads_and_local_boundary(client):
    r=client.get('/api/jobs/sample-sky130_zundamon/files/image.gds?download=true')
    assert r.status_code==200 and 'attachment' in r.headers['content-disposition']
    assert r.content==(server.SAMPLES['sky130_zundamon']/'image.gds').read_bytes()
    assert client.get('/api/jobs/sample-sky130_zundamon/files/stack.yaml').status_code==404
    assert client.post('/api/jobs',data=form(client),headers={'Origin':'https://other.example'}).status_code==403
    assert client.get('/',headers={'Host':'other.example'}).status_code==403

def test_custom_stack_validation(client):
    assert client.post('/api/stack/validate',json={'yaml':'layers: bad'}).status_code==422
    data=client.get('/api/presets/soi_al').json()['stack'];data['layers'][1]['thickness_um']=.12
    r=client.post('/api/stack/validate',json={'yaml':json.dumps(data)})
    assert r.status_code==200 and r.json()['stack']['layers'][1]['thickness_um']==.12

@pytest.mark.parametrize('name,materials', [
    ('si_al_sio2_al_pattern', ['air', 'Al', 'SiO2', 'Al', 'Si']),
    ('si_sio2_al_sio2_pattern', ['air', 'SiO2', 'Al', 'SiO2', 'Si']),
])
def test_new_process_submission(client, name, materials):
    assert name in {p['id'] for p in client.get('/api/presets').json()['presets']}
    response = client.get('/api/presets/' + name)
    assert response.status_code == 200
    stack = response.json()['stack']
    assert [layer['material'] for layer in stack['layers']] == materials
    assert [layer['thickness_um'] for layer in stack['layers']] == [0, .1, .1, .1, 0]
    assert [i for i, layer in enumerate(stack['layers']) if layer.get('patterned')] == [1]
    assert stack['layers'][1]['background'] == 'air'
    data = form(client)
    data['stack'] = json.dumps(stack)
    response = client.post('/api/jobs', data=data)
    assert response.status_code == 202, response.text
    saved = server.load_stack(server.JOBS / response.json()['id'] / 'stack.yaml')
    assert saved['layers'] == stack['layers']


def test_preset_discovery(client, tmp_path, monkeypatch):
    definition = client.get('/api/presets/soi_al').json()['yaml']
    monkeypatch.setattr(server, 'PRESETS', tmp_path)
    assert client.get('/api/presets').json()['presets'] == []
    (tmp_path / 'custom.yaml').write_text(definition)
    (tmp_path / 'broken.yaml').write_text('not a stack')
    assert [p['id'] for p in client.get('/api/presets').json()['presets']] == ['custom']
    assert client.get('/api/presets/custom').status_code == 200
    assert client.get('/api/presets/broken').status_code == 422
    assert client.get('/api/presets/missing').status_code == 404


def test_saved_palette_preview_and_download(client, tmp_path, monkeypatch):
    import shutil
    import numpy as np
    from optics import color
    source = server.SAMPLES['soi_al_zundamon']
    manifest = json.loads((source / 'manifest.json').read_text())
    calibration = f"calibration_{manifest['optimization_history'][-1]['round']}.gds"
    for name in ['manifest.json', 'palette.npz', calibration]:
        shutil.copyfile(source / name, tmp_path / name)
    monkeypatch.setattr(server, 'SAMPLES', {**server.SAMPLES, 'soi_al_zundamon': tmp_path})
    response = client.get('/api/jobs/sample-soi_al_zundamon/files/palette.png')
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'image/png'
    image = Image.open(io.BytesIO(response.content))
    with np.load(tmp_path / 'palette.npz') as data:
        expected = tuple(np.uint8(np.array(color(data['reflectance'][0], data['wavelength_nm'])['rgb']) * 255 + .5))
    assert image.getpixel((30, 175)) == expected
    response = client.get('/api/jobs/sample-soi_al_zundamon/files/palette.png?download=true')
    assert response.status_code == 200
    assert 'attachment' in response.headers['content-disposition']
    assert not (tmp_path / 'palette.png').exists()
    job = client.post('/api/jobs', data=form(client)).json()
    assert client.get(f"/api/jobs/{job['id']}/files/palette.png").status_code == 409


@pytest.mark.parametrize('sample', sorted(server.SAMPLES))
def test_palette_spectra_match_saved_data(client, sample):
    import numpy as np
    from optics import color
    response = client.get(f'/api/jobs/sample-{sample}/palette')
    assert response.status_code == 200, response.text
    palette = response.json()
    with np.load(server.SAMPLES[sample] / 'palette.npz') as data:
        assert palette['wavelength_nm'] == data['wavelength_nm'].tolist()
        spectra = np.vstack([data['reflectance'], data['blank']])
        assert len(palette['entries']) == len(spectra)
        for entry, spectrum in zip(palette['entries'], spectra):
            assert entry['reflectance'] == spectrum.tolist()
            rgb = np.uint8(np.array(color(spectrum, data['wavelength_nm'])['rgb']) * 255 + .5)
            assert entry['hex'] == '#' + ''.join(f'{v:02x}' for v in rgb)
    assert all(e['pitch_nm'] > e['width_nm'] > 0 for e in palette['entries'][:-1])
    assert palette['entries'][-1]['pitch_nm'] is None
    assert palette['entries'][-1]['width_nm'] is None
    manifest = json.loads((server.SAMPLES[sample] / 'manifest.json').read_text())
    assert palette['blank_comparison_only'] == (manifest.get('opaque_pixels_allow_blank') is False)


def test_palette_unavailable_and_unfinished(client, tmp_path, monkeypatch):
    assert client.get('/api/jobs/missing/palette').status_code == 404
    job = client.post('/api/jobs', data=form(client)).json()
    assert client.get(f"/api/jobs/{job['id']}/palette").status_code == 409
    monkeypatch.setattr(server, 'SAMPLES', {'empty': tmp_path})
    response = client.get('/api/jobs/sample-empty/palette')
    assert response.status_code == 404
    assert 'palette source data' in response.json()['detail']


def test_ui_assets_revalidate_and_bypass_legacy_cache(client):
    from html.parser import HTMLParser
    from urllib.parse import urlsplit

    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'script':
                self.urls.append(attrs['src'])
            elif tag == 'link' and attrs.get('rel') == 'stylesheet':
                self.urls.append(attrs['href'])

    response = client.get('/')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-cache'
    assets = Assets()
    assets.feed(response.text)
    assert any(urlsplit(url).path == '/static/app.js' for url in assets.urls)
    for url in assets.urls:
        # Previously cached URLs had no query string.
        assert urlsplit(url).query
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-cache'
        cached = client.get(url, headers={'If-None-Match': response.headers['etag']})
        assert cached.status_code == 304
        assert cached.headers['cache-control'] == 'no-cache'


def test_palette_png_language(client):
    english = client.get('/api/jobs/sample-sky130_zundamon/files/palette.png')
    japanese = client.get('/api/jobs/sample-sky130_zundamon/files/palette.png?lang=ja')
    assert english.status_code == japanese.status_code == 200
    assert english.content != japanese.content
