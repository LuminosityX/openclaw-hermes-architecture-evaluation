"""Read original native canonical transcript, including native Zstandard records.
No claim that this exhausts every possible product recovery surface.
"""
import ctypes,hashlib,json,sqlite3
from runtime import R,save
from mcp_contract_fixture import LARGE

def main():
 lib=ctypes.CDLL('libzstd.so.1');lib.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];lib.ZSTD_decompress.restype=ctypes.c_size_t;lib.ZSTD_isError.argtypes=[ctypes.c_size_t];lib.ZSTD_isError.restype=ctypes.c_uint;rows=[]
 for transport in ['stdio','streamable-http']:
  for unit in range(1,4):
   root=R/'runs-mcp-contracts'/transport/f'u{unit}'/'openclaw';hits=[];counts=dict(decoded=0,errors=0);other=[]
   for p in (root/'state').rglob('*.sqlite'):
    c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);tables={x[0] for x in c.execute("select name from sqlite_master where type='table'")}
    if 'transcript_events' in tables:
     for session,seq,plain,blob,size in c.execute('select session_id,seq,event_json,event_zstd,event_utf8_bytes from transcript_events'):
      if blob:
       dest=ctypes.create_string_buffer(size);source=ctypes.create_string_buffer(blob);n=lib.ZSTD_decompress(dest,size,source,len(blob))
       if lib.ZSTD_isError(n):counts['errors']+=1;continue
       raw=dest.raw[:n]
      elif plain:raw=plain.encode()
      else:continue
      counts['decoded']+=1
      if b'MCP_LARGE_BEGIN_' in raw:
       text=raw.decode();obj=json.loads(text);msg=obj.get('message',{});blocks=msg.get('content',[]);full=any(isinstance(x,dict) and LARGE==x.get('text') for x in blocks) if isinstance(blocks,list) else LARGE==blocks;hits.append(dict(database=str(p.relative_to(R)),session=session,seq=seq,role=msg.get('role'),native_event_bytes=len(raw),full_large_content_exact=full,tail_present='_MCP_LARGE_END_中文' in text,event_sha256=hashlib.sha256(raw).hexdigest()))
    for t in ['capture_blobs','plugin_blob_entries','session_transcript_cold_archives','session_transcript_archives','trajectory_runtime_events']:
     if t in tables:
      row=dict(database=str(p.relative_to(R)),table=t,rows=c.execute('select count(*) from '+t).fetchone()[0])
      if t=='trajectory_runtime_events':row.update(tail_hits=c.execute('select count(*) from '+t+' where instr(event_json,?)>0',('_MCP_LARGE_END_',)).fetchone()[0])
      other.append(row)
    c.close()
   rows.append(dict(unit=unit,transport=transport,counts=counts,large_native_events=hits,other_native_stores=other))
 save(R/'results/mcp-original-storage-audit.json',dict(rows=rows,scope='Read-only canonical transcript including Zstandard blobs, and listed native blob/trajectory/archive tables. Full text in an external evaluator fixture is never counted as a native recovery archive. Alternate supported code-mode routes are outside this particular ordinary-tool-path observation.'))
 print('NATIVE_MCP_STORAGE_AUDIT',len(rows),'profiles, full canonical events',sum(e['full_large_content_exact'] for x in rows for e in x['large_native_events']))
if __name__=='__main__':main()
