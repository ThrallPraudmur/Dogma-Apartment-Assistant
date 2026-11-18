import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
export const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export const API='https://service.dogma.ru/api/layouts-filter/v4';
export async function request(endpoint,body){
 for(let attempt=0;attempt<3;attempt++){
  try{const r=await fetch(API+endpoint,{method:'POST',headers:{'Content-Type':'application/json','User-Agent':'DogmaTestAssignment/1.0'},body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
   if(!r.ok)throw Error(`HTTP ${r.status}`);const j=await r.json();if(j.error||!j.data)throw Error(JSON.stringify(j.error??j));return j.data;
  }catch(e){if(attempt===2)throw e;await new Promise(r=>setTimeout(r,1000*(attempt+1)));}
 }
}
export function normalize(o,at){
 for(const k of ['id','project_id','project_name','cost','area','room','floor','status'])if(o[k]===undefined||o[k]===null)throw Error(`Missing ${k}, id=${o.id}`);
 const sale=Number(o.cost_sale)>0?Number(o.cost_sale):null;
 const row={id:Number(o.id),project_id:Number(o.project_id),project:o.project_name,price_rub:sale??Number(o.cost),base_price_rub:Number(o.cost),sale_price_rub:sale,area_m2:Number(o.area),rooms:Number(o.room),floor:Number(o.floor),floors_total:Number(o.floor_max),status_code:Number(o.status),status:'catalog_available',url:`https://dogma.ru/flat/${o.id}`,project_url:new URL(o.project_link,'https://dogma.ru').href,address:o.address??null,collected_at:at};
 if(!(row.price_rub>0&&row.area_m2>0&&Number.isInteger(row.id)))throw Error(`Invalid lot ${o.id}`);return row;
}
export function saveSqlite(rows,file){
 const db=new DatabaseSync(file);try{db.exec('CREATE TABLE IF NOT EXISTS apartments (id INTEGER PRIMARY KEY, project_id INTEGER, project TEXT, price_rub REAL, base_price_rub REAL, sale_price_rub REAL, area_m2 REAL, rooms INTEGER, floor INTEGER, floors_total INTEGER, status_code INTEGER, status TEXT, url TEXT, project_url TEXT, address TEXT, collected_at TEXT); BEGIN; DELETE FROM apartments;');
 const keys=Object.keys(rows[0]);const stmt=db.prepare(`INSERT INTO apartments (${keys.join(',')}) VALUES (${keys.map(()=>'?').join(',')})`);for(const row of rows)stmt.run(...keys.map(k=>row[k]));db.exec('CREATE INDEX IF NOT EXISTS idx_filter ON apartments(project_id,price_rub,area_m2); COMMIT;');}finally{db.close();}
}
export async function scrape(){
 const started_at=new Date().toISOString(), rows=new Map(), counts=[];let offset=0,duplicates=0;
 while(true){const data=await request('/objects/filter',{type:1,statuses:[2],limit:100,offset,group_by:'',order:{field:'id',type:'asc'}});counts.push(Number(data.count));
 if(!Array.isArray(data.objects))throw Error('API schema changed: objects is not an array');
 if(!data.objects.length){if(offset<Number(data.count))throw Error('Premature empty page');break;}
 for(const o of data.objects){if(rows.has(o.id))duplicates++;rows.set(o.id,normalize(o,started_at));}offset+=data.objects.length;
 if(offset%1000===0)console.log(`${offset}/${data.count}`);
 if(offset>=Number(data.count))break;await new Promise(r=>setTimeout(r,150));
 }
 const apartments=[...rows.values()].sort((a,b)=>a.id-b.id);if(!apartments.length)throw Error('Empty catalog; previous snapshot preserved');
 const metadata={source:API+'/objects/filter',started_at,finished_at:new Date().toISOString(),scope:{type:1,statuses:[2],cities:'all'},reported_count:counts.at(-1),downloaded_rows:offset,unique_count:apartments.length,duplicates,count_changed:new Set(counts).size>1,complete:new Set(counts).size===1&&duplicates===0&&apartments.length===counts[0],price_policy:'positive cost_sale, otherwise cost',status_policy:'code 2 used by public catalog; other statuses not collected'};
 fs.mkdirSync(path.join(ROOT,'data'),{recursive:true});const out=path.join(ROOT,'data','apartments.json');fs.writeFileSync(out+'.tmp',JSON.stringify({metadata,apartments},null,2));
 saveSqlite(apartments,path.join(ROOT,'data','apartments.sqlite'));fs.renameSync(out+'.tmp',out);console.log(JSON.stringify(metadata,null,2));
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))scrape().catch(e=>{console.error(e);process.exitCode=1});
