// v7 引用層：不改 DATA.archive／draftMeta；外部素材跟隨稿單保存。
const SP_RULES=Object.freeze({singleSource:1,sideRatio:0.5,penalty:12.5,sinceDays:DATA.supplementV7.sinceDays,previewLimit:10});
const spExternal=new Map();
const spCode=c=>c.replace(/^RTV(?=\d)/,'RT');
const spCodes=r=>(r.spCodes||metaFor(r).codes||[r.code]).map(spCode);
const spNotes=r=>[...(metaFor(r).notes||[]),...(r.text.match(/\([^)]*\)/g)||[])].join(' ');
const spStill=r=>/靜照|照片|截圖|still|screenshot/i.test(spNotes(r)+' '+(r.text.match(/▎畫面[：:]([^▎]*)/)||[])[1])&&!/動態|走動|起飛|爆炸瞬間/.test(spNotes(r));
const spVisual=r=>r.kind!=='side'&&!spStill(r)&&/▎畫面[：:]\s*[^▎\s]|畫面素材|B-ROLL/i.test(r.text)&&!/▎畫面[：:]\s*(無|未提供|待補|不明)/.test(r.text);
function spContext(d){return [d.topic,d.query,d.稿名,d.主軸,...rdRows(d).flatMap(r=>[...(r.T||[]),...(r.C||[]),...Object.values(r.cat||{}),r.text])].join(' ');}
function spAssess(d){
 const rs=rdRows(d),sources=new Set(rs.map(r=>r.src.replace(/^SIDE_/,'').replace(/^NS$/,'CNN'))),bites=rs.some(r=>rdBites(r).length),side=rs.filter(r=>r.kind==='side').length;
 const military=/軍事|前線|戰爭|空襲|飛彈|美軍|軍隊|戰場/.test(spContext(d));
 const rules=[
 ['source',sources.size<=SP_RULES.singleSource,'來源數 ≤ '+SP_RULES.singleSource,'補不同來源的現場畫面或說法'],
 ['bite',!bites,'全無可用 BITE 引言','找有講者與原文引言的素材；濃縮引言仍需核對逐字稿及 TC'],
 ['visual',!rs.some(spVisual),'全為靜照／側錄或未保存動態畫面證據','優先補動態畫面；截圖可支持聲明，不能代替現場'],
 ['link',rs.some(r=>linkInfo(r).state!=='direct'||/reutersconnect.*[?&]search=/.test(linkInfo(r).url)),'核心素材無連結或僅搜尋頁','逐支定位原始詳情頁（保守將已選素材都視為核心）'],
 ['side',rs.length>0&&side/rs.length>SP_RULES.sideRatio,'側錄占比超過 '+SP_RULES.sideRatio*100+'%','補正式外電現場畫面，側錄六碼留給掐 BITE'],
 ['date',rs.length>0&&rs.every(r=>!r.md||r.q==='ingestion_fallback'),'素材日全為暫列／未知','核對發布日與拍攝日，舊畫面標背景'],
 ['empty',!rs.length||d.segments.some(s=>!s.items.length),'某段落 0 素材','為空段落尋找對應素材'],
 ['sot',d.形式==='SOT'&&!bites,'形式為 SOT 但無可用 BITE','先補可核對引言，再確認 SOT 形式'],
 ['military',military&&!rs.some(spVisual),'軍事／前線議題無動態畫面證據','補現場或有日期的背景 B-ROLL；美軍議題可查 DVIDS']
 ];
 const hits=rules.filter(x=>x[1]).map(([id,_,reason,plan])=>({id,reason,plan}));
 return {score:Math.max(0,Math.round(100-hits.length*SP_RULES.penalty)),lacking:!!hits.length,count:rs.length,sources:sources.size,hits};
}
function spHealth(d){const a=spAssess(d),n=el('p','sp-health','素材充足度 '+a.score+'/100 · '+(a.lacking?'建議增補':'未命中不足規則')+(a.lacking?'\n'+a.hits.map(x=>x.reason).join('；'):'')+'\n規則提示不阻擋採用；不代表素材已查證。');n.dataset.lacking=String(a.lacking);return n;}
function spInventory(d){
 const rs=rdRows(d),ids=new Set(rs.map(r=>r.id)),used=new Set(rs.flatMap(spCodes)),bs=allBundles().filter(b=>b.id===d.bundle_id||b.ids.some(id=>ids.has(id))),bundleIds=new Set(bs.flatMap(b=>b.ids));
 const aliases=DATA.supplementV7.canonicalAliases.filter(g=>g.aliases.some(a=>[d.topic,...bs.map(b=>b.name),...rs.flatMap(r=>Object.values(r.cat||{}))].includes(a)));
 for(const r of DATA.archive)if(aliases.some(g=>g.aliases.some(a=>Object.values(r.cat||{}).includes(a))))bundleIds.add(r.id);
 const query=(d.query||d.topic||[...bs.map(b=>b.name),...rs.map(r=>r.cat?.中主題||'')].join(' ')||d.稿名).replace(/案(?=\s|$)/g,'');
 const hits=rdSearch(query),by=new Map(hits.map(h=>[h.id,h]));
 for(const id of bundleIds)if(!by.has(id)){const r=archiveById.get(id);if(r)by.set(id,{id,code:r.code,score:0,all:false,hits:0,reasons:[],date:r.md});}
 const latest=rs.flatMap(r=>(r.obs||[]).map(o=>o.shift)).sort().at(-1)||'s2:2026-10-03';
 const seen=new Set(used),result=[];
 for(const h of [...by.values()].sort((a,b)=>Number(b.all)-Number(a.all)||b.score-a.score||b.hits-a.hits||(b.date||'').localeCompare(a.date||'')||a.id.localeCompare(b.id))){const r=archiveById.get(h.id);if(ids.has(r.id)||spCodes(r).some(c=>seen.has(c)))continue;spCodes(r).forEach(c=>seen.add(c));const same=bundleIds.has(r.id),background=same&&(r.obs||[]).every(o=>o.shift<latest);result.push({...h,reasons:[...h.reasons,...(same?['同議題包／canonical']:[]),...(background?['前幾班同題背景，須核對拍攝日']:[])],background,shifts:[...new Set((r.obs||[]).map(o=>o.shift))]});}
 // 背景另優先列出；同組內完整沿用情境2的命中與排序。
 return result.sort((a,b)=>Number(b.background)-Number(a.background));
}
function spAddInventory(id){const d=rdDraft(),h=spInventory(d).find(h=>h.id===id);if(!h)return;const r=archiveById.get(id);spTarget(d).items.push({material_id:id,用途:'【增補｜庫存增補'+(h.background?'｜背景':'')+'】原班次：'+h.shifts.join('、')+'；'+h.reasons.join('；'),includeOriginal:false,supplement:{source:'庫存增補',shifts:h.shifts,background:h.background}});d.bites.push(...rdBites(r).filter(b=>!d.bites.some(x=>x.material_id===id&&x.text===b.text)));rdSave();rdRenderCards();rdRenderEditor();$('spPanel').open=true;}
function spTarget(d){if(!d.segments.length)d.segments.push({title:'增補素材',note:'',items:[]});return d.segments[Number(d.spTarget)||0]||d.segments[0];}
function spEnglish(d){if(typeof d.supplementEnglish==='string')return d.supplementEnglish;const preset=DATA.supplementV7.candidateEnglish[d.id];if(preset)return preset;
 // 僅擷取原文已出現的拉丁字專名候選；不翻譯中文，不把通用格式標記當人名。
 const found=rdRows(d).flatMap(r=>r.text.match(/\b(?:[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?(?:[ -](?:[A-Z][a-z]+|al-[A-Z][a-z]+)){0,3}|[A-Z]{2,8})\b/g)||[]);
 return [...new Set(found.filter(s=>!/^(AP|RTV?|CNN|ENEX|ABC|BITE|SOT|OS|TC|STAND|LIVE|UGC|FILE|CCTV|CGTN|SNTV|NS)$/.test(s)))].slice(0,16).join(' ');
}
// 議題分組只看稿名／主軸／議題／T/C／分類，不看素材全文（全文常順帶提及他區，曾把北韓飛彈誤配中東來源）
function spTopicContext(d){return [d.topic,d.query,d.稿名,d.主軸,...rdRows(d).flatMap(r=>[...(r.T||[]),...(r.C||[]),...Object.values(r.cat||{})])].join(' ');}
function spGroups(d){const t=spTopicContext(d),g=['all'];if(/烏克蘭|烏俄|俄烏|俄打烏|Ukraine|Ukrain/i.test(t))g.push('ukraine');if(/中東|美伊|伊朗|杜拜|加薩|以色列|葉門|沙烏地|伊拉克/.test(t))g.push('mideast');if(/南韓|北韓|南北韓|朝鮮|Korea/i.test(t))g.push('korea');if(/美軍|美國軍|美國海軍|美國空軍|美國陸軍|CENTCOM|U\.S\. (?:military|Army|Navy|Air Force)/i.test(t))g.push('usmilitary');return g;}
const SP_REMIND='務必點進原頁核對發布日期與拍攝日。AP third-party／stringer 非純數字 ID、需扣點者只列候選不收；SNTV 可收並標 (SNTV)。社群備註「社群素材非官方外電，需注意版權與查證」；通訊社 YouTube 頻道標非母帶；DVIDS 視為正式素材。';
function spTask(d){const dates=rdRows(d).map(r=>r.md).filter(v=>/^\d{4}-\d{2}-\d{2}$/.test(v||'')).sort(),since=dates.length?new Date(Date.parse(dates[0]+'T00:00:00Z')-SP_RULES.sinceDays*86400000).toISOString().slice(0,10):'{YYYY-MM-DD待填}',zh=d.supplementChinese??(d.query||d.topic||d.稿名),en=spEnglish(d),q=en||zh;
 const tasks=[{name:'AP Newsroom｜Video',url:'https://newsroom.ap.org/home/search?query='+encodeURIComponent(q)+'&mediaType=video',note:'選 Search with keywords（不用 with AI），切 Video，從卡片展開完整詳情；Metadata／Shotlist 核對 ID、Provided By、Restrictions 與 BITE。'},
 {name:'Reuters Connect｜Video',url:'https://www.reutersconnect.com/all?media-types=vid&search=all%3A'+encodeURIComponent(q),note:'確認 My Subscription ON；Video 分頁按標題選素材，進詳情取 Edit No.、Restrictions、Shotlist；需要 TC 再看 Video Transcript。'},
 {name:'CNN Newsource',url:'https://newsource.ns.cnn.com/',note:'先瀏覽左側 TRENDING 分類，再在首頁右上搜尋框輸入自由關鍵字「'+q+'」；兩種都做，不使用 ?search= 網址。'}];
 const fallback=DATA.supplementV7.fallbacks.filter(s=>spGroups(d).includes(s.group)).map(s=>({...s,note:s.note+(s.account?'\nX 搜尋：from:'+s.account+' '+q+' since:'+since:s.name.startsWith('YouTube')?'\n頻道影片分頁排最新／頻道內搜尋；排除 LIVE。通訊社／新聞台頻道畫面非母帶。':'')}));
 return {zh,en,since,tasks,fallback};
}
function spPrompt(d=rdDraft()){const t=spTask(d),a=spAssess(d);return '請使用 Claude in Chrome 執行增補素材。先全文讀 common/11-wire-rundown-organizer.md、common/05-material-numbering.md，並依 ap/01-search-workflow.md 與 reuters/01-search-workflow.md 操作。取材優先序：①既有庫存（本次發布全庫、跨班跨日）→②AP／RT／CNN Newsource→③備援來源；前階段足夠就停止。不得把摘要引言冒充逐字稿，不捏造 TC；發布／拍攝日、Restrictions、背景與用途需保留。\n\n稿單現況\n'+rdText(d)+'\n\n不足原因與建議方案（'+a.score+'/100）\n'+a.hits.map(h=>h.reason+' → '+h.plan).join('\n')+'\n\n中文關鍵字：'+t.zh+'\n英文關鍵字：'+(t.en||'〔未抽得原文英文專名，請主管填寫；勿自造翻譯〕')+'\n英文來源：'+(DATA.supplementV7.candidateEnglish[d.id]?'建置時預寫（主管可改）':'僅擷取素材原文專名候選（主管需核對）')+'\nsince：'+t.since+'（最早素材日往前 '+SP_RULES.sinceDays+' 天；暫列日須核對）\n\n② 通訊社搜尋\n'+t.tasks.map(s=>s.name+'\n'+s.url+'\n'+s.note+'\n提醒：'+SP_REMIND).join('\n\n')+'\n\n③ 通訊社查無後的備援來源\n'+t.fallback.map(s=>s.name+'\n'+s.url+'\n'+s.note+'\n提醒：'+SP_REMIND).join('\n\n')+'\n\n回傳格式（每行一則；不先編 #XX）：\n{代碼} ({備註}) [(BITE)] {短摘要}▎畫面：…▎BITE：「…」或 ▎無BITE。\n多碼以「 / 」相接；RTV 改 RT。日期與來源連結寫在備註；保留限制、SNTV、背景／資料畫面、社群查證提醒。側錄寫來源＋日期＋六碼，不占一般編號。X 純 status 先確認影音數量，每個 video/N 或 photo/N 分行列出；只有文字當參考。ENEX／ABC 只編號，勿猜下載路由。AP stringer 另列候選供主管決定。無法核對與矛盾另列，勿刪未辨識內容。';}
function spParse(text){return text.split(/\r?\n/).map((raw,index)=>{const line=raw.trim();if(!line)return {raw,index,status:'blank'};
 const start=line.replace(/^(?:同)?(?:圖)?#\d+\s*/,'');
 if(/^(?:AP\s*)?(?:vrb|stltd|un)\d+\b/i.test(start)||/^AP\s*[a-z]+\d+/i.test(start)&&!/^APcctv\d{6}\b/i.test(start))return {raw,index,status:'candidate',message:'只列候選、需主管決定（AP third-party／stringer，不自動加入）'};
 const token=/^(?:APcctv\d{6}|AP\d{7}|RTV?\d+|ENEX\d+|ABC\d+|[A-Z]{2,6}-\d{1,4}(?:MO|TU|WE|TH|FR|SA|SU)|(?:CNN|NHK|BBC|CNA|TVBS|ABC)\s+(?:\d{2}-\d{2}\s+)?\d{6}|(?:X|YouTube|DVIDS)\s+https?:\/\/[^\s<>]+|https?:\/\/[^\s<>]+|\d{7})(?=\s|$)/;
 let rest=start,codes=[],incomplete=false;while(true){const m=rest.match(token);if(!m){incomplete=true;break;}let code=m[0];const url=code.match(/https?:\/\/\S+/)?.[0];if(url){try{const u=new URL(url);if(!/^(?:www\.)?(?:x\.com|twitter\.com|youtube\.com|youtu\.be|dvidshub\.net)$/.test(u.hostname))break;if(/(?:x|twitter)\.com$/.test(u.hostname)&&!/^\/[^/]+\/status\/\d+(?:\/(?:video|photo)\/\d+)?\/?$/.test(u.pathname))break;if(u.hostname.endsWith('dvidshub.net')&&!u.pathname.startsWith('/video/'))break;if(/youtube\.com$/.test(u.hostname)&&!(/^\/(?:watch|shorts\/|live\/)/.test(u.pathname)))break;}catch{break;}code=url;}else if(/^\d{7}$/.test(code))code='AP'+code;codes.push(spCode(code));rest=rest.slice(m[0].length).trimStart();if(rest.startsWith('/ '))rest=rest.slice(2).trimStart();else break;}
 if(!codes.length||incomplete||codes.length>1&&codes.some(c=>/^[A-Z]+\s+(?:\d{2}-\d{2}\s+)?\d{6}$/.test(c)))return {raw,index,status:'unknown',message:'無法辨識；原行保留，請修正代碼／網址或補上側錄來源'};
 // 限制、備註、畫面與引言逐字保留；僅識別碼正規化。
 let notes=[...(rest.match(/\([^)]*\)/g)||[])].map(x=>x.slice(1,-1));if(codes.some(c=>/^AP5/.test(c))&&!notes.includes('SNTV'))notes.push('SNTV');
 if(codes.some(c=>/^https?:\/\/(?:www\.)?(?:x|twitter)\.com/.test(c)))notes.push('社群素材非官方外電，需注意版權與查證');
 if(codes.some(c=>/youtu/.test(c)))notes.push('YouTube 頻道畫面，非母帶；需核對版權與查證');
 const side=/^[A-Z]+\s+(?:\d{2}-\d{2}\s+)?\d{6}$/.test(codes[0]);const src=side?'SIDE_'+codes[0].split(' ')[0]:/^AP/.test(codes[0])?'AP':/^RT/.test(codes[0])?'RT':/^ENEX/.test(codes[0])?'ENEX':/^ABC/.test(codes[0])?'ABC':/^[A-Z]{2,6}-/.test(codes[0])?'NS':/dvidshub/.test(codes[0])?'DVIDS':/youtu/.test(codes[0])?'YouTube':'X';
 const row={id:'sp-external-'+crypto.randomUUID(),code:codes.join(' / '),spCodes:codes,src,kind:side?'side':'wire',text:codes.join(' / ')+(rest?' '+rest:''),link:codes.find(c=>/^https?:/.test(c))||(rest.match(/https?:\/\/[^\s)]+/)||[])[0]||'',md:null,q:'ingestion_fallback',T:[],C:[],cat:{},obs:[],spNotes:notes,spRaw:raw};
 return {raw,index,status:'recognized',message:'可辨識｜'+src+(side?'｜側錄不編號':'')+(src==='X'?(codes.some(c=>/\/(video|photo)\/\d+$/.test(c))?'｜明確影音路徑，依附件類型編號':'｜純 status 待確認附件後才編號'):''),row};
 });}
function spRegister(r){spExternal.set(r.id,r);archiveById.set(r.id,r);}
function spAddParsed(){const d=rdDraft(),parsed=spParse(d.supplementPaste||''),used=new Set(rdRows(d).flatMap(spCodes));let count=0;d.supplementRows=d.supplementRows||[];for(const p of parsed){if(p.status!=='recognized'||p.row.spCodes.some(c=>used.has(c)))continue;const r=p.row;r.spCodes.forEach(c=>used.add(c));d.supplementRows.push(r);spRegister(r);spTarget(d).items.push({material_id:r.id,用途:'【增補｜外部增補】'+r.spNotes.map(n=>'('+n+')').join(' ')+' '+r.text,includeOriginal:false,supplement:{source:'外部增補'}});d.bites.push(...rdBites(r));count++;}rdSave();rdRenderCards();rdRenderEditor();$('spPanel').open=true;$('spFeedback').textContent='已加入 '+count+' 則；同碼略過。候選與無法辨識行仍保留在貼上區。';}
function spPreview(){const d=rdDraft(),root=$('spPreview');root.replaceChildren();for(const p of spParse(d.supplementPaste||'')){if(p.status==='blank')continue;const li=el('li',p.status==='recognized'?'sp-state':'sp-unrecognized');li.append(el('strong','',String(p.index+1)+'. '+p.message),el('pre','',p.raw));root.append(li);} $('spConfirm').disabled=!spParse(d.supplementPaste||'').some(p=>p.status==='recognized');}
function spRender(){const d=rdDraft();if(!d)return;const section=el('section');section.id='spSection';section.append(spHealth(d));const open=button('增補素材',run(async()=>{onlineNotice('讀取跨班庫存供增補…');await loadInventory();onlineNotice('');rdRenderEditor();$('spPanel').open=true;$('spPanel').scrollIntoView({block:'start'});}));open.id='spOpen';section.append(open);const panel=el('details','sp-panel');panel.id='spPanel';panel.append(el('summary','','補充素材｜先查庫存，再交付搜尋任務'),el('p','rd-meta','頁面不連外、不呼叫 LLM。檢查只作提示，素材使用仍由主管決定。'));
 const plans=el('ul');for(const h of spAssess(d).hits)plans.append(el('li','',h.reason+' → '+h.plan));panel.append(plans);
 rdSelect(panel,'增補加入段落',d.segments.map((s,i)=>[String(i),s.title]),String(d.spTarget||0),v=>{d.spTarget=Number(v);rdSave();},'spTarget');
 panel.append(el('h4','','① 庫存增補（按需載入跨班素材）'));const hits=spInventory(d),list=el('ul','sp-list'),limit=d.spShowAll?hits.length:SP_RULES.previewLimit;panel.append(el('p','rd-meta',hits.length+' 筆未收素材；沿用指定議題檢索排序，排除同碼。背景優先（同組沿用原排序），目前列 '+Math.min(limit,hits.length)+' 筆；舊班同題標背景，使用前仍需核對是否同一事件。'));for(const h of hits.slice(0,limit)){const r=archiveById.get(h.id),li=el('li');li.append(el('strong','',r.code+(h.background?' · 背景':'')),el('p','rd-meta','原班次 '+h.shifts.join('、')+'｜素材日 '+(r.md||'未知')),el('p','',h.reasons.join('；')));const raw=el('details');raw.append(el('summary','','原文（唯讀）'),el('pre','',r.text));li.append(raw,button('加入增補',()=>spAddInventory(r.id),'sp-add'));list.append(li);}if(!hits.length)list.append(el('li','','庫存未找到可加入素材，請產生通訊社搜尋任務。'));panel.append(list);if(hits.length>SP_RULES.previewLimit)panel.append(button(d.spShowAll?'收合庫存建議':'顯示全部 '+hits.length+' 筆',()=>{d.spShowAll=!d.spShowAll;rdRenderEditor();$('spPanel').open=true;}));
 panel.append(el('h4','','② 通訊社搜尋 → ③ 備援來源'));
 rdField(panel,'中文關鍵字',spTask(d).zh,v=>{d.supplementChinese=v;rdSave();spRefreshTask();},'input','spChinese');rdField(panel,'英文關鍵字（未抽得時可留空，主管填寫）',spEnglish(d),v=>{d.supplementEnglish=v;rdSave();spRefreshTask();},'input','spEnglish');panel.append(el('p','rd-meta',DATA.supplementV7.candidateEnglish[d.id]?'英文由建置時預寫；可依角度調整。':'英文只擷取原文專名候選，不自造翻譯；請核對是否為人名、地名或機構。'));
 const tasks=el('div');tasks.id='spTasks';panel.append(tasks);const prompt=el('details');prompt.append(el('summary','','交給 Claude 執行增補｜完整指令'));const pre=el('pre');pre.id='spPrompt';prompt.append(pre);panel.append(button('交給 Claude 執行增補',()=>copy(spPrompt(d)),'sp-copy'),prompt);
 panel.append(el('h4','','貼上增補結果'));rdField(panel,'素材行（無法辨識內容會保留）',d.supplementPaste||'',v=>{d.supplementPaste=v;rdSave();spPreview();},'textarea','spPaste');const preview=el('ul','sp-list');preview.id='spPreview';panel.append(preview);const confirm=button('確認加入可辨識素材',spAddParsed);confirm.id='spConfirm';panel.append(confirm);const feedback=el('p','rd-status');feedback.id='spFeedback';feedback.setAttribute('role','status');panel.append(feedback);section.append(panel);$('rdEditor').insertBefore(section,$('rdEditor').children[2]);spRefreshTask();spPreview();}
function spRefreshTask(){const d=rdDraft(),t=spTask(d),root=$('spTasks');if(!root)return;root.replaceChildren();for(const [title,rows] of [['通訊社',t.tasks],['備援（通訊社查無再做）',t.fallback]]){const details=el('details');details.append(el('summary','',title+' · '+rows.length+' 個入口'));for(const s of rows){const article=el('div','sp-panel'),a=el('a','',s.name);a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';article.append(a,el('p','',s.note),el('p','rd-meta',SP_REMIND));details.append(article);}root.append(details);}$('spPrompt').textContent=spPrompt(d);}
const spOldMeta=metaFor;metaFor=function(r){return spExternal.has(r.id)?{known:true,codes:r.spCodes,notes:r.spNotes,bite:rdBites(r).map(b=>b.text)}:spOldMeta(r);};
const spOldLoad=rdLoad;rdLoad=function(){try{const saved=JSON.parse(localStorage.getItem(RD_KEY)||'null');for(const d of Object.values(saved?.drafts||{}))for(const r of d.supplementRows||[]){if(!r||typeof r.id!=='string'||!r.id.startsWith('sp-external-')||typeof r.text!=='string'||typeof r.code!=='string'||!Array.isArray(r.spCodes)||!r.spCodes.every(c=>typeof c==='string')||!Array.isArray(r.spNotes)||!r.spNotes.every(n=>typeof n==='string'))throw Error('外部增補記錄損壞');spRegister(r);}}catch(e){rdReadable=false;}spOldLoad();if(!rdReadable)rdMessage('讀取稿單失敗：本機資料無法讀取，未覆蓋。請複製備份。',true);};
const spOldCards=rdRenderCards;rdRenderCards=function(){spOldCards();for(const c of DATA.rundownV6.candidates){const card=document.querySelector('[data-candidate="'+c.id+'"]');if(card)card.append(spHealth(rdStore.drafts[c.id]||c));}};
const spOldEditor=rdRenderEditor;rdRenderEditor=function(){spOldEditor();spRender();};
const spOldUpdate=rdUpdate;rdUpdate=function(){spOldUpdate();if(rdDraft()&&$('spSection')){const opened=$('spPanel').open;$('spSection').remove();spRender();$('spPanel').open=opened;}};
