import contextlib,hashlib,io,json,os,sys,time
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parents[1];label='backup-files'if os.environ.get('NF_BACKUP_FILES')=='1'else'backup';home=R/('runtime/backup-files-hermes'if label=='backup-files'else'runtime/backup-source-hermes');os.environ['HERMES_HOME']=str(home);os.environ['HERMES_RUNTIME_DIR']=str(home/'runtime');sys.path.insert(0,'/root/output/openclaw-hermes-benchmark-20261022/sources/hermes')
from hermes_cli.backup import run_backup,run_import
expected=json.loads((R/'results/backup-manifest-hermes.json').read_text());records=[]
for i in range(4):
    os.environ['HERMES_HOME']=str(home);archive=R/f'runtime/{label}-hermes-{i}.zip';target=R/f'runtime/restore-{label}-hermes-{i}';capture=io.StringIO();start=time.monotonic()
    with contextlib.redirect_stdout(capture):backed_ok=run_backup(SimpleNamespace(output=str(archive)))
    backed=time.monotonic();os.environ['HERMES_HOME']=str(target);os.environ['HERMES_RUNTIME_DIR']=str(target/'runtime')
    with contextlib.redirect_stdout(capture):restored_ok=run_import(SimpleNamespace(zipfile=str(archive),force=True))
    restored=time.monotonic();folder=target/'portable-fixture';correct=0
    for name,sha in expected.items():
        p=folder/name
        if p.exists()and hashlib.sha256(p.read_bytes()).hexdigest()==sha:correct+=1
    rec={'framework':'hermes','sample':i-1,'warmup':i==0,'backup_ms':(backed-start)*1000,'restore_ms':(restored-backed)*1000,'archive_bytes':archive.stat().st_size,'correct_files':correct,'expected_files':64,'backup_ok':backed_ok,'restore_status':restored_ok,'native_output':capture.getvalue(),'source':str(home),'target':str(target)};records.append(rec);(R/f'raw/{label}-hermes.json').write_text(json.dumps(records,indent=2));print(json.dumps({k:rec[k]for k in['sample','backup_ms','restore_ms','correct_files']}),flush=True)
