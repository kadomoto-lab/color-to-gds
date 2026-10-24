"""Start the local workbench: uv run run_web.py [--port 8765]."""
import argparse
import os
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
from webgui.vendor import prepare
import uvicorn

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    prepare()
    uvicorn.run('webgui.server:app', host='127.0.0.1', port=args.port)
