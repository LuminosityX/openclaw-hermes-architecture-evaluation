import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=path.resolve(import.meta.dirname,'..'), src=path.join(root,'sources/openclaw');
const imp=async p=>import(pathToFileURL(path.join(src,p)));
const out={};
function check(row,name,actual,expected){(out[row]??=[]).push({name,actual,expected,passed:JSON.stringify(actual)===JSON.stringify(expected)});}
const {buildAgentPeerSessionKey:key,resolveThreadSessionKeys:thread}=await imp('src/routing/session-key.ts');
const base={agentId:'bench',channel:'telegram',accountId:'bot-a',peerKind:'direct',peerId:'user-a',dmScope:'per-account-channel-peer'};
const k=x=>key({...base,...x});
check(1,'repeat_same_event',k({})===k({}),true);
for(const [field,value] of [['agentId','other'],['channel','discord'],['accountId','bot-b'],['peerId','user-b'],['peerKind','group']])check(1,`isolate_${field}`,k({})!==k({[field]:value}),true);
check(1,'group_chat_isolation',k({peerKind:'group',peerId:'room-a'})!==k({peerKind:'group',peerId:'room-b'}),true);
check(1,'group_channel_isolation',k({peerKind:'group'})!==k({peerKind:'group',channel:'discord'}),true);
check(1,'explicit_main_scope_shared',k({dmScope:'main'})===k({dmScope:'main',peerId:'user-b'}),true);
check(1,'per_peer_scope_ignores_channel',k({dmScope:'per-peer'})===k({dmScope:'per-peer',channel:'discord'}),true);
for(const id of ['topic-a','topic-b'])check(1,`thread_stable_${id}`,thread({baseSessionKey:k({peerKind:'group'}),threadId:id}).sessionKey===thread({baseSessionKey:k({peerKind:'group'}),threadId:id}).sessionKey,true);
check(1,'thread_isolation',thread({baseSessionKey:k({peerKind:'group'}),threadId:'topic-a'}).sessionKey!==thread({baseSessionKey:k({peerKind:'group'}),threadId:'topic-b'}).sessionKey,true);
const {resolveChannelIngressState}=await imp('src/channels/message-access/state.ts');
const {decideChannelIngress}=await imp('src/channels/message-access/decision.ts');
const {defineStableChannelIngressIdentity,createIdentityAdapter,createIdentitySubject}=await imp('src/channels/message-access/runtime-identity.ts');
const identity=defineStableChannelIngressIdentity({channelId:'telegram',label:'bench'});
const authCases=[{list:['alice'],user:'alice',allow:true},{list:['alice'],user:'bob',allow:false},{list:[],user:'alice',allow:false},{list:['*'],user:'bob',allow:true},{list:['alice','bob'],user:'bob',allow:true},{list:['alice','bob'],user:'carol',allow:false},{list:['alice'],user:'Alice',allow:false},{list:['123'],user:'123',allow:true},{list:['123'],user:'1234',allow:false},{list:['alice','alice'],user:'alice',allow:true},{list:['a:b'],user:'a:b',allow:true},{list:['a:b'],user:'a',allow:false}];
for(const [i,c] of authCases.entries()){
 const state=await resolveChannelIngressState({channelId:'telegram',accountId:'bench',subject:createIdentitySubject(identity,{stableId:c.user}),conversation:{kind:'direct',id:'chat'},adapter:createIdentityAdapter(identity),event:{kind:'message',authMode:'inbound',mayPair:false},allowlists:{dm:c.list}});
 const result=decideChannelIngress(state,{dmPolicy:'allowlist',groupPolicy:'disabled'});
 check(3,`allowlist_${i}`,result.admission==='dispatch',c.allow);
}
const {resolveAgentWorkspaceDir}=await imp('src/agents/agent-scope-config.ts');
const {resolveSandboxInputPath}=await imp('src/agents/sandbox-paths.ts');
const work=path.join(root,'fixtures/extended-controls/workspaces');
const entries=Object.fromEntries(['a','b'].map(id=>[id,{workspace:path.join(work,id)}]));
for(const id of ['a','b']){
 fs.mkdirSync(entries[id].workspace,{recursive:true});
 const cwd=resolveAgentWorkspaceDir({agents:{entries}},id);
 for(const rel of ['same.txt','sub/file.txt','with space.txt','中文.txt','sub/../normalized.txt']){
  check(4,`${id}/${rel}`,resolveSandboxInputPath(rel,cwd),path.resolve(entries[id].workspace,rel));
 }
}
const {parseRetryAfterErrorSeconds}=await imp('packages/ai/src/internal/retry-after.ts');
for(const [i,c] of [{headers:{'retry-after':'0'},want:null},{headers:{'retry-after':'1'},want:1},{headers:{'Retry-After':'30'},want:30},{headers:{'retry-after':' 4 '},want:4},{headers:{'retry-after':8},want:8},{headers:{'retry-after':'120'},want:120},{headers:{},want:null},{headers:{'retry-after':'garbage'},want:null},{headers:{'retry-after':''},want:null},{headers:{'unrelated':'8'},want:null},{headers:{'retry-after':'60'},want:60},{headers:{'retry-after':'3600'},want:3600}].entries()){
 const wait=parseRetryAfterErrorSeconds({response:{headers:c.headers}});check(17,`retry_after_${i}`,wait>0?wait:null,c.want);
}
const {evaluateSystemRunPolicy}=await imp('src/node-host/exec-policy.ts');
for(const [i,variant] of [{},{approved:true},{approvalDecision:'allow-once'},{approvalDecision:'allow-always'},{durableApprovalSatisfied:true},{ask:'off'},{ask:'always'},{allowlistSatisfied:true},{analysisOk:false},{isWindows:true,cmdInvocation:true,shellWrapperInvocation:true},{approved:true,durableApprovalSatisfied:true},{approvalDecision:'allow-always',ask:'off',allowlistSatisfied:true}].entries()){
 const decision=evaluateSystemRunPolicy({security:'deny',ask:'on-miss',analysisOk:true,allowlistSatisfied:false,approvalDecision:null,isWindows:false,cmdInvocation:false,shellWrapperInvocation:false,...variant});
 check(19,`explicit_deny_precedence_${i}`,decision.allowed,false);
}
const outputPath=path.join(root,'raw/extended-controls/openclaw.json');
const existing=fs.existsSync(outputPath)?JSON.parse(fs.readFileSync(outputPath)):{};
fs.writeFileSync(outputPath,JSON.stringify({...existing,...out},null,2));
fs.writeFileSync(path.join(root,'raw/extended-controls/openclaw-retry-compat.json'),JSON.stringify({fractional_seconds:parseRetryAfterErrorSeconds({response:{headers:{'retry-after':'1.5'}}})??null,negative_seconds:parseRetryAfterErrorSeconds({response:{headers:{'retry-after':'-1'}}})??null,note:'Compatibility observations only; not scored.'},null,2));
console.log(JSON.stringify(Object.fromEntries(Object.entries(out).map(([k,v])=>[k,{passed:v.filter(x=>x.passed).length,total:v.length}]))));
