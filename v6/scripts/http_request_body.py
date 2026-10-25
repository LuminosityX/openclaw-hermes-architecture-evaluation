"""Read HTTP request bodies, including standard chunked exporter transports."""
def read_body(handler,maximum=64*1024*1024):
 if 'chunked' not in handler.headers.get('Transfer-Encoding','').lower():
  length=int(handler.headers.get('Content-Length','0'))
  if length<0 or length>maximum:raise ValueError('Invalid fixture body length')
  data=handler.rfile.read(length)
  if len(data)!=length:raise EOFError('Incomplete Content-Length body')
  return data
 chunks=[];total=0
 while True:
  line=handler.rfile.readline(65536)
  if not line:raise EOFError('Missing HTTP chunk size')
  size=int(line.split(b';',1)[0].strip(),16)
  if size==0:
   while True:
    trailer=handler.rfile.readline(65536)
    if trailer in [b'\r\n',b'\n',b'']:break
   return b''.join(chunks)
  total+=size
  if size<0 or total>maximum:raise ValueError('HTTP chunked fixture body too large')
  data=handler.rfile.read(size)
  if len(data)!=size:raise EOFError('Incomplete HTTP chunk')
  if handler.rfile.read(2)!=b'\r\n':raise ValueError('Invalid HTTP chunk terminator')
  chunks.append(data)
