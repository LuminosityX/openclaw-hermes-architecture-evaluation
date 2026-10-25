"""Trusted live-row inspection only; external fixture logs are never product audit evidence."""
import json,os,sqlite3
from pathlib import Path

def decision_records(state,identities):
 state=Path(state);records=[]
 for directory,dirs,files in os.walk(state):
  dirs[:]=[x for x in dirs if x not in ['installs','runtime-leases','node_modules','__pycache__','cache','.cache']]
  for name in files:
   path=Path(directory)/name
   if path.suffix not in ['.db','.sqlite','.sqlite3']:continue
   try:
    conn=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    for table, in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '%fts%'"):
     quote='"'+table.replace('"','""')+'"';cursor=conn.execute('SELECT * FROM '+quote);cols=[x[0] for x in cursor.description];matched=[]
     for row in cursor:
      text=str(row)
      found=[i for i in identities if i in text]
      if found:matched.append(dict(ids=found,row={k:v.decode(errors='replace') if isinstance(v,bytes) else v for k,v in zip(cols,row)}))
     if matched:records.append(dict(source=str(path.relative_to(state)),table=table,matches=matched))
    conn.close()
   except sqlite3.Error as ex:records.append(dict(source=str(path.relative_to(state)),error=type(ex).__name__))
 return records
