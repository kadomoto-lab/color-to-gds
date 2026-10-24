import os
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
import io
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
import yaml
from color2gds.model import load_stack
from color2gds.layout import candidates
from .vendor import ROOT, VENDOR

PRESETS = ROOT / 'presets'
JOBS = ROOT / 'runs' / 'web'
JOBS.mkdir(parents=True, exist_ok=True)
SAMPLES = {f'{stack}_{name}': ROOT/f'runs/{stack}_{name}' for name in ['zundamon', 'metan'] for stack in ['sky130', 'soi_al']}
SAMPLE_IMAGES = {'zundamon': (ROOT/'samples/zundamon.png', 'Zundamon'), 'metan': (ROOT/'samples/metan.png', 'Shikoku Metan')}
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.RLock()
PROCESSES = {}
STATES = {}
@asynccontextmanager
async def lifespan(app):
    for p in JOBS.glob('*/job.json'):
        state = json.loads(p.read_text())
        if state['status'] in ['queued', 'running']:
            state.update(status='interrupted', error='The run was interrupted because the server stopped. Please run it again.')
            p.write_text(json.dumps(state, ensure_ascii=False))
        STATES[state['id']] = state
    yield
    with LOCK:
        for state in STATES.values():
            if state['status'] in ['queued', 'running']:
                state.update(status='interrupted', error='The run was interrupted because the server stopped.')
                save(state)
        for process in PROCESSES.values():
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass

app = FastAPI(title='Color2GDS Studio', docs_url=None, redoc_url=None, lifespan=lifespan)

@app.middleware('http')
async def local_requests(request, call_next):
    if request.url.hostname not in ['localhost', '127.0.0.1', 'testserver']:
        return JSONResponse({'detail': 'Localhost access only'}, status_code=403)
    if request.method == 'POST':
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
            return JSONResponse({'detail': 'Same-origin request required'}, status_code=403)
        try:
            if int(request.headers.get('content-length', '0')) > 18 * 1024 * 1024:
                return JSONResponse({'detail': 'Images must be 16 MB or smaller.'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': 'Invalid content length'}, status_code=400)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Revalidate UI files together so HTML changes cannot leave stale JS in use.
    if request.url.path == '/' or (request.url.path.startswith('/static/')
                                    and request.url.path.endswith(('.js', '.css'))):
        response.headers['Cache-Control'] = 'no-cache'
    return response

class Options(BaseModel):
    min_width_um: float = Field(default=.14, ge=.005, le=10, allow_inf_nan=False)
    min_space_um: float = Field(default=.14, ge=.005, le=10, allow_inf_nan=False)
    pixel_size_um: float = Field(default=7.815, ge=.1, le=100, allow_inf_nan=False)
    columns: int = Field(default=128, ge=8, le=256)
    gds_layer: int = Field(default=68, ge=0, le=65535)
    angle_deg: float = Field(default=0, ge=0, lt=80, allow_inf_nan=False)
    modes: int = Field(default=31, ge=11, le=51)
    step_nm: float = Field(default=1, ge=.5, le=5, allow_inf_nan=False)
    refine_rounds: int = Field(default=1, ge=0, le=3)
    mapping: str = 'color'

def validate_stack(text):
    if len(text) > 64000:
        raise ValueError('The layer stack definition is too large.')
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)/'stack.yaml'; p.write_text(text)
        cfg = load_stack(p)
    if not isinstance(cfg.get('name'), str) or not cfg['name'].strip():
        raise ValueError('The layer stack needs a name.')
    if len(cfg['layers']) > 24:
        raise ValueError('A layer stack can have at most 24 layers.')
    return cfg

def save(state):
    STATES[state['id']] = state
    p = JOBS/state['id']/'job.json'
    p.with_suffix('.tmp').write_text(json.dumps(state, ensure_ascii=False))
    p.with_suffix('.tmp').replace(p)

def execute(job_id, command):
    directory = JOBS/job_id
    with LOCK:
        state = STATES[job_id]
        if state['status'] != 'queued': return
        state.update(status='running', started=time.time())
        save(state)
        log = (directory/'compile.log').open('w')
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except Exception as exc:
            log.close(); state.update(status='failed', error=str(exc)); save(state); return
        PROCESSES[job_id] = process
    code = process.wait()
    log.close()
    with LOCK:
        PROCESSES.pop(job_id, None)
        if state['status'] not in ['cancelled', 'interrupted']:
            state['status'] = 'complete' if code == 0 else 'failed'
            if code:
                state['error'] = (directory/'compile.log').read_text(errors='replace')[-4000:]
        state['finished'] = time.time()
        save(state)

def output_dir(job_id):
    if job_id.startswith('sample-') and job_id[7:] in SAMPLES:
        return SAMPLES[job_id[7:]]
    if job_id not in STATES:
        raise HTTPException(404, 'Output not found.')
    return JOBS/job_id/'output'

@app.get('/')
def home(): return FileResponse(Path(__file__).parent/'static/index.html')

@app.get('/favicon.ico')
def favicon(): return Response(status_code=204)

@app.get('/viewer/')
def viewer(): return FileResponse(VENDOR/'viewer.html', media_type='text/html')

@app.get('/viewer/LICENSE.txt')
def license_text(): return FileResponse(VENDOR/'LICENSE.txt', media_type='text/plain')

def preset_paths():
    return {p.stem: p for p in sorted(PRESETS.glob('*.yaml')) if p.is_file()}

def read_preset(path):
    try:
        text = path.read_text(encoding='utf-8-sig')
        return {'yaml': text, 'stack': validate_stack(text)}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, yaml.YAMLError) as exc:
        raise HTTPException(422, f'{path.name}: Invalid layer stack definition: {exc}')

@app.get('/api/presets')
def list_presets():
    entries = []
    for name, path in preset_paths().items():
        try:
            entries.append({'id': name, 'name': read_preset(path)['stack']['name']})
        except HTTPException:
            continue
    return {'presets': entries}

@app.get('/api/presets/{name}')
def preset(name: str):
    path = preset_paths().get(name)
    if path is None: raise HTTPException(404)
    return read_preset(path)

@app.post('/api/stack/validate')
async def stack_validate(request: Request):
    try:
        data = await request.json()
        cfg = validate_stack(data['yaml'])
        return {'stack': cfg, 'yaml': yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)}
    except (ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError) as exc:
        raise HTTPException(422, 'Invalid layer stack definition: '+str(exc))

@app.get('/api/jobs')
def list_jobs():
    with LOCK:
        recent = sorted(STATES.values(), key=lambda x: x['created'], reverse=True)[:20]
        return {'jobs': recent}

@app.post('/api/preview')
async def preview(request: Request):
    try:
        form = await request.form(max_files=1, max_fields=1)
        data = await form['image'].read(16*1024*1024+1)
        if len(data) > 16*1024*1024: raise ValueError('Images must be 16 MB or smaller.')
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ['PNG','JPEG','PPM','BMP']: raise ValueError('Unsupported image format.')
            if im.width*im.height > 16_000_000: raise ValueError('Images must have at most 16 million pixels.')
            im.thumbnail((360,360)); output = io.BytesIO(); im.convert('RGBA').save(output, format='PNG')
        return Response(output.getvalue(), media_type='image/png')
    except (ValueError, KeyError, AttributeError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, str(exc))

@app.get('/api/jobs/{job_id}')
def job(job_id: str):
    if job_id.startswith('sample-') and job_id[7:] in SAMPLES:
        state = {'id': job_id, 'status': 'complete', 'label': 'Saved case study'}
    else:
        with LOCK:
            if job_id not in STATES: raise HTTPException(404)
            state = dict(STATES[job_id])
        p = JOBS/job_id/'compile.log'
        state['log'] = p.read_text(errors='replace')[-5000:] if p.exists() else ''
    if state['status'] == 'complete':
        d = output_dir(job_id)
        state['summary'] = json.loads((d/'summary.json').read_text())
        state['manifest'] = json.loads((d/'manifest.json').read_text())
    return state

@app.post('/api/jobs')
async def submit(request: Request):
    try:
        form = await request.form(max_files=1, max_fields=8, max_part_size=17*1024*1024)
        opts = Options.model_validate_json(form['options'])
        cfg = validate_stack(form['stack'])
        if opts.modes % 2 != 1 or abs(400/opts.step_nm-round(400/opts.step_nm)) > 1e-8:
            raise ValueError('The number of modes must be odd and the wavelength step must divide 400 nm.')
        if opts.mapping not in ['color', 'contrast']: raise ValueError('Invalid mapping')
        if cfg['gds'].get('fixed_layer') and opts.gds_layer != cfg['gds']['layer']:
            raise ValueError('The GDS layer does not match the selected layer stack.')
        grid = cfg['rules']['grid_um']
        if abs(opts.pixel_size_um/grid-round(opts.pixel_size_um/grid)) > 1e-7:
            raise ValueError(f'The pixel size must be a multiple of the {grid} µm manufacturing grid.')
        if opts.min_width_um < cfg['rules']['min_width_um'] or opts.min_space_um < cfg['rules']['min_space_um']:
            raise ValueError('The line width or spacing is below the minimum rule of the layer stack.')
        candidates(cfg, opts.min_width_um, opts.min_space_um, opts.pixel_size_um)
        upload = form.get('image')
        if upload and hasattr(upload, 'read'):
            data = await upload.read(16*1024*1024+1)
            label = Path(upload.filename or 'image').name
        elif form.get('sample') in SAMPLE_IMAGES:
            path, label = SAMPLE_IMAGES[form['sample']]; data = path.read_bytes()
        else: raise ValueError('Please select an input image.')
        if len(data) > 16*1024*1024: raise ValueError('Images must be 16 MB or smaller.')
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ['PNG', 'JPEG', 'PPM', 'BMP']: raise ValueError('Unsupported image format.')
            if im.width*im.height > 16_000_000: raise ValueError('Images must have at most 16 million pixels.')
            rows = max(1, round(opts.columns*im.height/im.width))
            if rows > 512 or rows*opts.columns > 65536: raise ValueError('The output image is too large. Reduce the number of columns.')
            im.verify()
        with LOCK:
            if sum(s['status'] in ['queued','running'] for s in STATES.values()) >= 5:
                raise HTTPException(429, 'Five runs are already queued. Please try again after they finish.')
            job_id = uuid.uuid4().hex[:16]; d = JOBS/job_id; d.mkdir()
            (d/'input.image').write_bytes(data)
            (d/'stack.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False))
            command = [sys.executable, '-u', '-m', 'color2gds', 'compile', str(d/'input.image'),
                       '--stack', str(d/'stack.yaml'), '--out', str(d/'output'), '--workers', '3']
            for k,v in opts.model_dump().items(): command += ['--'+k.replace('_','-'), str(v)]
            state = {'id':job_id, 'status':'queued', 'created':time.time(), 'label':label,
                     'stack_name':cfg['name'], 'options':opts.model_dump()}
            save(state)
            POOL.submit(execute, job_id, command)
        return JSONResponse(state, status_code=202)
    except HTTPException: raise
    except (ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, str(exc))

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id: str):
    with LOCK:
        if job_id not in STATES: raise HTTPException(404)
        s = STATES[job_id]
        if s['status'] in ['queued', 'running']:
            s['status'] = 'cancelled'; save(s)
            p = PROCESSES.get(job_id)
            if p and p.poll() is None:
                try: os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError: pass
        return s

@app.get('/api/jobs/{job_id}/palette')
def palette(job_id: str):
    d = output_dir(job_id)
    if not job_id.startswith('sample-') and STATES[job_id]['status'] != 'complete':
        raise HTTPException(409, 'This output is not finished yet.')
    from color2gds.palette import palette_data
    try:
        return palette_data(d)
    except FileNotFoundError:
        raise HTTPException(404, 'The palette source data is missing.')


ARTIFACTS = {'image.gds', 'image.bmp', 'appearance.png', 'appearance_large.png', 'appearance.npz',
             'input.png', 'input_white.png', 'manifest.json', 'summary.json', 'report.html', 'readback.json',
             'comparison.png', 'layout_detail.png', 'palette.npz', 'palette.png'}

@app.get('/api/jobs/{job_id}/files/{name}')
def file(job_id: str, name: str, download: bool = False, lang: str = 'en'):
    if name not in ARTIFACTS: raise HTTPException(404)
    d = output_dir(job_id)
    if not job_id.startswith('sample-') and STATES[job_id]['status'] != 'complete':
        raise HTTPException(409, 'This output is not finished yet.')
    p = d/name
    if name == 'palette.png':
        from color2gds.palette import palette_png
        try:
            content = palette_png(d, 'ja' if lang == 'ja' else 'en')
        except FileNotFoundError:
            raise HTTPException(404, 'The palette source data is missing.')
        return Response(content, media_type='image/png',
                        headers={'Content-Disposition': 'attachment; filename="palette.png"'} if download else {})
    if not p.is_file(): raise HTTPException(404)
    return FileResponse(p, filename=name if download else None,
                        media_type='application/octet-stream' if name.endswith(('.gds','.npz')) else None)

app.mount('/static', StaticFiles(directory=Path(__file__).parent/'static'), name='static')
