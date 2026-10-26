import fs from 'node:fs';
import {gatewayClient} from './public_gateway_client.mjs';
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const client=await gatewayClient(spec);const rows=[];
try{
 const owner=await client.paired({scopes:['operator.admin']});
 if(!owner.result.ok)throw new Error('Native operator authentication failed');
 for(const operation of spec.operations)rows.push({method:operation.method,result:await owner.rpc(operation.method,operation.params??{},operation.timeout??180000)});
 console.log(JSON.stringify({native_invoked:true,responses:rows,events:client.events}));
}catch(error){console.log(JSON.stringify({harness_error:error.name+': '+error.message,responses:rows}));process.exitCode=1;}
finally{client.close();}
