// All payloads are synthetic and the only endpoint is the owned loopback Gateway.
import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const client=await gatewayClient(spec);
const report={kind:'public-trace-access-probe',responses:[],native_invoked:false};
try{
 const owner=await client.paired({scopes:['operator.admin']});
 if(!owner.result.ok)throw new Error('Owner authentication positive control failed');
 const health=await owner.rpc('health',{});
 if(!health.ok)throw new Error('Owner health positive control failed');
 report.native_invoked=true;
 let selected=owner;
 if(spec.role){
  const reader=await client.paired({pairable:true},owner);
  if(!reader.result.ok||!reader.token)throw new Error('Reader pairing positive control failed');
  selected=await client.connect({identity:reader.identity,token:reader.token,pairable:true,
    scopes:spec.role==='read'?['operator.read']:[]});
  if(!selected.result.ok)throw new Error('Scoped connection positive control failed');
 }
 report.granted_scopes=selected.scopes;
 for(const operation of spec.operations){
  const started=performance.now();
  const result=await selected.rpc(operation.method,operation.params);
  report.responses.push({method:operation.method,result,latency_ms:performance.now()-started});
 }
}catch(error){report.harness_error=error.name+': '+error.message;}
finally{client.close();}
report.events=client.events;
const encoded=JSON.stringify(report);
if(Buffer.byteLength(encoded)>512*1024)throw new Error('Trace export exceeded its predeclared bound');
console.log(encoded);
if(report.harness_error)process.exitCode=1;
