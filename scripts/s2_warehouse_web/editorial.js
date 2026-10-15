'use strict';
// Online adapters for the preserved v5/v6/v7 editorial logic. All state remains
// a browser reference layer; fetched records and warehouse shards are never edited.
const bundleDays=new Map(),tagIndex=new Map(),memberTags=new Map(),loadedGroups=new Map();
let scopeRows=[],editorialRequest=0;
const specialView=()=>view==='bundles'||view==='rundown';
const editorialDay=()=>states.handoff.shift;
const onlineNotice=text=>{$('editorialNotice').textContent=text;};
const run=fn=>async(...args)=>{try{return await fn(...args);}catch(e){onlineNotice('載入或操作失敗：'+errorText(e)+'；請重試。');}};

async function groupRows(group,key){
  const entry=manifest[group]?.find(e=>e.date===key);if(!entry)return [];
  const cacheKey=group+':'+key;
  if(!loadedGroups.has(cacheKey)){
    const pending=(async()=>{const rows=[];for(const p of entry.parts)rows.push(...(await getJSON(p.path,p.sha256)).items);return rows;})();
    loadedGroups.set(cacheKey,pending);
    pending.catch(()=>loadedGroups.delete(cacheKey));
  }
  return loadedGroups.get(cacheKey);
}
async function ensureBundleScope(mode,day){
  const entries=mode==='archive'?manifest.bundles:manifest.bundles.filter(e=>e.date===day);
  // Bounded fetch concurrency, including on the 70-shift archive view.
  let i=0;await Promise.all(Array.from({length:4},async()=>{while(i<entries.length){const e=entries[i++];bundleDays.set(e.date,await groupRows('bundles',e.date));}}));
  refreshBundleIndex();
}
function registerEditorial(rows){
  for(const raw of rows){if(archiveById.has(raw.id))continue;const r={...raw};delete r.meta;archiveById.set(r.id,r);DATA.archive.push(r);DATA.draftMeta[r.id]=raw.meta||{};}
}
async function ensureEditorialDay(day){registerEditorial(await groupRows('editorial',day));}
async function hydrate(ids){
  const missing=[...new Set(ids)].filter(id=>!archiveById.has(id)&&!id.startsWith('sp-external-'));
  const buckets=new Map();
  for(const id of missing){const bytes=new TextEncoder().encode(id),h=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('').slice(0,2);if(!buckets.has(h))buckets.set(h,[]);buckets.get(h).push(id);}
  const refs=[];for(const key of buckets.keys())refs.push(...await groupRows('references',key));
  const map=new Map(refs.map(r=>[r.id,r])),days=new Set(missing.map(id=>map.get(id)?.day).filter(Boolean));
  for(const day of days)await ensureEditorialDay(day);
  for(const id of missing){const ref=map.get(id),r=ref&&archiveById.get(ref.material_id);if(r)archiveById.set(id,r);}
}
async function loadInventory(day=''){
  await ensureBundleScope('archive',day);
  if(day){
    // Editorial shards have a single owning shift; references resolve repeated
    // observations without downloading every other shift's full text.
    const entries=manifest.shifts.filter(e=>e.date===day);const ids=[];
    for(const e of entries)for(const p of e.parts)ids.push(...(await getJSON(p.path,p.sha256)).items.map(r=>r.material_id));
    await hydrate(ids);
  }else{let i=0;await Promise.all(Array.from({length:4},async()=>{while(i<manifest.editorial.length){const e=manifest.editorial[i++];await ensureEditorialDay(e.date);}}));}
}
function fullDay(day){if(/^\d{4}-\d{2}-\d{2}$/.test(day||''))return day;return manifest.shifts.find(e=>e.date.slice(5).replace('-','')===day)?.date||day;}
function canonicalId(id){return archiveById.get(id)?.id||id;}
function refreshBundleIndex(){
  const merged=new Map();
  for(const bundles of bundleDays.values())for(const b of bundles){const prev=merged.get(b.id);merged.set(b.id,prev?{...prev,ids:[...new Set([...prev.ids,...b.ids])],shifts:{...prev.shifts,...b.shifts}}:structuredClone(b));}
  DATA.bundleData.bundles=[...merged.values()];tagIndex.clear();memberTags.clear();
  const all=allBundles();
  for(const day of manifest.shifts.map(e=>e.date)){
    const original=new Map((bundleDays.get(day)||[]).map(b=>[b.id,b]));
    for(const b of all){
      const custom=b.id.startsWith('custom-');if(custom&&fullDay(b.day)!==day)continue;
      const base=original.get(b.id);if(!custom&&!base&&!bundleStore.edits[b.id])continue;
      const ids=[...new Set(b.ids.map(canonicalId))].filter(id=>custom||(base?.ids.includes(id))||archiveById.get(id)?.obs.some(o=>o.shift==='s2:'+day));
      if(!ids.length&&!custom)continue;
      const t={key:day+':'+b.id,bundleId:b.id,day,name:b.name,ids,custom,a33:base?.shifts?.[day]};tagIndex.set(t.key,t);
      for(const id of ids){if(!memberTags.has(id))memberTags.set(id,[]);memberTags.get(id).push(t);}
    }
  }
}
const dayTags=(day=editorialDay())=>[...tagIndex.values()].filter(t=>t.day===day).sort((a,b)=>b.ids.length-a.ids.length||a.name.localeCompare(b.name,'zh-Hant'));
function passBundleTags(row,s){return !s.bundleTags.size||(memberTags.get(row.material_id)||[]).some(t=>s.bundleTags.has(t.key));}
function filterTag(t){
  states.handoff.bundleTags=new Set([t.key]);states.handoff.shift=t.day;states.handoff.page=1;
  // Preserve other filter groups just as v8 did; callers may clear them explicitly.
  if(view==='handoff'){restore();load().then(()=>$('results').firstElementChild?.scrollIntoView({block:'start'}));}
  else switchView('handoff').then(()=>$('results').firstElementChild?.scrollIntoView({block:'start'}));
}
function drawBundleFilters(){
  if(!manifest||specialView())return;
  const group=node('details','filter-group');group.id='bundleTagFilters';group.open=true;group.append(node('summary','','議題包 TAG'));
  const s=current(),without={...s,bundleTags:new Set()},hits=new Map();
  for(const row of scopeRows)if(pass(row,without))for(const t of memberTags.get(row.material_id)||[]){if(view==='handoff'&&t.day!==s.shift)continue;hits.set(t.key,(hits.get(t.key)||0)+1);}
  const days=view==='handoff'?[s.shift]:manifest.shifts.map(e=>e.date).reverse();
  for(const day of days){const tags=dayTags(day).filter(t=>hits.has(t.key)||s.bundleTags.has(t.key));if(!tags.length)continue;const wrap=node('div','tag-day');wrap.dataset.tagDay=day;if(view==='archive')wrap.append(node('h3','',day+' 班'));
    const list=node('div','tag-choices');tags.forEach((t,i)=>{const lab=node('label','check bundle-tag'),cb=node('input');cb.type='checkbox';cb.checked=s.bundleTags.has(t.key);cb.dataset.bundleTag=t.key;cb.title=cb.ariaLabel=`${t.name}：${t.ids.length} 位成員，目前條件 ${hits.get(t.key)||0} 筆觀測`;cb.onchange=()=>{cb.checked?s.bundleTags.add(t.key):s.bundleTags.delete(t.key);load();};lab.append(cb,document.createTextNode('# '+t.name+' · '+t.ids.length));if(i>=8&&!cb.checked)lab.hidden=true;list.append(lab);});wrap.append(list);
    if(tags.length>8)wrap.append(button('顯示全部 '+tags.length+' 個 TAG',e=>{for(const lab of list.children)lab.hidden=false;e.currentTarget.hidden=true;}));group.append(wrap);
  }
  if(!group.querySelector('.tag-day'))group.append(node('p','hint','目前條件沒有議題包 TAG。'));
  const before=$('filterGroups').children[1];$('filterGroups').insertBefore(group,before||null);
}
function materialEditorialActions(row,body,tags){
  for(const t of memberTags.get(row.material_id)||[]){if(view==='handoff'&&t.day!==current().shift)continue;tags.append(button('# '+t.name+(view==='archive'?' · '+t.day.slice(5):''),()=>{const s=current();s.bundleTags.has(t.key)?s.bundleTags.delete(t.key):s.bundleTags.add(t.key);load();},'chip bundle-tag'));}
  const tools=node('div','bundle-tools'),check=node('label','check'),cb=node('input');cb.type='checkbox';cb.checked=selectionOrder.includes(row.material_id);cb.onchange=()=>{const i=selectionOrder.indexOf(row.material_id);if(cb.checked&&i<0)selectionOrder.push(row.material_id);else if(!cb.checked&&i>=0)selectionOrder.splice(i,1);};check.append(cb,document.createTextNode('F02 暫存'));tools.append(check,
    button('加入稿單',run(async()=>{await hydrate([row.material_id]);await switchView('rundown');rdAdd([row.material_id]);}),'rd-add-material'),
    button('加入議題包',run(async()=>{await hydrate([row.material_id]);await switchView('bundles');$('bundlePending').dataset.id=row.material_id;$('bundlePending').textContent='待加入：'+row.id;$('bundleTarget').focus();}),'add-bundle'));body.append(tools);
}
function drawEditorialEntry(){
  const day=editorialDay(),count=manifest.bundles.find(e=>e.date===day)?.count||0,n=manifest.rundowns.find(e=>e.date===day)?.count||0;
  $('editorialEntry').replaceChildren(button(`${day} 班｜${count} 個議題包 TAG`,()=>switchView('bundles')),button(`${n} 份候選稿單 · 稿單助手`,()=>switchView('rundown')));
}
function restoreEditorialView(){
  const special=specialView();$('searchForm').hidden=special;document.querySelector('.layout').hidden=special;$('bundlesPage').hidden=view!=='bundles';$('rundownPage').hidden=view!=='rundown';$('editorialEntry').hidden=special;
  for(const name of ['handoff','archive','bundles','rundown'])$(name+'Tab').setAttribute('aria-pressed',String(view===name));
  if(special){$('title').textContent=view==='bundles'?'今日議題包':'稿單助手';$('subtitle').textContent=view==='bundles'?'展開本班 TAG 校閱成員，整理成開稿包或送往稿單助手。':'從人工候選或指定議題組稿，編輯、增補並保存。';}
  shift=DATA.shifts.findIndex(s=>s.day===editorialDay());
}
function saveOnlineView(){try{localStorage.setItem('s2.demo.view.v8',JSON.stringify({version:1,view,day:editorialDay(),shift:editorialDay()}));}catch(e){onlineNotice('無法保存分頁與班次；當次操作仍可使用。');}}
async function loadEditorialView(){
  const request=++editorialRequest;++token;controller?.abort();const day=editorialDay();saveOnlineView();onlineNotice('讀取本班議題包與稿單資料…');
  try{
    await ensureBundleScope('archive',day);await loadInventory(day);
    const cs=await groupRows('rundowns',day);await hydrate(cs.flatMap(c=>c.segments.flatMap(s=>s.items.map(i=>i.material_id))));
    if(request!==editorialRequest||day!==editorialDay()||!specialView())return;
    DATA.rundownV6.candidates=cs;renderBundles();renderToday();rdRenderCards();rdRenderEditor();renderLocks();
    $('rdCandidatesSection').querySelector('.rd-intro').textContent=cs.length?`${cs.length} 份人工編輯提案 · 採用後可編輯；略過後仍可重新採用。`:'本班尚無候選稿單';
    $('rdShift').value=day;rdInvalidateQuery();onlineNotice('');
  }catch(e){if(request===editorialRequest)onlineNotice('讀取失敗：'+errorText(e)+'；可重新選取班次重試。');}
}
function renderToday(){
  const tags=dayTags().filter(t=>!t.custom).sort((a,b)=>Number(!!b.a33?.qualifies)-Number(!!a.a33?.qualifies)||(b.a33?.score||0)-(a.a33?.score||0)||a.name.localeCompare(b.name,'zh-Hant')).slice(0,10);
  $('todayBundles').replaceChildren(node('h2','','A33 推薦 TAG'),node('p','hint','依本班 A33 訊號排序前 10 包；點 TAG 到晚班交接篩選。'));
  const list=node('div','bundle-tools');for(const t of tags)list.append(button('# '+t.name+' · '+t.ids.length,()=>filterTag(t),'bundle-tag'));$('todayBundles').append(list);
}
function renderBundles(){
  refreshBundleIndex();const tags=dayTags(),target=$('bundleTarget'),old=target.value;target.replaceChildren(...tags.map(t=>{const o=node('option','',t.name);o.value=t.bundleId;return o;}));if([...target.options].some(o=>o.value===old))target.value=old;
  $('bundleSummary').textContent=`本班議題包 TAG（${tags.length} 個）`;$('bundleList').replaceChildren();
  for(const t of tags.filter(t=>t.name.includes($('bundleSearch').value.trim()))){
    const d=node('details','bundle-row');d.dataset.bundle=t.bundleId;const rs=t.ids.map(id=>archiveById.get(id)).filter(Boolean),info=suggest(rs),dates=rs.map(r=>r.md).filter(Boolean).sort(),sources=[...groupBy(rs,r=>r.src)].map(([s,a])=>s+' '+a.length).join('／');
    const summary=node('summary','',`# ${t.name} · ${t.ids.length} 則 · ${info.form}`);
    summary.append(node('span','bundle-meta',sources+'｜素材日 '+(dates.length?dates[0]+' ～ '+dates.at(-1):'未知')+'｜'+(t.custom?'自訂':t.a33?.qualifies?'A33 達標':'A33 未達標')));d.append(summary);
    d.addEventListener('toggle',()=>{if(!d.open||d.dataset.built)return;d.dataset.built='1';const b=allBundles().find(b=>b.id===t.bundleId),tools=node('div','bundle-tools'),name=node('input');name.value=t.name;name.ariaLabel='議題包名稱';name.maxLength=120;
      tools.append(name,button('改名',()=>{if(name.value.trim())saveBundle({...b,name:name.value.trim()});}));
      tools.append(button('到晚班交接篩選',()=>filterTag(t),'filter-bundle'),button('送到稿單助手組稿',run(async()=>{await hydrate(t.ids);await switchView('rundown');const draft=rdMakeDraft(t.ids,t.name);draft.topic=t.name;draft.bundle_id=t.bundleId;rdStore.drafts[draft.id]=draft;rdStore.active=draft.id;rdSave();rdRenderSaved();rdRenderEditor();$('rdEditor').scrollIntoView({block:'start'});}),'bundle-compose'),button('整理成開稿包',()=>openDraft(t.name,t.ids,t.bundleId),'bundle-draft'));d.append(tools,node('p','hint','改名與成員調整會套用此議題包在其他班的 TAG。'));
      for(const id of t.ids){const r=archiveById.get(id),line=node('div','bundle-member');line.append(button(r?`${r.code}｜${r.md||'日期未知'}｜${r.text.split('\n')[0]}`:id,()=>gotoMaterial(id),'member-link'),button('移除',()=>saveBundle({...b,ids:b.ids.filter(x=>canonicalId(x)!==id)}),'bundle-remove'));d.append(line);}
    });$('bundleList').append(d);
  }
}
// Preserve the original keys and validation; convert resolvable legacy IDs only
// in memory. A failed/unknown localStorage record is never overwritten.
const onlineSaveBundle=saveBundle;
saveBundle=function(b){if(b.id.startsWith('custom-')&&!b.day)b.day=editorialDay();const ok=onlineSaveBundle(b);if(ok){refreshBundleIndex();if(!specialView())load();rdRenderSaved();}return ok;};
async function addToBundle(ids){await hydrate(ids);const b=allBundles().find(b=>b.id===$('bundleTarget').value);if(!b||!ids.length){bundleStatus('請先選擇議題包及素材。');return;}saveBundle({...b,ids:[...new Set([...b.ids,...ids.map(canonicalId)])]});}
const onlineOpenDraft=openDraft;
openDraft=async function(name,ids,bundle=null,scroll=true){await hydrate(ids);if(scroll)await switchView('rundown');onlineOpenDraft(name,ids,bundle,scroll);};
async function gotoMaterial(id){
  await hydrate([id]);const r=archiveById.get(id);if(!r){onlineNotice('本版缺少此素材。');return;}const s=states.archive;Object.assign(s,state(),{from:r.md||manifest.default_end_date,to:r.md||manifest.default_end_date,notes:true,unknown:!r.md,keyword:r.code});
  if(view==='archive'){restore();await load();}else await switchView('archive');
  const index=results.findIndex(row=>row.material_id===r.id);
  if(index>=0){pageNumber=Math.floor(index/PAGE_SIZE)+1;renderPage();const item=[...$('results').children].find(n=>n.dataset.materialId===r.id);item?.scrollIntoView({block:'start'});item?.classList.add('bundle-target');}
  else onlineNotice('目前發布分片找不到此素材，請核對素材日期與版本。');
}
const onlineRenderEditor=rdRenderEditor;
rdRenderEditor=function(){onlineRenderEditor();if(!rdDraft())return;
  if($('spOpen'))$('spOpen').onclick=run(async()=>{onlineNotice('讀取跨班庫存供增補…');await loadInventory();onlineNotice('');rdRenderEditor();$('spPanel').open=true;$('spPanel').scrollIntoView({block:'start'});});
  const f02=$('rdEditor').querySelector('.rd-add-f02');if(f02)f02.onclick=run(async()=>{await hydrate(selectionOrder);rdAdd(selectionOrder);});
  const bundle=$('rdEditor').querySelector('.rd-add-bundle');if(bundle)bundle.onclick=run(async()=>{const ids=allBundles().find(b=>b.id===$('rdBundleTarget').value)?.ids||[];await hydrate(ids);rdAdd(ids);});
};
async function initEditorial(){
  DATA.shifts=manifest.shifts.map(e=>({day:e.date}));DATA.supplementV7=(await groupRows('config','supplement'))[0]||DATA.supplementV7;
  // Restore v8 view records (old v8 used a numeric shift and an MMDD day).
  try{const saved=JSON.parse(localStorage.getItem('s2.demo.view.v8')||'null');const day=fullDay(saved?.day||saved?.shift);if(saved?.version===1&&['handoff','archive','bundles','rundown'].includes(saved.view)){view=saved.view;if(manifest.shifts.some(e=>e.date===day))states.handoff.shift=day;}}catch(e){onlineNotice('無法保存或還原分頁；當次操作仍可使用。');}
  const ids=new Set();
  for(const key of [BUNDLE_KEY,RD_KEY])try{const saved=JSON.parse(localStorage.getItem(key)||'null');const walk=v=>{if(!v||typeof v!=='object')return;if(Array.isArray(v.ids))v.ids.forEach(id=>{if(typeof id==='string')ids.add(id);});if(typeof v.material_id==='string')ids.add(v.material_id);for(const value of Object.values(v))if(typeof value==='object')walk(value);};walk(saved);}catch(e){/* Original loaders report and protect malformed records. */}
  await hydrate([...ids]);loadBundleStore();
  for(const b of [...Object.values(bundleStore.edits),...bundleStore.custom])b.ids=b.ids.map(canonicalId);
  for(const b of bundleStore.custom)if(!b.day)b.day=editorialDay();
  initRundown();
  for(const d of Object.values(rdStore.drafts)){for(const s of d.segments)for(const item of s.items)item.material_id=canonicalId(item.material_id);for(const bite of d.bites)bite.material_id=canonicalId(bite.material_id);}
  const queryButton=[...$('rdQueryPanel').querySelectorAll('button')].find(b=>b.textContent==='尋找建議素材');
  const queryState=()=>['rdQuery','rdShift','rdFrom','rdTo'].map(id=>$(id).value).join('\n');
  queryButton.onclick=run(async()=>{const conditions=queryState();queryButton.disabled=true;onlineNotice('讀取指定班次的素材…');try{await loadInventory($('rdShift').value);if(conditions!==queryState()){onlineNotice('條件已變更，請重新尋找建議素材。');return;}onlineNotice('');rdRunQuery();}finally{queryButton.disabled=false;}});
  $('rdQuery').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();queryButton.click();}};
  $('bundleSearch').oninput=renderBundles;
  $('newBundle').onclick=()=>{const name=$('newBundleName').value.trim();if(!name){bundleStatus('請填寫自訂包名稱。');return;}if(saveBundle({id:'custom-'+crypto.randomUUID(),name,day:editorialDay(),ids:[]}))$('newBundleName').value='';};
  $('addStaged').onclick=run(()=>addToBundle(selectionOrder));$('addPending').onclick=run(()=>addToBundle($('bundlePending').dataset.id?[$('bundlePending').dataset.id]:[]));
  $('draftTitle').oninput=updateDraft;$('copyDraft').onclick=()=>copy($('draftText').textContent);
  $('lockDraft').onclick=()=>{if(!draftInput?.ids.length){bundleStatus('空清單無法鎖定。');return;}const next=structuredClone(bundleStore);next.locks.push({package_id:'pkg-'+crypto.randomUUID(),created:new Date().toISOString(),title:$('draftTitle').value,ids:[...draftInput.ids],signatures:Object.fromEntries(draftInput.ids.map(id=>[id,signature(id)])),text:$('draftText').textContent});if(saveBundleStore(next))renderLocks();};
  $('showLocks').onclick=run(async()=>{await switchView('rundown');$('draftPanel').hidden=false;$('draftPanel').open=true;renderLocks();$('draftPanel').scrollIntoView({block:'start'});});
  $('bundlesTab').onclick=()=>switchView('bundles');$('rundownTab').onclick=()=>switchView('rundown');
  const originalShift=$('shift').onchange;$('shift').onchange=()=>{if(specialView())states.handoff.shift=$('shift').value;else current().bundleTags.clear();originalShift();saveOnlineView();};
  renderLocks();
}
init();
