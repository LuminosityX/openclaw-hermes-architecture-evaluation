import json,sys,threading,time
sys.path.insert(0,'/workspace/project/src')
import pluggy
TASK=sys.argv[1];SEED=int(sys.argv[2]);spec=pluggy.HookspecMarker('bench');impl=pluggy.HookimplMarker('bench')
def atomic():
 out=[]
 for failure in ['signature','history','property']:
  class Specs:
   @spec
   def a_ok(self,value):pass
   @spec
   def z_bad(self,value):pass
  class Hist:
   @spec(historic=True)
   def z_history(self,value):pass
  class Good:
   @impl
   def a_ok(self,value):return value+SEED
  class BadSignature:
   @impl
   def a_ok(self,value):return -999
   @impl
   def z_bad(self,value,unexpected):return value
  class BadHistory:
   @impl
   def a_ok(self,value):return -999
   @impl
   def z_history(self,value):raise RuntimeError('history failure')
  class BadProperty:
   @impl
   def a_ok(self,value):return -999
   @property
   def z_property(self):raise RuntimeError('property failure')
  p=pluggy.PluginManager('bench');p.add_hookspecs(Specs);p.add_hookspecs(Hist);p.register(Good(),name='good');p.hook.z_history.call_historic(kwargs={'value':SEED});bad={'signature':BadSignature,'history':BadHistory,'property':BadProperty}[failure]();error=None
  try:p.register(bad,name='broken')
  except Exception as e:error=type(e).__name__
  row=dict(case=failure,error=error,names=sorted(n for n,_ in p.list_name_plugin()),calls=p.hook.a_ok(value=7),plugin_present=p.get_plugin('broken') is bad)
  try:row['retry_name']=p.register(type('Clean',(),{})(),name='broken')
  except Exception as e:row['retry_error']=type(e).__name__
  out.append(row)
 class BadNew:
  @impl
  def a_unpublished(self):return 5
  @property
  def z_fail(self):raise RuntimeError('discovery failed')
 p=pluggy.PluginManager('bench')
 try:p.register(BadNew(),name='badnew')
 except Exception:pass
 out.append(dict(case='new_relay',relay_left=hasattr(p.hook,'a_unpublished'),names=sorted(n for n,_ in p.list_name_plugin())))
 return out

def tracing():
 rows=[]
 class Specs:
  @spec
  def compute(self,value):pass
  @spec
  def outer(self,value):pass
  @spec
  def inner(self,value):pass
 class P1:
  @impl
  def compute(self,value):return value+1
 class P2:
  @impl
  def compute(self,value):return value*2
 p=pluggy.PluginManager('bench');p.add_hookspecs(Specs);p.register(P1(),name='p1');p.register(P2(),name='p2');a=[];b=[]
 def observer(e):a.append(dict(e));raise RuntimeError('observer failure')
 ua=p.enable_plugin_tracing(observer);ub=p.enable_plugin_tracing(lambda e:b.append(dict(e)));result=p.hook.compute(value=SEED);aa=list(a);bb=list(b);ua();p.hook.compute(value=SEED+1);na=len(a);nb=len(b);ub();ub();p.hook.compute(value=SEED+2)
 rows.append(dict(case='observers',result=result,a=aa,b=bb,after_a=na,after_b=nb,final_b=len(b)))
 p=pluggy.PluginManager('bench');p.add_hookspecs(Specs);events=[]
 class Outer:
  @impl
  def outer(self,value):time.sleep(.001);return sum(p.hook.inner(value=value))+1
 class Inner:
  @impl
  def inner(self,value):return value*3
 p.register(Outer(),name='outer_impl');p.register(Inner(),name='inner_impl');p.enable_plugin_tracing(lambda e:events.append(dict(e)));result=p.hook.outer(value=SEED);rows.append(dict(case='nested',result=result,events=list(events)));events.clear();results=[]
 ts=[threading.Thread(target=lambda v:results.append(p.hook.outer(value=v)),args=(SEED+i,)) for i in range(3)]
 for t in ts:t.start()
 for t in ts:t.join()
 rows.append(dict(case='threads',results=results,events=list(events)))
 class Bad:
  @impl
  def compute(self,value):raise ValueError('business failure')
 p=pluggy.PluginManager('bench');p.add_hookspecs(Specs);p.register(Bad(),name='bad');events=[];p.enable_plugin_tracing(lambda e:events.append(dict(e)));error=None
 try:p.hook.compute(value=SEED)
 except Exception as e:error=type(e).__name__
 rows.append(dict(case='exception',error=error,events=list(events)))
 class Suppress:
  @impl(wrapper=True)
  def compute(self,value):
   try:r=yield
   except ValueError:return ['recovered']
   return r
 p=pluggy.PluginManager('bench');p.add_hookspecs(Specs);p.register(Bad(),name='bad');p.register(Suppress(),name='suppress');events=[];p.enable_plugin_tracing(lambda e:events.append(dict(e)));error=None;result=None
 try:result=p.hook.compute(value=SEED)
 except Exception as e:error=type(e).__name__
 rows.append(dict(case='wrapper',result=result,error=error,events=list(events)))
 class FirstSpec:
  @spec(firstresult=True)
  def first(self,value):pass
 class First:
  @impl
  def first(self,value):return value+9
 class OldWrap:
  @impl(hookwrapper=True)
  def first(self,value):
   r=yield;r.force_result(r.get_result()+2)
 p=pluggy.PluginManager('bench');p.add_hookspecs(FirstSpec);p.register(First(),name='first');p.register(OldWrap(),name='oldwrap');events=[];p.enable_plugin_tracing(lambda e:events.append(dict(e)));rows.append(dict(case='first_legacy',result=p.hook.first(value=SEED),events=list(events)))

 # Independent managers must not share trace ancestry.
 pa=pluggy.PluginManager('bench');pb=pluggy.PluginManager('bench');pa.add_hookspecs(Specs);pb.add_hookspecs(Specs);ea=[];eb=[]
 class CrossA:
  @impl
  def outer(self,value):return sum(pb.hook.inner(value=value))
 class CrossB:
  @impl
  def inner(self,value):return value+19
 pa.register(CrossA(),name='manager_a');pb.register(CrossB(),name='manager_b');pa.enable_plugin_tracing(lambda e:ea.append(dict(e)));pb.enable_plugin_tracing(lambda e:eb.append(dict(e)))
 rows.append(dict(case='manager_isolation',result=pa.hook.outer(value=SEED),a=ea,b=eb))
 # A callback's own hook calls execute but do not recurse into tracing.
 p=pluggy.PluginManager('bench');p.add_hookspecs(Specs);p.register(P1(),name='p1');events=[];once=[False]
 def recursive(e):
  events.append(dict(e))
  if not once[0]:once[0]=True;p.hook.compute(value=0)
 p.enable_plugin_tracing(recursive);result=p.hook.compute(value=SEED)
 rows.append(dict(case='observer_recursion',result=result,events=events))
 return rows
try:out=dict(task=TASK,seed=SEED,observations=atomic() if TASK=='W1' else tracing())
except BaseException as e:out=dict(task=TASK,seed=SEED,probe_error=type(e).__name__,message=str(e))
print(json.dumps(out,ensure_ascii=False))
