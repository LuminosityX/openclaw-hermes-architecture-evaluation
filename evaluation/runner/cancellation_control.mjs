// A pre-connected real operator can write Stop while native JavaScript is busy.
import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const client=await gatewayClient(spec);
const report={requests:[],responses:[]};let finish;const done=new Promise(resolve=>{finish=resolve;});let buffer='';
const timer=setTimeout(finish,90000);
const observe=async(kind,values={})=>{
 const response=await fetch('http://127.0.0.1:18080/cancellation-control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,...values})});
 if(!response.ok)throw new Error('Owned cancellation observer failed');
};
try{
 const owner=await client.paired({scopes:['operator.admin']});if(!owner.result.ok)throw new Error('Actual cancel operator authentication failed');
 process.stdin.on('data',async bytes=>{
  buffer+=String(bytes);let newline;
  while((newline=buffer.indexOf('\n'))>=0){
   const command=buffer.slice(0,newline);buffer=buffer.slice(newline+1);
   if(command==='finish'){finish();continue;}
   if(command!=='abort')continue;
   try{
    const started=Number(process.hrtime.bigint());const pending=owner.rpc('sessions.abort',{key:spec.session_key},20000);
    let written;
    for(let i=0;i<100&&!written;i++){
     written=client.events.find(e=>e.kind==='rpc-request-written'&&e.method==='sessions.abort'&&e.monotonic_ns>=started);
     if(!written)await new Promise(resolve=>setTimeout(resolve,5));
    }
    if(written)report.requests.push({id:written.request_id,method:'sessions.abort',params:{key:spec.session_key}});
    await observe('actual-stop-request-written',{written});
    const result=await pending;const received=Number(process.hrtime.bigint());report.responses.push(result);
    await observe('actual-stop-response',{native_response:result,response_received_monotonic_ns:received});
   }catch(error){report.harness_error=error.message;await observe('control-error',{error:error.message});}
  }
 });
 console.log(JSON.stringify({ready:true}));await done;
}catch(error){report.harness_error=error.message;}
finally{clearTimeout(timer);client.close();}
console.log(JSON.stringify({...report,events:client.events}));if(report.harness_error)process.exitCode=1;
