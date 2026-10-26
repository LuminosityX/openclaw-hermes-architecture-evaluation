// Byte-preserving loopback frame proxy; only the chosen native request/ACK is held.
import fs from 'node:fs';
import {createHash,generateKeyPairSync,createPrivateKey,createPublicKey} from 'node:crypto';
import {gatewayClient} from './public_gateway_client.mjs';
const {default:WebSocket,WebSocketServer}=await import('/runtime/node_modules/ws/wrapper.mjs');
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const hash=value=>createHash('sha256').update(value).digest('hex');
let finish;const done=new Promise(resolve=>{finish=resolve;});process.stdin.on('data',finish);const timer=setTimeout(finish,80000);
const proxySockets=[];let server;const report={responses:[]};
const observe=async(kind,values={})=>{
 const response=await fetch('http://127.0.0.1:18080/admission-wire',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,...values})});
 if(!response.ok)throw new Error('Owned admission observer failed');
};
if(!fs.existsSync(spec.identity_path)){
 const pair=generateKeyPairSync('ed25519');
 fs.writeFileSync(spec.identity_path,JSON.stringify({private:pair.privateKey.export({type:'pkcs8',format:'pem'}),public:pair.publicKey.export({type:'spki',format:'pem'})}),{mode:0o600});
}
const saved=JSON.parse(fs.readFileSync(spec.identity_path,'utf8'));const publicKey=createPublicKey(saved.public);const raw=publicKey.export({type:'spki',format:'der'}).subarray(-32);
const identity={publicKey,privateKey:createPrivateKey(saved.private),raw,id:hash(raw)};
if(['before-append','before-client-ack'].includes(spec.mode)){
 server=new WebSocketServer({host:'127.0.0.1',port:18790,maxPayload:1024*1024});
 server.on('connection',downstream=>{
  const upstream=new WebSocket('ws://127.0.0.1:18789');proxySockets.push(downstream,upstream);let targetId;
  const forward=(socket,data)=>{if(socket.readyState===WebSocket.OPEN)socket.send(data);};
  downstream.on('message',async bytes=>{
   let frame;try{frame=JSON.parse(String(bytes));}catch{downstream.terminate();return;}
   if(frame.type==='req'&&frame.method==='chat.send'&&frame.params?.idempotencyKey===spec.idempotency_key){
    targetId=frame.id;
    if(spec.mode==='before-append')await observe('target-request-held-before-forwarding',{request_sha256:hash(bytes),request_id:targetId});
   }
   if(upstream.readyState===WebSocket.CONNECTING)await new Promise(resolve=>upstream.once('open',resolve));
   if(frame.id===targetId)await observe('target-request-forward-attempt',{upstream_open:upstream.readyState===WebSocket.OPEN});
   forward(upstream,bytes);
  });
  upstream.on('message',async bytes=>{
   let frame;try{frame=JSON.parse(String(bytes));}catch{upstream.terminate();return;}
   if(frame.type==='res'&&frame.id===targetId&&spec.mode==='before-client-ack')await observe('native-ack-held-before-client',{native_response:frame,response_sha256:hash(bytes)});
   forward(downstream,bytes);
  });
  upstream.on('error',()=>downstream.terminate());downstream.on('error',()=>upstream.terminate());
  upstream.on('close',()=>downstream.terminate());downstream.on('close',()=>upstream.terminate());
 });
 await new Promise(resolve=>server.once('listening',resolve));
}
const client=await gatewayClient(spec);
try{
 const bootstrap=await client.paired({scopes:['operator.admin']});
 if(!bootstrap.result.ok)throw new Error('Actual bootstrap owner connection failed');
 const owner=await client.paired({identity,ui:true,origin:'http://127.0.0.1:18789',scopes:['operator.admin'],port:server?18790:18789,
  buildId:bootstrap.result.payload.server.buildId,version:bootstrap.result.payload.server.version},bootstrap);
 if(!owner.result.ok)throw new Error('Actual Control UI wire owner connection failed: '+JSON.stringify(owner.result));
 const health=await owner.rpc('health',{});if(!health.ok)throw new Error('Actual wire health control failed');
 console.log(JSON.stringify({ready:true}));
 const response=await owner.rpc('chat.send',{sessionKey:spec.session_key,message:'Execute the deterministic operation for '+spec.token,idempotencyKey:spec.idempotency_key},25000);
 report.responses.push(response);await observe('actual-client-rpc-result',{native_response:response});
 await done;
}catch(error){report.harness_error=error.message;await observe('wire-error',{error:error.message});}
finally{clearTimeout(timer);client.close();for(const socket of proxySockets)socket.terminate();server?.close();}
console.log(JSON.stringify({...report,events:client.events}));
if(report.harness_error)process.exitCode=1;
