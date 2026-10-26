// Actual native UI decision, with a separately observed pre-dispatch inode gate.
import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const client=await gatewayClient(spec);const report={approvals:[]};
let finish;const done=new Promise(resolve=>{finish=resolve;});
const timer=setTimeout(finish,90000);process.stdin.on('data',finish);
const observe=async(kind,record)=>{
 const response=await fetch('http://127.0.0.1:18080/revocation-observer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,...record})});
 if(!response.ok)throw new Error('Owned revocation observer failed');
};
try{
 const owner=await client.paired({scopes:['operator.admin']});if(!owner.result.ok)throw new Error('Owner auth failed');
 const ui=await client.paired({ui:true,origin:'http://127.0.0.1:18789',scopes:['operator.admin'],buildId:owner.result.payload.server.buildId,version:owner.result.payload.server.version},owner);
 if(!ui.result.ok)throw new Error('Native UI approval connection failed');
 ui.socket.on('message',async bytes=>{
  let frame;try{frame=JSON.parse(String(bytes));}catch{return;}
  if(frame.type!=='event'||frame.event!=='exec.approval.requested'||!JSON.stringify(frame.payload).includes(spec.command_marker))return;
  const record={requested:frame.payload};report.approvals.push(record);
  try{
   await observe('arm-before-native-decision',record);
   record.resolution=await ui.rpc('exec.approval.resolve',{id:frame.payload.id,decision:'allow-once'});
   record.terminal=await ui.rpc('approval.get',{id:frame.payload.id});
   record.execProjection=await ui.rpc('exec.approval.get',{id:frame.payload.id});
   await observe('actual-native-decision-returned',record);
  }catch(error){record.error=error.message;await observe('observer-error',record);}
 });
 console.log(JSON.stringify({ready:true}));await done;
 report.history=await owner.rpc('approval.history',{kind:'exec',limit:30});
}catch(error){report.harness_error=error.message;}
finally{clearTimeout(timer);client.close();}
console.log(JSON.stringify({...report,events:client.events}));
if(report.harness_error)process.exitCode=1;
