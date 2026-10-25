import fs from 'node:fs';import path from 'node:path';import {pathToFileURL}from'node:url';
const root=path.resolve(import.meta.dirname,'..');const secret=process.env.DEEPSEEK_API_KEY;if(!secret)throw Error('Missing credential');
const{streamSimpleOpenAICompletions}=await import(pathToFileURL(path.join(root,'sources/openclaw/packages/ai/src/providers/openai-completions.ts')));
const spec=JSON.parse(fs.readFileSync(path.join(root,'results/extended-vision-cases.json'),'utf8'));const records=[];
const model={id:'deepseek-flash',name:'DeepSeek Flash',provider:'deepseek-bench',api:'openai-completions',baseUrl:'https://api.deepseek.com',reasoning:true,input:['text','image'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:128000,maxTokens:512,compat:{thinkingFormat:'deepseek',supportsReasoningEffort:false,supportsDeveloperRole:false,maxTokensField:'max_tokens'}};
for(const item of spec.cases){
 const record={case_id:item.case_id,sha256:item.sha256};
 try{const response=await streamSimpleOpenAICompletions(model,{systemPrompt:'Extract exactly the requested fields from the image. JSON only.',messages:[{role:'user',content:[{type:'text',text:spec.prompt},{type:'image',data:fs.readFileSync(item.path).toString('base64'),mimeType:'image/png'}],timestamp:Date.now()}]},{apiKey:secret,temperature:0,maxTokens:256,reasoning:'off',onPayload:p=>{p.thinking={type:'disabled'};return p;}}).result();record.response=response;record.text=response.content.filter(x=>x.type==='text').map(x=>x.text).join('');}
 catch(error){record.error_type=error.name;record.error=error.message;}
 records.push(record);fs.mkdirSync(path.join(root,'raw/extended-models'),{recursive:true});fs.writeFileSync(path.join(root,'raw/extended-models/vision-openclaw.json'),JSON.stringify({framework:'openclaw',entrypoint:'packages/ai/providers/openai-completions.streamSimpleOpenAICompletions',records},null,2).replaceAll(secret,'[REDACTED]'));
 console.log(JSON.stringify({framework:'openclaw',case_id:item.case_id,text:record.text,error_type:record.error_type}));
}
