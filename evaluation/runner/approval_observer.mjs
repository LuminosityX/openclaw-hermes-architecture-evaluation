// Native operator approval observation for owned commands only.
import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const client=await gatewayClient(spec);
const report={kind:'native-authorization-observer',approvals:[],native_invoked:false};
let finish;const finished=new Promise(resolve=>{finish=resolve;});
const deadline=setTimeout(finish,90000);
process.stdin.on('data',()=>finish());
try{
 const owner=await client.paired({scopes:['operator.admin']});
 if(!owner.result.ok)throw new Error('Owner connection failed');
 const ui=await client.paired({ui:true,origin:'http://127.0.0.1:18789',scopes:['operator.admin'],buildId:owner.result.payload.server.buildId,version:owner.result.payload.server.version},owner);
 if(!ui.result.ok)throw new Error('Native operator UI approval connection failed');
 report.native_invoked=true;report.reviewer_device_id=ui.identity.id;
 ui.socket.on('message',async bytes=>{
  let frame;try{frame=JSON.parse(String(bytes));}catch{return;}
  if(frame.type!=='event'||frame.event!=='exec.approval.requested'||!JSON.stringify(frame.payload).includes(spec.command_marker))return;
  const approval=frame.payload;
  const observation={native_requested_event:approval,effect_before_decision:fs.existsSync(spec.effect_path),review_received_monotonic_ns:Number(process.hrtime.bigint())};
  report.approvals.push(observation);
  try{
   observation.resolution=await ui.rpc('exec.approval.resolve',{id:approval.id,decision:spec.decision??'deny'});
   observation.native_terminal=await ui.rpc('approval.get',{id:approval.id});
   observation.native_exec_projection=await ui.rpc('exec.approval.get',{id:approval.id});
  }catch(error){observation.observer_error=error.message;}
 });
 console.log(JSON.stringify({kind:'authorization-observer-ready',ready:true}));
 await finished;
 report.native_history=await owner.rpc('approval.history',{limit:100,kind:'exec'});
}catch(error){report.harness_error=error.name+': '+error.message;}
finally{clearTimeout(deadline);client.close();}
report.events=client.events;
console.log(JSON.stringify(report));
if(report.harness_error)process.exitCode=1;
