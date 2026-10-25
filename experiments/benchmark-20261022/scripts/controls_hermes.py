import json,os,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
profile=ROOT/'fixtures/extended-controls/hermes-profile'
profile.mkdir(parents=True,exist_ok=True)
(profile/'config.yaml').write_text('approvals:\n  mode: off\n  deny: ["*"]\nterminal:\n  backend: local\n')
os.environ['HERMES_HOME']=str(profile)
os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime')
os.environ['TERMINAL_ENV']='local'
sys.path.insert(0,str(ROOT/'sources/hermes'))
out={}
def check(row,name,actual,expected):out.setdefault(str(row),[]).append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))
from gateway.config import Platform
from gateway.session import SessionSource,build_session_key
base=dict(platform=Platform.TELEGRAM,chat_id='chat-a',user_id='user-a',chat_type='dm')
def key(**kw):
    d={**base,**kw};profile=d.pop('profile','bench');return build_session_key(SessionSource(**d),group_sessions_per_user=False,profile=profile)
check(1,'repeat_same_event',key()==key(),True)
for field,value in [('profile','other'),('platform',Platform.DISCORD),('chat_id','chat-b'),('chat_type','group')]:check(1,'isolate_'+field,key()!=key(**{field:value}),True)
check(1,'dm_without_chat_isolates_user',key(chat_id='',user_id='u1')!=key(chat_id='',user_id='u2'),True)
check(1,'group_chat_isolation',key(chat_type='group',chat_id='g1')!=key(chat_type='group',chat_id='g2'),True)
check(1,'group_channel_isolation',key(chat_type='group')!=key(chat_type='group',platform=Platform.DISCORD),True)
check(1,'group_shared_members',key(chat_type='group')==key(chat_type='group',user_id='user-b'),True)
check(1,'dm_chat_owns_continuity',key()==key(user_id='user-b'),True)
for thread in ['topic-a','topic-b']:check(1,'thread_stable_'+thread,key(chat_type='group',thread_id=thread)==key(chat_type='group',thread_id=thread),True)
check(1,'thread_isolation',key(chat_type='group',thread_id='topic-a')!=key(chat_type='group',thread_id='topic-b'),True)
from gateway.authz_mixin import GatewayAuthorizationMixin
class Gate(GatewayAuthorizationMixin):
    def _adapter_profile_for_source(self,s):return None
    def _chat_scoped_grant(self,*a):return False
    def _pairing_store_for(self,*a):return None
    def _adapter_flag(self,*a):return False
    def _adapter_extra_allowlist_authorizes(self,*a):return False
    def _adapter_resolved_allowlist_ids(self,*a):return set()
g=Gate()
auth=[(['alice'],'alice',True),(['alice'],'bob',False),([],'alice',False),(['*'],'bob',True),(['alice','bob'],'bob',True),(['alice','bob'],'carol',False),(['alice'],'Alice',False),(['123'],'123',True),(['123'],'1234',False),(['alice','alice'],'alice',True),(['a:b'],'a:b',True),(['a:b'],'a',False)]
for i,(lst,user,allow) in enumerate(auth):
    for var in ['GATEWAY_ALLOW_ALL_USERS','TELEGRAM_ALLOW_ALL_USERS','GATEWAY_ALLOWED_USERS']:os.environ.pop(var,None)
    os.environ['TELEGRAM_ALLOWED_USERS']=','.join(lst)
    actual=g._is_user_authorized(SessionSource(platform=Platform.TELEGRAM,chat_id='bench',user_id=user))
    check(3,f'allowlist_{i}',actual,allow)
from tools.terminal_tool import record_session_cwd,clear_session_cwd
from tools.file_tools_paths import _resolve_path_for_task
for task in ['a','b']:
    cwd=ROOT/'fixtures/extended-controls/workspaces'/task;cwd.mkdir(parents=True,exist_ok=True)
    record_session_cwd('controls-'+task,str(cwd))
    for rel in ['same.txt','sub/file.txt','with space.txt','中文.txt','sub/../normalized.txt']:
        check(4,task+'/'+rel,str(_resolve_path_for_task(rel,'controls-'+task)),str((cwd/rel).resolve()))
    clear_session_cwd('controls-'+task)
from agent.retry_utils import provider_retry_after_seconds
retry=[({'retry-after':'0'},None),({'retry-after':'1'},1),({'Retry-After':'30'},30),({'retry-after':' 4 '},4),({'retry-after':8},8),({'retry-after':'120'},120),({},None),({'retry-after':'garbage'},None),({'retry-after':''},None),({'unrelated':'8'},None),({'retry-after':'60'},60),({'retry-after':'3600'},3600)]
class ProviderError(Exception):pass
for i,(headers,want) in enumerate(retry):
    e=ProviderError('synthetic');e.response=SimpleNamespace(headers=headers)
    check(17,f'retry_after_{i}',provider_retry_after_seconds(e),want)
from tools.approval import check_dangerous_command,enable_session_yolo,disable_session_yolo
commands=['echo bench','pwd','true','ls .','cat fixture.txt','python -V','git status','printf bench','env echo bench','sh -c "echo bench"','echo bench && true','echo bench | cat']
for i,command in enumerate(commands):
    actual=check_dangerous_command(command,'local',approval_callback=lambda *a,**k:'once')
    check(19,f'explicit_deny_precedence_{i}',actual['approved'],False)
output_path=ROOT/'raw/extended-controls/hermes.json'
existing=json.loads(output_path.read_text()) if output_path.exists() else {}
output_path.write_text(json.dumps({**existing,**out},ensure_ascii=False,indent=2))
compat={}
for key,value in [('fractional_seconds','1.5'),('negative_seconds','-1')]:
    e=ProviderError('synthetic');e.response=SimpleNamespace(headers={'retry-after':value});compat[key]=provider_retry_after_seconds(e)
compat['note']='Compatibility observations only; not scored.'
(ROOT/'raw/extended-controls/hermes-retry-compat.json').write_text(json.dumps(compat,indent=2))
print(json.dumps({k:dict(passed=sum(x['passed'] for x in v),total=len(v)) for k,v in out.items()}))
