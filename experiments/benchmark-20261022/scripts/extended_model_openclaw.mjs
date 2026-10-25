import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=path.resolve(import.meta.dirname,'..');
const source=path.join(root,'sources/openclaw');
const secret=process.env.DEEPSEEK_API_KEY;
if(!secret)throw Error('DeepSeek credential not configured');
const {registerSealedRuntimeProcessEntrypoint}=await import(pathToFileURL(path.join(source,'src/infra/runtime-process-url.ts')));
registerSealedRuntimeProcessEntrypoint('serviceChildGroupAnchor',pathToFileURL(path.join(source,'dist/process/supervisor/service-child-group-anchor.js')));
const {agentExecCommand}=await import(pathToFileURL(path.join(source,'src/commands/agent-exec.ts')));
const cases=JSON.parse(fs.readFileSync(path.join(root,'results/extended-model-cases.json'),'utf8')).cases;
const config=JSON.parse(fs.readFileSync(path.join(root,'configs/openclaw-deepseek-config.json'),'utf8'));
config.agents.defaults.models['deepseek-bench/deepseek-flash'].params.maxTokens=1536;
const configPath=path.join(root,'runtime/extended-model-openclaw-config.json');
fs.mkdirSync(path.dirname(configPath),{recursive:true});fs.writeFileSync(configPath,JSON.stringify(config));
fs.mkdirSync(path.join(root,'runtime/extended-model-openclaw-state'),{recursive:true});
const dir=path.join(root,'raw/extended-models');fs.mkdirSync(dir,{recursive:true});
for(const item of cases){
 const output=path.join(dir,`openclaw-${item.case_id}.json`);if(fs.existsSync(output))continue;
 const logs=[];const runtime={log:(...args)=>logs.push({kind:'log',args}),error:(...args)=>logs.push({kind:'error',args}),writeStdout:value=>logs.push({kind:'stdout',value}),writeJson:value=>logs.push({kind:'json',value}),exit:code=>{throw Error(`Unexpected exit ${code}`)}};
 const record={framework:'openclaw',case_id:item.case_id,row:item.row,model:'deepseek-flash'};const start=performance.now();
 try{record.result=await agentExecCommand(item.prompt,{cwd:item.workspaces.openclaw,stateDir:path.join(root,'runtime/extended-model-openclaw-state'),config:configPath,model:'deepseek-bench/deepseek-flash',thinking:'off',codeMode:'direct',timeout:'120',json:true},runtime);}catch(error){record.error_type=error.name;record.error=error.message;}
 let actual=null;try{actual=JSON.parse(fs.readFileSync(path.join(item.workspaces.openclaw,item.output_file),'utf8'));}catch{}
 record.actual=actual;record.correct=JSON.stringify(actual)===JSON.stringify(item.expected);record.wall_seconds=(performance.now()-start)/1000;record.logs=logs;
 // Dictionary key order is not a semantic correctness condition; parent independently verifies JSON equality.
 fs.writeFileSync(output,JSON.stringify(record,null,2).replaceAll(secret,'[REDACTED]'));
 console.log(JSON.stringify({framework:'openclaw',case_id:item.case_id,correct:record.correct,wall_seconds:record.wall_seconds}));
}
