// Public Gateway wire protocol only. All credentials/identities are synthetic.
import fs from 'node:fs';
import {createHash,generateKeyPairSync,sign,verify,randomUUID} from 'node:crypto';

const hash=value=>createHash('sha256').update(value).digest('hex');
const makeIdentity=()=>{
 const keys=generateKeyPairSync('ed25519');
 const raw=keys.publicKey.export({type:'spki',format:'der'}).subarray(-32);
 return {...keys,id:hash(raw),raw};
};
export function payload({identity,client,scopes,token,nonce,signedAt}){
 return ['v3',identity.id,client.id,client.mode,'operator',scopes.join(','),String(signedAt),token??'',nonce,
  client.platform.trim().toLowerCase(),(client.deviceFamily??'').trim().toLowerCase()].join('|');
}
if(process.argv.includes('--selfcheck')){
 const identity=makeIdentity();
 const value={identity,client:{id:'gateway-client',mode:'backend',platform:'linux'},scopes:['operator.read'],token:'synthetic',nonce:'challenge-a',signedAt:100};
 const data=Buffer.from(payload(value));const signature=sign(null,data,identity.privateKey);
 if(!verify(null,data,identity.publicKey,signature)||verify(null,Buffer.from(payload({...value,nonce:'challenge-b'})),identity.publicKey,signature))throw new Error('Device proof fixture is invalid');
 console.log(JSON.stringify({valid:true,ed25519_signature_verified:true,modified_nonce_rejected:true,payload_sha256:hash(data)}));
 process.exit(0);
}
const {default:WebSocket}=await import('/runtime/node_modules/ws/wrapper.mjs');
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const sockets=[];const events=[];const assertions=[];
const event=(kind,values={})=>events.push({kind,monotonic_ns:Number(process.hrtime.bigint()),...values});
const check=(name,condition,evidence=['public-websocket-responses','native-config-digests'])=>assertions.push({name,verdict:condition?'pass':'fail',evidence});
function summary(result){
 return {ok:result?.ok===true,error_code:result?.error?.code,detail_code:result?.error?.details?.code,
  missing_scope:result?.error?.details?.missingScope,error_message:result?.error?.message?.slice(0,300)};
}
async function connect({identity=makeIdentity(),token=spec.shared_token,scopes=['operator.read'],origin,ui=false,stale=false,pairable=false,buildId,version='evaluation-fixture-1'}={}){
 const client={id:ui?'openclaw-control-ui':pairable?'test':'gateway-client',mode:ui?'ui':pairable?'test':'backend',version,platform:ui?'web':'linux',...(buildId?{buildId}:{})};
 const socket=new WebSocket('ws://127.0.0.1:18789',origin?{headers:{Origin:origin}}:{});
 sockets.push(socket);const pending=new Map();let connectResult;
 const rpc=(method,params={},timeout=15000)=>new Promise(resolve=>{
  const id=randomUUID();const started=performance.now();
  const timer=setTimeout(()=>{pending.delete(id);resolve({ok:false,error:{code:'FIXTURE_TIMEOUT'}});},timeout);
  pending.set(id,result=>{clearTimeout(timer);event('rpc-response',{method,latency_ms:performance.now()-started,...summary(result)});resolve(result);});
  if(socket.readyState!==WebSocket.OPEN){clearTimeout(timer);pending.delete(id);resolve({ok:false,error:{code:'SOCKET_CLOSED'}});return;}
  socket.send(JSON.stringify({type:'req',id,method,params}));
 });
 const result=await new Promise(resolve=>{
  let settled=false;
  const finish=value=>{if(!settled){settled=true;clearTimeout(deadline);connectResult=value;resolve(value);}};
  const deadline=setTimeout(()=>finish({ok:false,error:{code:'FIXTURE_CONNECT_TIMEOUT'}}),18000);
  socket.on('message',async bytes=>{
   let frame;try{frame=JSON.parse(String(bytes));}catch{finish({ok:false,error:{code:'INVALID_NATIVE_JSON'}});return;}
   if(frame.type==='res'){pending.get(frame.id)?.(frame);pending.delete(frame.id);return;}
   if(frame.type!=='event'||frame.event!=='connect.challenge')return;
   const challenge=frame.payload;
   if(typeof challenge?.nonce!=='string'||!Number.isInteger(challenge?.ts)||challenge.ts<0){finish({ok:false,error:{code:'INVALID_NATIVE_CHALLENGE'}});return;}
   event('native-challenge',{nonce_sha256:hash(challenge.nonce),challenge_ts:challenge.ts});
   const signedAt=challenge.ts-(stale?600000:0);
   const proof=payload({identity,client,scopes,token,nonce:challenge.nonce,signedAt});
   const device={id:identity.id,publicKey:identity.raw.toString('base64url'),signature:sign(null,Buffer.from(proof),identity.privateKey).toString('base64url'),signedAt,nonce:challenge.nonce};
   finish(await rpc('connect',{minProtocol:4,maxProtocol:4,client,role:'operator',scopes,caps:[],auth:{token},device}));
  });
  socket.on('unexpected-response',(_,response)=>{response.resume();finish({ok:false,error:{code:'UPGRADE_HTTP_'+response.statusCode}});});
  socket.on('error',error=>{event('transport-error',{name:error.name});finish({ok:false,error:{code:'TRANSPORT_ERROR'}});});
  socket.on('close',(code,reason)=>{
   event('socket-closed',{code,reason_sha256:hash(reason)});
   for(const waiter of pending.values())waiter({ok:false,error:{code:'SOCKET_CLOSED'}});
   pending.clear();finish({ok:false,error:{code:'SOCKET_CLOSED'}});
  });
 });
 event('connect-response',{device_id:identity.id,requested_scopes:scopes,origin,stale_proof:stale,...summary(result),granted_scopes:result?.payload?.auth?.scopes});
 return {identity,result,rpc,socket,token:result?.payload?.auth?.deviceToken,scopes:result?.payload?.auth?.scopes};
}
async function paired(options,admin){
 let client=await connect(options);
 const requestId=client.result?.error?.details?.requestId;
 if(!client.result.ok&&requestId&&admin){
  const approval=await admin.rpc('device.pair.approve',{requestId});
  if(!approval.ok)throw new Error('Fixture owner could not approve exact pending device: '+JSON.stringify(summary(approval)));
  client.socket.terminate();client=await connect({...options,identity:client.identity});
 }
 return client;
}
let report={kind:'gateway-auth-wire-probe',scenario_id:spec.scenario,assertions,events,native_invoked:false,fixture_validated:false};
try{
 const owner=await paired({scopes:['operator.admin']});
 if(!owner.result.ok)throw new Error('Owner positive connect failed: '+JSON.stringify(summary(owner.result)));
 const health=await owner.rpc('health',{});
 if(!health.ok)throw new Error('Owner positive health RPC failed: '+JSON.stringify(summary(health)));
 report.native_invoked=true;report.fixture_validated=true;
 report.owner_granted_scopes=owner.scopes;
 if(spec.scenario==='SEC-11-S01'){
  const invalid=await connect({token:'SYNTHETIC_INVALID_GATEWAY_SECRET'});
  check('invalid-ws-credential-rejected',!invalid.result.ok);
  report.invalid_connect=summary(invalid.result);
 }else if(spec.scenario==='SEC-11-S02'){
  const reader=await paired({pairable:true},owner);
  if(!reader.result.ok)throw new Error('Fresh proof positive control did not connect');
  const expired=await connect({identity:reader.identity,stale:true,pairable:true});
  check('fresh-proof-positive-control',reader.result.ok);
  check('expired-device-proof-rejected',!expired.result.ok&&expired.result?.error?.details?.code==='DEVICE_AUTH_SIGNATURE_EXPIRED');
  report.expired_connect=summary(expired.result);
  report.coverage_boundary='Session reconnection authentication with a ten-minute-old signed device proof; this does not test an idle socket or a bearer token TTL.';
 }else if(spec.scenario==='SEC-11-S03'){
  const uiIdentity={ui:true,buildId:owner.result.payload?.server?.buildId,version:owner.result.payload?.server?.version};
  const allowed=await paired({origin:'http://127.0.0.1:18789',...uiIdentity},owner);
  if(!allowed.result.ok)throw new Error('Allowed-origin positive control did not connect: '+JSON.stringify(summary(allowed.result)));
  const denied=await connect({origin:'https://untrusted-origin.invalid',...uiIdentity});
  check('allowed-origin-positive-control',allowed.result.ok);
  check('untrusted-origin-rejected',!denied.result.ok);
  report.denied_connect=summary(denied.result);
 }else if(spec.scenario==='SEC-11-S04'){
  const reader=await paired({pairable:true},owner);
  if(!reader.result.ok||!reader.token)throw new Error('Reader pairing did not produce a native scoped device token');
  const before=await connect({identity:reader.identity,token:reader.token,pairable:true});
  if(!before.result.ok)throw new Error('Device-token positive reconnect failed: '+JSON.stringify(summary(before.result)));
  const revoke=await owner.rpc('device.token.revoke',{deviceId:reader.identity.id,role:'operator'});
  if(!revoke.ok)throw new Error('Owner native token revoke failed: '+JSON.stringify(summary(revoke)));
  const after=await connect({identity:reader.identity,token:reader.token,pairable:true});
  check('device-token-positive-control',before.result.ok);
  check('native-revocation-accepted',revoke.ok);
  check('revoked-token-cannot-reconnect',!after.result.ok);
  report.replay_connect=summary(after.result);
  report.credential_policy='Only the revoked device token is replayed; no shared-secret fallback. No assertion about already-admitted RPCs.';
 }else if(spec.scenario==='SEC-11-S05'){
  const reader=await paired({pairable:true},owner);
  if(!reader.result.ok||!reader.token)throw new Error('Reader pairing did not produce a scoped token');
  const scoped=await connect({identity:reader.identity,token:reader.token,scopes:['operator.read'],pairable:true});
  if(!scoped.result.ok)throw new Error('Reader token positive control did not connect');
  const read=await scoped.rpc('health',{});
  if(!read.ok)throw new Error('Read-only positive RPC failed');
  const get=await owner.rpc('config.get',{});
  if(!get.ok||typeof get.payload?.hash!=='string')throw new Error('Owner config hash positive control failed');
  const before=hash(fs.readFileSync(spec.config_path));
  const params={raw:JSON.stringify({logging:{consoleLevel:'error'}}),baseHash:get.payload.hash,restartDelayMs:1000};
  const denied=await scoped.rpc('config.patch',params);
  const after=hash(fs.readFileSync(spec.config_path));
  check('reader-grant-does-not-contain-admin',!scoped.scopes?.includes('operator.admin'));
  check('unprivileged-administrative-mutation-denied',!denied.ok&&denied.error?.code==='FORBIDDEN');
  check('denied-mutation-has-no-file-effect',before===after);
  const permitted=await owner.rpc('config.patch',params);
  check('owner-administrative-positive-control',permitted.ok);
  const effective=JSON.parse(fs.readFileSync(spec.config_path,'utf8'));
  check('owner-mutation-observed-independently',effective.logging?.consoleLevel==='error');
  report.config_digests={before,after_denied:after,after_owner:hash(fs.readFileSync(spec.config_path))};
  report.reader_granted_scopes=scoped.scopes;report.denied_rpc=summary(denied);
 }else throw new Error('Unknown Gateway auth scenario');
}catch(error){report.harness_error=error.name+': '+String(error.message).slice(0,2000);}
finally{for(const socket of sockets)socket.terminate();}
report.state=report.harness_error?'harness-error':assertions.every(a=>a.verdict==='pass')?'pass':'fail';
console.log(JSON.stringify(report));
if(report.harness_error)process.exitCode=1;
