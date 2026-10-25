// Evaluator operator transport. Uses WebSocket and the public authenticated
// protocol; it advertises an approval inbox and records events, never resolves one.
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire('/runtime/openclaw/node_modules/openclaw/package.json');
const WebSocket=require('ws');
const client=new WebSocket('ws://127.0.0.1:18789');
client.on('message',raw=>{
 const event=JSON.parse(raw.toString());
 fs.appendFileSync('/state/approval-observer-events.jsonl',JSON.stringify(event)+'\n');
 if(event.type==='event' && event.event==='connect.challenge')client.send(JSON.stringify({type:'req',id:'approval-inbox-connect',method:'connect',params:{minProtocol:4,maxProtocol:4,client:{id:'cli',displayName:'Evaluation approval inbox',version:'2026.10.6',platform:'linux',mode:'cli'},caps:['exec-approvals'],role:'operator',scopes:['operator.admin','operator.approvals'],auth:{token:'synthetic-evaluation-token'}}}));
 if(event.type==='res' && event.id==='approval-inbox-connect'){
  if(!event.ok){console.error(JSON.stringify(event));client.close();return;}
  fs.writeFileSync('/state/approval-observer-ready.json',JSON.stringify({connected:true,hello:event.payload}));
 }
 if(event.type==='res' && event.id?.startsWith('operator-rpc-')){
  const responsePath='/state/'+event.id+'-response.json';
  fs.writeFileSync(responsePath+'.tmp',JSON.stringify(event));
  fs.renameSync(responsePath+'.tmp',responsePath);
 }
});
let lastRequest='';
setInterval(()=>{
 const path='/state/approval-rpc-request.json';
 if(!fs.existsSync(path)||client.readyState!==WebSocket.OPEN)return;
 try{const req=JSON.parse(fs.readFileSync(path,'utf8'));if(req.id===lastRequest)return;lastRequest=req.id;client.send(JSON.stringify(req));}catch(error){console.error(String(error));}
},50);
client.on('error',error=>console.error(String(error)));
process.on('SIGTERM',()=>{client.close();process.exit(0);});
setTimeout(()=>{client.close();process.exit(0);},180000);
