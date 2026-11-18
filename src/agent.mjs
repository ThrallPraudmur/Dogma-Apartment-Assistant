import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {select} from './search.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export const DEFAULT_MODEL='inclusionai/ling-3.2-flash:free';
export async function ask(query,currentFilters={},limit=3){
 const key=process.env.OPENROUTER_API_KEY;if(!key)throw Error('Set OPENROUTER_API_KEY in environment');
 const model=process.env.OPENROUTER_MODEL??DEFAULT_MODEL;
 if(!model.endsWith(':free')&&model!=='openrouter/free')throw Error('Only free models are enabled');
 if(typeof query!=='string'||!query.trim()||query.length>8000)throw Error('Query must contain 1..8000 characters');
 const snapshot=JSON.parse(fs.readFileSync(path.join(root,'data/apartments.json'),'utf8'));
 select(snapshot,currentFilters,limit);
 const prompt=fs.readFileSync(path.join(root,'schemas/agent-prompt.txt'),'utf8');
 const r=await fetch('https://openrouter.ai/api/v1/chat/completions',{method:'POST',headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},body:JSON.stringify({model,temperature:0,max_tokens:2048,response_format:{type:'json_object'},messages:[{role:'system',content:prompt},{role:'system',content:'Текущие подтверждённые фильтры: '+JSON.stringify(currentFilters)},{role:'user',content:query}]}),signal:AbortSignal.timeout(60000)});
 const j=await r.json();if(!r.ok||j.error)throw Error(`OpenRouter HTTP ${r.status}: ${String(j.error?.message??'request failed').replaceAll(key,'[REDACTED]')}`);
 const out=JSON.parse(j.choices?.[0]?.message?.content??'');
 if(!out||Array.isArray(out)||Object.keys(out).some(k=>!['filters','needs_clarification','clarification_question'].includes(k))||typeof out.needs_clarification!=='boolean'||!out.filters||typeof out.filters!=='object'||Array.isArray(out.filters))throw Error('Invalid model response schema');
 if(out.needs_clarification){if(typeof out.clarification_question!=='string'||!out.clarification_question.trim())throw Error('Missing clarification question');return {filters:currentFilters,answer:[],needs_clarification:true,explanation:out.clarification_question,model:j.model};}
 if(out.clarification_question!==null)throw Error('Unexpected clarification question');
 for(const v of Object.values(out.filters))if(v===null)throw Error('Null filters are not allowed');
 return {...select(snapshot,out.filters,limit),model:j.model,usage:j.usage};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))ask(process.argv[2],JSON.parse(process.argv[3]??'{}')).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e.message.replaceAll(process.env.OPENROUTER_API_KEY??'__NO_KEY__','[REDACTED]'));process.exitCode=1;});
