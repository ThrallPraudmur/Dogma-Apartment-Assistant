import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export function select(snapshot,filters={},limit=5){
 const allowed=['budget_min','budget_max','area_min','area_max','project','rooms'];
 for(const k of Object.keys(filters))if(!allowed.includes(k))throw Error(`Unknown filter: ${k}`);
 for(const k of ['budget_min','budget_max','area_min','area_max','rooms'])if(filters[k]!=null&&(!Number.isFinite(filters[k])||filters[k]<0))throw Error(`Invalid ${k}`);
 if(filters.rooms!=null&&!Number.isInteger(filters.rooms))throw Error('rooms must be integer');
 if(filters.project!=null&&(typeof filters.project!=='string'||!filters.project.trim()))throw Error('project must be nonempty string');
 for(const [a,b] of [['budget_min','budget_max'],['area_min','area_max']])if(filters[a]!=null&&filters[b]!=null&&filters[a]>filters[b])throw Error(`${a} exceeds ${b}`);
 if(!Number.isInteger(limit)||limit<1||limit>5)throw Error('limit must be 1..5');
 const canon=s=>s.toLocaleLowerCase('ru').replaceAll('ё','е').trim();
 const projects=[...new Set(snapshot.apartments.map(a=>a.project))];let project;
 if(filters.project){const q=canon(filters.project);const exact=projects.filter(p=>canon(p)===q);const matches=exact.length?exact:projects.filter(p=>canon(p).includes(q));
 if(matches.length!==1)return {filters,answer:[],explanation:matches.length?'Уточните ЖК: найдено несколько совпадений.':'ЖК не найден.',needs_clarification:true,project_candidates:matches,total_matches:0};project=matches[0];}
 const rows=snapshot.apartments.filter(a=>a.status_code===2&&(!project||a.project===project)&&(filters.rooms==null||a.rooms===filters.rooms)&&(filters.budget_min==null||a.price_rub>=filters.budget_min)&&(filters.budget_max==null||a.price_rub<=filters.budget_max)&&(filters.area_min==null||a.area_m2>=filters.area_min)&&(filters.area_max==null||a.area_m2<=filters.area_max)).sort((a,b)=>a.price_rub-b.price_rub||b.area_m2-a.area_m2||a.id-b.id);
 return {filters:{...filters,...(project?{project}:{})},answer:rows.slice(0,limit).map(a=>({...a,explanation:[`ЖК «${a.project}»`,`${a.price_rub.toLocaleString('ru-RU')} ₽${filters.budget_max!=null?' — в пределах бюджета':''}`,`${a.area_m2} м²${filters.area_min!=null?' — не меньше требуемой площади':''}`,...(filters.rooms!=null?[a.rooms===0?'Студия':`Комнат: ${a.rooms}`]:[])].join('; ')})),explanation:rows.length?'Подходящие квартиры отсортированы по цене по возрастанию, затем по площади по убыванию.':'Точных совпадений нет. Условия поиска не изменялись.',total_matches:rows.length,needs_clarification:false,snapshot_at:snapshot.metadata.finished_at,snapshot_complete:snapshot.metadata.complete};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const s=JSON.parse(fs.readFileSync(path.join(root,'data/apartments.json'),'utf8'));const result=select(s,JSON.parse(process.argv[2]??'{}'),Number(process.argv[3]??5));console.log(JSON.stringify(result,null,2));}catch(e){console.error(e.message);process.exitCode=1;}
}
