"""Offline activation using the native verified archive manifest, as its runbook requires."""
import json,shutil
from pathlib import Path
from runtime import save

def activate_openclaw(staging,target_state,target_workspace,record):
 staging=Path(staging);manifests=[]
 for p in staging.rglob('manifest.json'):
  try:d=json.loads(p.read_text())
  except ValueError:continue
  if isinstance(d.get('assets'),list) and all(isinstance(x,dict) and 'sourcePath' in x for x in d['assets']):manifests.append((p,d))
 if len(manifests)!=1:raise RuntimeError('Native archive manifest must be unambiguous before activation')
 manifest,data=manifests[0];assets=data['assets'];activated=[]
 def source(original):
  candidates=[a for a in assets if original==a['sourcePath'] or original.startswith(a['sourcePath'].rstrip('/')+'/')]
  if not candidates:raise RuntimeError('Native manifest does not cover '+original)
  asset=max(candidates,key=lambda a:len(a['sourcePath']));member=Path(asset['archivePath']);container=manifest.parent.parent
  if member.parts and member.parts[0]!=manifest.parent.name:container=manifest.parent
  path=container/member
  relative=original[len(asset['sourcePath']):].lstrip('/')
  if relative:path=path/relative
  if not path.resolve().is_relative_to(staging.resolve()) or not path.exists():raise RuntimeError('Verified manifest asset could not be located safely: '+original)
  return path
 for original,dest in [('/state/openclaw',Path(target_state)/'openclaw'),('/workspace',Path(target_workspace)),('/state/openclaw.json',Path(target_state)/'openclaw.json')]:
  src=source(original);dest.parent.mkdir(parents=True,exist_ok=True)
  if src.is_dir():shutil.copytree(src,dest,dirs_exist_ok=True,symlinks=True)
  else:shutil.copy2(src,dest)
  activated.append(dict(original=original,archive_asset=str(src.relative_to(staging)),target=str(dest)))
 save(record,dict(manifest=str(manifest),manifest_content=data,activated=activated,note='Native backup restore already verified paths and databases. This is the separately documented offline activation, with exact manifest asset mapping.'))
 return activated
