import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const R=path.resolve(import.meta.dirname,'..'),src=path.join(R,'sources/openclaw');
const stateDir=path.join(R,'fixtures/extended-context/openclaw-state');fs.mkdirSync(stateDir,{recursive:true});
process.env.OPENCLAW_STATE_DIR=stateDir;process.env.OPENCLAW_CONFIG_PATH=path.join(stateDir,'openclaw.json');
fs.writeFileSync(process.env.OPENCLAW_CONFIG_PATH,'{}');
const {truncateOversizedToolResultsInMessages}=await import(pathToFileURL(path.join(src,'src/agents/embedded-agent-runner/tool-result-truncation.ts')));
const {resolveLiveToolResultMaxChars}=await import(pathToFileURL(path.join(src,'src/agents/tool-result-limits.ts')));
const {estimateToolResultTextChars}=await import(pathToFileURL(path.join(src,'src/agents/embedded-agent-runner/tool-result-text-budget.ts')));
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
const cases=[];
for(const c of JSON.parse(fs.readFileSync(path.join(R,'fixtures/extended-context/manifest.json')))){
 const text=fs.readFileSync(c.path,'utf8');
 const message={role:'toolResult',toolCallId:c.name,toolName:'bench_data',content:[{type:'text',text}],isError:false,timestamp:Date.now()};
 const projected=truncateOversizedToolResultsInMessages([message],c.context);
 const inline=projected.messages[0].content.filter(x=>x.type==='text').map(x=>x.text).join('\n');
 const budget=resolveLiveToolResultMaxChars({contextWindowTokens:c.context});
 const weighted=estimateToolResultTextChars(inline);
 const originalIntegrity=sha(message.content[0].text)===c.sha256;
 const truncated=inline!==text;
 const notice=truncated?(/truncat|omitted|elided/.test(inline)):true;
 const evidenceFile=path.join(R,'raw/extended-controls',`context-openclaw-${c.name}.txt`);fs.writeFileSync(evidenceFile,inline);
 cases.push({...c,actual:{budget_weighted_chars:budget,inline_weighted_chars:weighted,inline_codepoints:[...inline].length,inline_utf16: inline.length,inline_utf8_bytes:Buffer.byteLength(inline),inline_fraction_utf8:Buffer.byteLength(inline)/c.utf8_bytes,truncated,notice,original_message_sha256:sha(message.content[0].text),original_message_preserved:originalIntegrity,archive_path:null,archive_sha256:null,markers_inline:Object.fromEntries(Object.entries(c.markers).map(([k,v])=>[k,inline.includes(v)])),projection_count:projected.truncatedCount},expected:{within_native_budget:true,truncation_notice_when_needed:true,original_message_preserved:true},passed:weighted<=budget&&notice&&originalIntegrity,evidence_file:path.relative(R,evidenceFile)});
}
fs.writeFileSync(path.join(R,'raw/extended-controls/context-openclaw.json'),JSON.stringify(cases,null,2));
console.log(JSON.stringify({passed:cases.filter(x=>x.passed).length,total:cases.length,inline_fractions:cases.map(x=>[x.name,x.actual.inline_fraction_utf8])}));
