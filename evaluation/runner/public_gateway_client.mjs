// Public Gateway wire helper, derived from the validated synthetic auth probe.
import {createHash,generateKeyPairSync,sign,randomUUID} from 'node:crypto';
const hash=value=>createHash('sha256').update(value).digest('hex');
const makeIdentity=()=>{
 const keys=generateKeyPairSync('ed25519');
 const raw=keys.publicKey.export({type:'spki',format:'der'}).subarray(-32);
 return {...keys,id:hash(raw),raw};
};
function payload({identity,client,scopes,token,nonce,signedAt}){
 return ['v3',identity.id,client.id,client.mode,'operator',scopes.join(','),String(signedAt),token??'',nonce,
  client.platform.trim().toLowerCase(),(client.deviceFamily??'').trim().toLowerCase()].join('|');
}

export async function gatewayClient(spec){
const {default:WebSocket}=await import('/runtime/node_modules/ws/wrapper.mjs');

const sockets=[];const events=[];const assertions=[];
const event=(kind,values={})=>events.push({kind,monotonic_ns:Number(process.hrtime.bigint()),...values});
const check=(name,condition,evidence=['public-websocket-responses','native-config-digests'])=>assertions.push({name,verdict:condition?'pass':'fail',evidence});
function summary(result){
 return {ok:result?.ok===true,error_code:result?.error?.code,detail_code:result?.error?.details?.code,
  missing_scope:result?.error?.details?.missingScope,error_message:result?.error?.message?.slice(0,300)};
}
async function connect({identity=makeIdentity(),token=spec.shared_token,scopes=['operator.read'],origin,ui=false,stale=false,pairable=false,buildId,version='evaluation-fixture-1',port=18789}={}){
 if(![18789,18790].includes(port))throw new Error('Only the owned loopback Gateway or admission proxy is permitted');
 const client={id:ui?'openclaw-control-ui':pairable?'test':'gateway-client',mode:ui?'ui':pairable?'test':'backend',version,platform:ui?'web':'linux',...(buildId?{buildId}:{})};
 const socket=new WebSocket('ws://127.0.0.1:'+port,origin?{headers:{Origin:origin}}:{});
 sockets.push(socket);const pending=new Map();let connectResult;
 const rpc=(method,params={},timeout=15000)=>new Promise(resolve=>{
  const id=randomUUID();const started=performance.now();
  const timer=setTimeout(()=>{pending.delete(id);resolve({ok:false,error:{code:'FIXTURE_TIMEOUT'}});},timeout);
  pending.set(id,result=>{clearTimeout(timer);event('rpc-response',{method,latency_ms:performance.now()-started,...summary(result)});resolve(result);});
  if(socket.readyState!==WebSocket.OPEN){clearTimeout(timer);pending.delete(id);resolve({ok:false,error:{code:'SOCKET_CLOSED'}});return;}
  socket.send(JSON.stringify({type:'req',id,method,params}),error=>{
   if(!error)event('rpc-request-written',{method,request_id:id});
  });
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

return {connect,paired,events,close(){for(const socket of sockets)socket.terminate();}};
}
