
// 所有新增資料及本機編輯皆為引用衍生層；不改 DATA.archive／category。
// Compatibility projection populated lazily from hash-checked editorial shards.
const DATA={archive:[],shifts:[],bundleData:{bundles:[]},draftMeta:{},rundownV6:{slots:['1100','1200','1700','1730','2200'],candidates:[]},supplementV7:{sinceDays:7,canonicalAliases:[],candidateEnglish:{},fallbacks:[]}};
const archiveById=new Map(),el=node,SRC={},selectionOrder=[];
let shift=0;
const errorText=e=>e?.message||String(e);
const label=(axis,value)=>axis==='q'?(qualities[value]||value):({none:'無連結',search:'搜尋頁，待定位',direct:'有保存連結，未驗證可讀性'}[value]||value||'未知');
const linkInfo=r=>({url:r.link||'',state:!r.link?'none':/[?&](search|query)=|\/search\b/.test(r.link)?'search':'direct'});
const groupBy=(rs,fn)=>{const m=new Map();for(const r of rs){const k=fn(r);if(!m.has(k))m.set(k,[]);m.get(k).push(r);}return m;};
async function copy(text){try{await navigator.clipboard.writeText(text);onlineNotice('已複製。');}catch(e){onlineNotice('無法自動複製，請從下方純文字區選取備份。');}}
const BUNDLE_KEY='s2.demo.bundles.v1';
let bundleStore={version:1,edits:{},custom:[],locks:[]},bundleStorageOK=true,draftInput=null;
const v5Text=v=>v==null||v===''?'未保存':typeof v==='object'?JSON.stringify(v):String(v);
const DATE_WORDS={high:'高',medium:'中',low:'低',filmed:'拍攝日',unknown:'未知',date:'日期',second:'秒',month:'月份',year:'年份',published:'發布日',released:'發布日',updated:'更新日',file:'資料畫面',file_date:'資料畫面日期',event:'事件日',scheduled:'預定日期',recording_start:'側錄開始時間',local_editorial_update:'本機編輯更新時間',checkpoint_anchor:'班次觀測檢查點',src_text:'原稿內文',raw_entry:'交接原文',id:'素材代碼',entry_updated_ts:'編輯更新時間',published_at_utc:'來源發布時間（世界標準時間）','Asia/Taipei':'臺北時間',UTC:'世界標準時間',true:'是',false:'否'};
const dateWord=v=>DATE_WORDS[String(v)]||v5Text(v);
function bundleStatus(s){$('bundleStatus').textContent=s;if($('draftStatus'))$('draftStatus').textContent=s;if(s.includes('失敗'))$('bundlePanel').open=true;}
function validBundle(b){return b&&typeof b.id==='string'&&typeof b.name==='string'&&Array.isArray(b.ids)&&b.ids.every(x=>typeof x==='string');}
function loadBundleStore(){try{const raw=localStorage.getItem(BUNDLE_KEY);if(raw){const d=JSON.parse(raw);if(d.version!==1||!d.edits||Array.isArray(d.edits)||typeof d.edits!=='object'||!Object.values(d.edits).every(validBundle)||!Array.isArray(d.custom)||!d.custom.every(validBundle)||!Array.isArray(d.locks)||!d.locks.every(l=>typeof l.package_id==='string'&&Array.isArray(l.ids)&&l.signatures&&typeof l.text==='string'))throw Error('格式損壞或版本不支援，保留原記錄');bundleStore=d;}}catch(e){bundleStorageOK=false;bundleStatus('讀取議題包失敗：'+errorText(e)+'。目前為唯讀，未覆蓋本機記錄。');}}
function saveBundleStore(next){if(!bundleStorageOK){bundleStatus('儲存失敗：本機記錄無法讀取，未覆蓋。');return false;}try{localStorage.setItem(BUNDLE_KEY,JSON.stringify(next));bundleStore=next;bundleStatus('已儲存在此瀏覽器。');return true;}catch(e){bundleStatus('儲存失敗：'+errorText(e)+'。變更未套用，請先複製開稿包。');return false;}}
function allBundles(){return [...DATA.bundleData.bundles.map(b=>({...b,...bundleStore.edits[b.id]})),...bundleStore.custom];}
function bundleRows(b){return b.ids.map(id=>archiveById.get(id)).filter(Boolean);}
function saveBundle(b){const next=structuredClone(bundleStore);if(DATA.bundleData.bundles.some(x=>x.id===b.id))next.edits[b.id]={id:b.id,name:b.name,ids:[...b.ids]};else{const i=next.custom.findIndex(x=>x.id===b.id);if(i<0)next.custom.push(b);else next.custom[i]=b;}if(saveBundleStore(next)){renderBundles();renderToday();if(draftInput?.bundle===b.id)openDraft(b.name,b.ids,b.id,false);return true;}return false;}
function metaFor(r){return DATA.draftMeta[r.id]||{};}
function suggest(rs){
 if(!rs.length)return {form:'未判定',reason:'尚未選取素材',role:'外電編譯'};
 const ms=rs.map(metaFor),bites=ms.some(m=>m.bite?.length),ctv=rs.filter(r=>metaFor(r).ctv),sources=new Set(rs.map(r=>r.src)),known=ms.every(m=>m.known);
 let form=ctv.length?'CTV':sources.size>=2&&bites?'SOT':known?'BS':'未判定';
 let reason=ctv.length?'A34：'+ctv.map(r=>r.code).join('、')+' 符合單一 story 條件；CTV 請擇一，其餘作參考':form==='SOT'?'A33：至少兩個來源，且有保存的 BITE':form==='BS'?'A33：單一來源或未保存合適引言':'部分素材缺少結構欄位，無法完整套用 A33／A34';
 const live=rs.filter(r=>/現場連線|記者連線|side-recording/i.test([...(metaFor(r).notes||[]),r.cat?.小分題||''].join(' '))).length>rs.length/2;
 const sport=rs.some(r=>(r.T||[]).includes('體育')||r.cat?.大分類==='體育');
 const role=live?'連線':sport?'體育':ms.some(m=>m.hilite)&&!bites?'影音':'外電編譯';
 return {form,reason,role,roleNote:live?'過半素材註記為現場連線':sport?'既有分類／標籤為體育':role==='影音'?'有畫面好標記且未保存引言':'突發傷亡需人工判斷；其餘按 A33 分派外電編譯'};
}
function shiftHas(r,day){const full=fullDay(day);return (r.obs||[]).some(o=>o.shift==='s2:'+full);}
function todayBundles(){const day=DATA.shifts[shift].day;return allBundles().map(b=>({b,rs:bundleRows(b).filter(r=>shiftHas(r,day))})).filter(x=>x.rs.length).sort((a,b)=>Number(b.b.shifts?.[day]?.qualifies||false)-Number(a.b.shifts?.[day]?.qualifies||false)||(b.b.shifts?.[day]?.score||0)-(a.b.shifts?.[day]?.score||0)||a.b.name.localeCompare(b.b.name,'zh-Hant')).slice(0,10);}
// common/05：文稿出現序、每碼獨立、同碼沿用、圖片獨立；側錄沿用六碼供 06 盤點。
function numberedMaterials(rs){
 let n=0,img=0;const seen=new Map(),gaps=[],rows=[],originals=[];
 const pattern=/\b(?:APcctv\d{6}|AP\d{7}|RTV?\d+|ENEX\d+|ABC\d+|[A-Z]{2,6}-\d{1,4}(?:MO|TU|WE|TH|FR|SA|SU)|(?:YNA|CNA|OTH)\d{2})\b|https?:\/\/[^\s<>）)。]+/g;
 const mediaURL=url=>/^https?:\/\/(?:www\.)?(?:youtube\.com|youtu\.be|facebook\.com|fb\.watch|x\.com|twitter\.com|dvidshub\.net)\//i.test(url);
 function mark(code){const normalized=code.replace(/^RTV(?=\d)/,'RT'),photo=/\/photo\/\d+/.test(code),plainSocial=/https?:\/\/(?:www\.)?(?:x|twitter)\.com\/[^/]+\/status\/\d+\/?$/.test(code);
  if(plainSocial){gaps.push('社群連結尚未人工確認影音／張數，不先編號：'+code);return {prefix:'',code:normalized};}
  if(seen.has(normalized)){gaps.push('同代碼重複：'+normalized+'，沿用 '+seen.get(normalized));return {prefix:'同'+seen.get(normalized)+' ',code:normalized};}
  const number=(photo?'圖#':'#')+String(photo?++img:++n).padStart(2,'0');seen.set(normalized,number);return {prefix:number+' ',code:normalized};
 }
 for(const r of rs){const m=metaFor(r),occ=[],text=r.text;
  // 只編素材識別碼／欄位列出的碼，以及文稿中的網址；不把內文巧合同形字當新素材。
  const allowed=new Set([r.code,...(m.codes||[])].filter(Boolean));
  let annotated=text.replace(pattern,(code,offset)=>{if(!allowed.has(code)&&!mediaURL(code))return code;const a=mark(code);occ.push({raw:code,...a});return a.prefix+a.code;});
  // URL 素材的新 YNA-/CNA-身分碼不冒充 common/05 舊兩碼流水號；依已保存影音 URL 編號。
  if(!occ.length&&r.kind!=='side'&&mediaURL(linkInfo(r).url)){const code=linkInfo(r).url,a=mark(code);occ.push({raw:code,...a});}
  if(!occ.length&&r.kind!=='side'&&r.code){const matches=r.code.match(pattern)||[];for(const code of matches){const a=mark(code);occ.push({raw:code,...a});}}
  const ref=occ.length?occ.map(o=>o.prefix+o.code+(/^AP5\d/.test(o.code)?' (SNTV)':'')).join(' / ')+(occ.every(o=>/^https?:/.test(o.code))?'｜代碼：'+r.code:''):(r.code||r.id);
  if(!occ.length&&r.kind!=='side')gaps.push('代碼格式待人工核對，尚未編號：'+(r.code||r.id));
  if(r.kind==='side')gaps.push((r.code||r.id)+'：側錄需掐 BITE，核對逐字稿與起訖時間碼');
  if(!r.md||!['embedded_verified','structured_source'].includes(r.q))gaps.push((r.code||r.id)+'：日期不確定（'+label('q',r.q)+'）');
  if(linkInfo(r).state==='none')gaps.push((r.code||r.id)+'：無連結，'+(r.lm||'需查原來源'));
  if(linkInfo(r).state==='search')gaps.push((r.code||r.id)+'：目前只有搜尋頁，需定位原素材');
  if(!m.bite?.length)gaps.push((r.code||r.id)+'：未保存可用 BITE，需查原文／影片');
  const notes=(m.notes||[]).join('、'),bite=Array.isArray(m.bite)?m.bite.join('、'):m.bite;
  rows.push(ref+'｜來源：'+(SRC[r.src]||r.src)+'｜素材日：'+(r.md||'未知')+'（'+label('q',r.q)+'；可信度'+dateWord(r.dc)+'）｜'+label('ls',linkInfo(r).state)+(linkInfo(r).url?' '+linkInfo(r).url:'')+(notes?'｜備註／使用限制：'+notes:'')+(bite?'｜可用 BITE：'+bite:''));
  originals.push(annotated);
 }
 return {rows,gaps:[...new Set(gaps)],originals};
}
function draftText(){if(!draftInput)return '';const rs=draftInput.ids.map(id=>archiveById.get(id)).filter(Boolean),info=suggest(rs),numbered=numberedMaterials(rs),title=$('draftTitle').value;
 const missing=draftInput.ids.filter(id=>!archiveById.has(id));numbered.gaps.push(...missing.map(id=>'本版缺少成員：'+id));
 const command=info.form==='SOT'?'自動寫稿(SOT)':info.form==='CTV'?'自動寫稿(CTV)':'協作寫稿模式';
 return '稿題暫名：'+title+'\n建議形式：'+info.form+'\n判定理由：'+info.reason+'\n分派角色：'+info.role+'（'+info.roleNote+'）\n\n素材清單（依包內／暫存清單順序）\n'+numbered.rows.join('\n')+'\n\n缺口檢查（不阻擋）\n'+(numbered.gaps.length?numbered.gaps.map(x=>'・'+x).join('\n'):'未發現上述缺口；仍需人工核對')+'\n\n交給寫稿\n'+command+'。稿題暫名「'+title+'」。請先按 common/05-material-numbering.md 核對下列完整清單，保留清單順序、同碼沿用編號、圖片另計；確認素材與限制並完成下載後，再依'+(info.form==='CTV'?' cnn/01-auto-script-writing.md 擇一合格 CNN Newsource story':' common/06-auto-script-sot.md 及既有寫稿流程')+'處理。先讀 common/auto-script-learning/INDEX.md 的有效規則。缺少的影音、官方文稿與 BITE 時間碼須補齊；不得把摘要當作可核對逐字稿，不得捏造畫面或引言。側錄以六碼盤點。分派只填角色。'+(info.form==='未判定'||info.form==='BS'?'先協作確認形式與大綱。':'')+'\n\n完整原始素材文字（僅插入編號；RTV 依規則正規化 RT）\n'+numbered.originals.join('\n\n');
}
function updateDraft(){if(!draftInput)return;const rs=draftInput.ids.map(id=>archiveById.get(id)).filter(Boolean),i=suggest(rs);$('draftAdvice').textContent=i.form+'｜'+i.reason+'｜分派：'+i.role;$('draftText').textContent=draftText();$('draftCopyText').value=$('draftText').textContent;}
function openDraft(name,ids,bundle=null,scroll=true){draftInput={name,ids:[...ids],bundle};$('draftPanel').hidden=false;$('draftPanel').open=true;$('draftTitle').value=name;updateDraft();renderLocks();if(scroll)$('draftPanel').scrollIntoView({block:'start'});}
function signature(id){const r=archiveById.get(id);return r?JSON.stringify([r,DATA.draftMeta[id]||null]):null;}
function lockChanged(l){return l.ids.some(id=>signature(id)!==l.signatures[id]);}
function renderLocks(){const root=$('draftLocks');root.replaceChildren();for(const l of [...bundleStore.locks].reverse()){const d=el('details','draft-lock');d.append(el('summary','',l.title+'｜'+l.created+'｜'+(lockChanged(l)?'已變動':'與鎖定資料一致')),el('p','bundle-hint',l.package_id+'｜'+l.ids.length+' 筆成員快照'),button('複製鎖定版本',()=>copy(l.text)));const p=el('pre');p.textContent=l.text;d.append(p);root.append(d);}}
