import hashlib,json,shutil,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for framework in ['openclaw','hermes']:
    target=R/'runtime'/('backup-source-'+framework);shutil.copytree(R/'runtime'/framework,target,dirs_exist_ok=True)
    # Use SQLite's backup API to make each copied native database self-contained.
    for original in (R/'runtime'/framework).rglob('*'):
        if original.suffix in ['.db','.sqlite','.sqlite3']and original.is_file():
            destination=target/original.relative_to(R/'runtime'/framework)
            try:
                source=sqlite3.connect('file:'+str(original)+'?mode=ro',uri=True);dest=sqlite3.connect(destination);source.backup(dest);dest.close();source.close()
                for suffix in ['-wal','-shm']:
                    sidecar=Path(str(destination)+suffix)
                    if sidecar.exists():sidecar.unlink()
            except sqlite3.Error:pass
    files=target/'portable-fixture';files.mkdir(exist_ok=True);manifest={}
    for i in range(64):
        content=hashlib.shake_256(f'nonfunctional-portable-{i}'.encode()).digest(32768);name=f'file-{i:03}.bin';(files/name).write_bytes(content);manifest[name]=hashlib.sha256(content).hexdigest()
    (R/f'results/backup-manifest-{framework}.json').write_text(json.dumps(manifest))
print('Prepared two isolated native state copies with identical 64-file, 2 MiB test data.')
