// Actual native UI decision, with a separately observed pre-dispatch inode gate.
import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const client=await gatewayClient(spec);const report={approvals:[]};
let finish;let selectedUi;const done=new Promise(resolve=>{finish=resolve;});
const timer=setTimeout(finish,90000);
const observe=async(kind,record)=>{
 const response=await fetch('http://127.0.0.1:18080/revocation-observer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,...record})});
 if(!response.ok)throw new Error('Owned revocation observer failed');
};
process.stdin.on('data',async bytes=>{
 for(const command of String(bytes).trim().split('\n')){
  if(command!=='revoke'){finish();continue;}
  try{
   const start=Number(process.hrtime.bigint());
   const pending=selectedUi.rpc('sessions.patch',{key:spec.session_key,permissionMode:'read-only'});
   let written;
   for(let i=0;i<100&&!written;i++){
    written=client.events.find(e=>e.kind==='rpc-request-written'&&e.method==='sessions.patch'&&e.monotonic_ns>=start);
    if(!written)await new Promise(resolve=>setTimeout(resolve,5));
   }
   if(written)report.revocation_request={id:written.request_id,method:'sessions.patch',params:{key:spec.session_key,permissionMode:'read-only'}};
   await observe('actual-revocation-request-written',{written});
   const result=await pending;report.revocation=result;await observe('actual-revocation-response',{native_response:result});
  }catch(error){await observe('observer-error',{error:error.message});}
 }
});
try{
 const owner=await client.paired({scopes:['operator.admin']});if(!owner.result.ok)throw new Error('Owner auth failed');
 const ui=await client.paired({ui:true,origin:'http://127.0.0.1:18789',scopes:['operator.admin'],buildId:owner.result.payload.server.buildId,version:owner.result.payload.server.version},owner);
 if(!ui.result.ok)throw new Error('Native UI approval connection failed');
 selectedUi=ui;
 ui.socket.on('message',async bytes=>{
  let frame;try{frame=JSON.parse(String(bytes));}catch{return;}
  if(frame.type!=='event'||frame.event!=='exec.approval.requested'||!JSON.stringify(frame.payload).includes(spec.command_marker))return;
  const record={requested:frame.payload};report.approvals.push(record);
  try{
   await observe('arm-before-native-decision',record);
   record.resolution=await ui.rpc('exec.approval.resolve',{id:frame.payload.id,decision:'allow-once'});
   await observe('actual-native-decision-returned',record);
   record.terminal=await ui.rpc('approval.get',{id:frame.payload.id});
   record.execProjection=await ui.rpc('exec.approval.get',{id:frame.payload.id});
   await observe('actual-native-terminal-observed',record);
  }catch(error){record.error=error.message;await observe('observer-error',record);}
 });
 console.log(JSON.stringify({ready:true}));await done;
 report.history=await owner.rpc('approval.history',{kind:'exec',limit:30});
}catch(error){report.harness_error=error.message;}
finally{clearTimeout(timer);client.close();}
console.log(JSON.stringify({...report,events:client.events}));
if(report.harness_error)process.exitCode=1;
