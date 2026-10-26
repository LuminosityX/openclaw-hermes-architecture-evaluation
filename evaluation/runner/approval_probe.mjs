// Public paired Control UI approval client. Only owned synthetic commands qualify.
import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const client=await gatewayClient(spec);
const report={kind:'owned-approval-probe',native_invoked:false};
try{
 const owner=await client.paired({scopes:['operator.admin']});
 if(!owner.result.ok)throw new Error('Owner connect failed');
 const ui=await client.paired({ui:true,origin:'http://127.0.0.1:18789',scopes:['operator.admin'],
  buildId:owner.result.payload.server.buildId,version:owner.result.payload.server.version},owner);
 if(!ui.result.ok)throw new Error('Native Control UI approval connection failed');
 report.native_invoked=true;
 const result=await new Promise(resolve=>{
  const timer=setTimeout(()=>resolve(null),20000);let handled=false;
  ui.socket.on('message',async bytes=>{
   let frame;try{frame=JSON.parse(String(bytes));}catch{return;}
   if(frame.type!=='event'||frame.event!=='exec.approval.requested'||handled)return;
   const approval=frame.payload;
   if(!JSON.stringify(approval).includes(spec.command_marker))return;
   handled=true;
   const before=fs.existsSync(spec.effect_path);
   await new Promise(done=>setTimeout(done,200));
   const verdict=await ui.rpc('exec.approval.resolve',{id:approval.id,decision:'allow-once'});
   clearTimeout(timer);resolve({approval_id:approval.id,decision:'allow-once',effect_before_decision:before,
    requested_monotonic_ns:Number(process.hrtime.bigint()),resolution:verdict});
  });
  console.log(JSON.stringify({kind:'owned-approval-listener-ready',ready:true}));
 });
 report.approval=result;
 if(!result)throw new Error('No matching native approval request observed');
}catch(error){report.harness_error=error.name+': '+error.message;}
finally{client.close();}
report.events=client.events;
console.log(JSON.stringify(report));
if(report.harness_error)process.exitCode=1;
