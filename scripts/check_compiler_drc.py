"""Optional SKY130 Magic check. Geometry validation runs first; never claims density signoff."""
import argparse,json,os,subprocess
from pathlib import Path
from color2gds.layout import read_gds

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run');p.add_argument('--magic',required=True);p.add_argument('--pdk-root',required=True);args=p.parse_args()
    run=Path(args.run).resolve();manifest=json.loads((run/'manifest.json').read_text());read_gds(run/'image.gds',manifest)
    if manifest['gds_layer'] not in [68,69] or manifest['gds_datatype']!=20:raise ValueError('Only SKY130 Met1/Met2 drawing layers supported for this check')
    # Magic runs with cwd=run, so the script uses run-relative paths and stays portable.
    if any(c in args.pdk_root for c in '{}\n'):raise ValueError('Unsupported path characters')
    output=run/'magic_drc.txt';script=run/'check_drc.tcl'
    script.write_text('''crashbackups stop
drc euclidean on
drc style drc(full)
drc off
gds read {GDS}
load COLOR_IMAGE
select top cell
expand
drc on
drc check
drc catchup
set errors [drc listall why]
set file [open {OUTPUT} w]
puts $file "Magic drc(full): density and antenna excluded"
puts $file "Error categories: [expr {[llength $errors]/2}]"
puts $file $errors
close $file
quit -noprompt
'''.replace('{GDS}','{image.gds}').replace('{OUTPUT}','{magic_drc.txt}'))
    env=dict(os.environ,PDK_ROOT=str(Path(args.pdk_root).resolve()))
    r=subprocess.run([str(Path(args.magic).resolve()),'-dnull','-noconsole','-rcfile',str(Path(args.pdk_root)/'sky130A/libs.tech/magic/sky130A.magicrc'),str(script)],cwd=run,env=env,capture_output=True,text=True)
    (run/'magic_run.log').write_text(r.stdout+'\n'+r.stderr)
    if r.returncode or not output.exists():raise RuntimeError('Magic failed; inspect magic_run.log')
    print(output.read_text())
