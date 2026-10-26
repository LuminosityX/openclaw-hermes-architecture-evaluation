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
  let result=await selected.rpc(operation.method,operation.params);
  const refresh=[];
  // sessions.usage explicitly distinguishes a refreshing cache from finalized
  // usage. A temporary zero cannot be scored as a missing token measurement.
  if(operation.method==='sessions.usage'){
   const pending=value=>value?.ok&&(value.payload?.cacheStatus?.status==='refreshing'||value.payload?.sessions?.some(row=>row.computing));
   while(pending(result)&&performance.now()-started<20000){
    refresh.push({elapsed_ms:performance.now()-started,cache_status:result.payload?.cacheStatus,totals:result.payload?.totals});
    await new Promise(resolve=>setTimeout(resolve,500));
    result=await selected.rpc(operation.method,operation.params);
   }
  }
  report.responses.push({method:operation.method,result,latency_ms:performance.now()-started,refresh_observations:refresh});
 }
}catch(error){report.harness_error=error.name+': '+error.message;}
finally{client.close();}
report.events=client.events;
const encoded=JSON.stringify(report);
if(Buffer.byteLength(encoded)>512*1024)throw new Error('Trace export exceeded its predeclared bound');
console.log(encoded);
if(report.harness_error)process.exitCode=1;
