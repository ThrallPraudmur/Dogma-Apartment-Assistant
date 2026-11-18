import test from 'node:test';
import assert from 'node:assert/strict';
import {select} from '../src/search.mjs';
const snapshot={metadata:{complete:true},apartments:[{id:1,project:'Самолёт',status_code:2,price_rub:7000000,area_m2:30,rooms:0},{id:2,project:'Самолёт',status_code:2,price_rub:7000001,area_m2:31,rooms:0},{id:3,project:'Самолёт 7',status_code:2,price_rub:6000000,area_m2:29,rooms:0},{id:4,project:'Самолёт',status_code:5,price_rub:5000000,area_m2:40,rooms:0}]};
test('Inclusive boundaries, studio=0, exact project and availability',()=>assert.deepEqual(select(snapshot,{project:'самолет',budget_max:7000000,area_min:30,rooms:0}).answer.map(a=>a.id),[1]));
test('Ambiguous project requires clarification',()=>assert.equal(select(snapshot,{project:'сам'}).needs_clarification,true));
test('No matches never relaxes filters',()=>assert.equal(select(snapshot,{budget_max:1}).total_matches,0));
test('Reject malformed LLM filters',()=>{for(const f of [{budget_max:'7 млн'},{area_min:40,area_max:30},{sql:'DROP TABLE'},{rooms:0.5}])assert.throws(()=>select(snapshot,f));});
