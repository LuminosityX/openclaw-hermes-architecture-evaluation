import contextvars,copy,itertools,time,pluggy
Original=pluggy.PluginManager
class Golden(Original):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self._subs=[];self._stack=contextvars.ContextVar('stack',default=());self._suppress=contextvars.ContextVar('suppress',default=False);self._seq=itertools.count()
 def enable_plugin_tracing(self,cb):
  key=object();self._subs.append((key,cb))
  def undo():self._subs[:]=[x for x in self._subs if x[0] is not key]
  return undo
 def _hookexec(self,hook_name,methods,kwargs,firstresult):
  if not self._subs or self._suppress.get():return super()._hookexec(hook_name,methods,kwargs,firstresult)
  proxies=[]
  for h in methods:
   x=copy.copy(h)
   def wrapped(*args,_fn=h.function,_wrapper=h.wrapper or h.hookwrapper,_plugin=h.plugin_name,**kw):
    cid=str(next(self._seq));stack=self._stack.get();parent=stack[-1] if stack else None;token=self._stack.set(stack+(cid,));start=time.monotonic_ns();subs=list(self._subs)
    def emit(phase,err=None):
     e=dict(call_id=cid,parent_call_id=parent,hook_name=hook_name,plugin_name=_plugin,phase=phase,duration_ns=0 if phase=='start' else time.monotonic_ns()-start,exception_type=type(err).__name__ if err else None)
     for _,cb in subs:
      t=self._suppress.set(True)
      try:cb(dict(e))
      except Exception:pass
      finally:self._suppress.reset(t)
    emit('start')
    try:r=_fn(*args,**kw)
    except BaseException as e:emit('finish',e);self._stack.reset(token);raise
    if not _wrapper:emit('finish');self._stack.reset(token);return r
    def gen():
     err=None
     try:return (yield from r)
     except BaseException as e:err=e;raise
     finally:emit('finish',err);self._stack.reset(token)
    return gen()
   x.function=wrapped;proxies.append(x)
  return super()._hookexec(hook_name,proxies,kwargs,firstresult)
pluggy.PluginManager=Golden
