# -*- coding: utf-8 -*-
"""晚班交接 HTML 檢視版——搜尋／篩選／分層複製（2026-08-09）。

**這是第二個投影，不是第二份真相。** WP1 之後 txt 已經是「從狀態檔全量渲染」，
這支只是多一個輸出目標：

    狀態檔（唯一真相源）
      ├─→ s2_render.py  → 晚班交接.txt   ← 權威產物，品質掃驗的是它
      └─→ 本支            → 晚班交接.html ← 純檢視層，衍生物

⛔ **絕不重寫排版邏輯**：分組、時段標記、素材行文字全部直接呼叫 `s2_render`
的現成函式（`group_items`／`render_item`／`mark_for`）。HTML 顯示的每一行
**與 txt 逐字相同**——所以複製出去貼到別的系統不會有格式差異，
也不會出現「兩份輸出各自演化」的維護地獄（`13b` 立案時就點名這個風險）。

使用情境（2026-08-09 使用者說明）：
  1. 編輯先在畫面上看整份列表
  2. 拆分派稿單給記者時**複製貼到別的系統**——顆粒度是「單則素材」或
     「整個中主題／小分題一起」，所以三種層級都要有複製鈕。

⚠️ **Google Drive 網頁預覽不會執行 JS**，篩選會失效。要開本機同步的那份
（`G:\\我的雲端硬碟\\...`），雙擊即可。

用法：
  python scripts/s2_render_html.py --file <state.json> --out <晚班交接.html>
  省略 --out 就印到 stdout。
"""
import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render as R  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def collect(state, base_mmdd):
    """把狀態檔攤成 HTML 要的扁平結構。

    每一則都帶著 `text`＝**txt 裡那一行的逐字內容**（複製出去就是它），
    外加篩選要用的欄位。分組順序完全交給 `R.group_items()`，不自己排。
    """
    rows = []
    for big, mids in R.group_items(state, base_mmdd).items():
        for mid, subs in mids.items():
            for sub, its in subs.items():
                for it in its:
                    lines = R.render_item(it, base_mmdd)
                    if not lines:
                        continue
                    text = "\n".join(lines)
                    f = it.get("fields") or {}
                    rows.append({
                        "big": big or "", "mid": mid or "", "sub": sub or "",
                        "id": it.get("id") or "",
                        "src": it.get("source") or "",
                        "mark": R.mark_for(it.get("first_seen_checkpoint") or "", base_mmdd) or "",
                        "cp": it.get("first_seen_checkpoint") or "",
                        "dur": f.get("duration") or "",
                        "bite": bool(f.get("bite")),
                        "text": text,
                        # 搜尋用：把使用者可能會想找的字全串起來，前端只比對這一欄
                        "q": " ".join([
                            it.get("id") or "", f.get("summary") or "",
                            f.get("footage") or "", " ".join(f.get("notes") or []),
                            " ".join(f.get("bite") or []), text,
                        ]).lower(),
                    })
    return rows


def build_header(state, base_mmdd, window):
    """檔頭沿用 txt 的前幾行，不另外算——數字只有一個來源。"""
    text = R.render(state, window, base_mmdd, "")
    head = []
    for ln in text.split("\n"):
        if ln.startswith("======"):
            break
        if ln.strip():
            head.append(ln)
    return head


TEMPLATE = """<!doctype html>
<html lang="zh-Hant"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--card:#fafafa;
      --accent:#0b62d0;--chip:#eef2f7;--chipon:#0b62d0;--warn:#c00}
@media (prefers-color-scheme:dark){
:root{--bg:#16181c;--fg:#e8e8e8;--mut:#9aa0a6;--line:#2c3038;--card:#1d2026;
      --accent:#6aa9ff;--chip:#252a32;--chipon:#2b6cb0;--warn:#ff6b6b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.7 "Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif}
header{position:sticky;top:0;z-index:9;background:var(--bg);
       border-bottom:1px solid var(--line);padding:10px 14px}
h1{font-size:17px;margin:0 0 2px}
.meta{color:var(--mut);font-size:13px;white-space:pre-wrap}
.alert{color:var(--warn);font-weight:600}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}
input[type=search]{flex:1;min-width:180px;padding:7px 10px;font-size:14px;
  border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.chip{padding:4px 10px;font-size:13px;border:1px solid var(--line);border-radius:14px;
      background:var(--chip);color:var(--fg);cursor:pointer;user-select:none}
.chip.on{background:var(--chipon);color:#fff;border-color:var(--chipon)}
.count{color:var(--mut);font-size:13px;margin-left:auto}
button.act{padding:4px 10px;font-size:12px;border:1px solid var(--line);
  border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button.act:hover{border-color:var(--accent);color:var(--accent)}
main{padding:6px 14px 60px}
.big{margin:18px 0 6px;padding-bottom:3px;border-bottom:2px solid var(--line);
     font-size:15px;font-weight:700;letter-spacing:.5px}
.mid{margin:12px 0 4px;font-weight:700;color:var(--accent)}
.sub{margin:8px 0 2px;color:var(--mut);font-size:13px}
.hd{display:flex;align-items:center;gap:8px}
.hd button{visibility:hidden}
.hd:hover button{visibility:visible}
.item{display:flex;gap:8px;padding:6px 8px;border:1px solid transparent;
      border-radius:6px;align-items:flex-start}
.item:hover{background:var(--card);border-color:var(--line)}
.item .txt{flex:1;white-space:pre-wrap;word-break:break-word}
.mark{flex:none;width:1.4em;text-align:center;font-size:15px}
.item button{visibility:hidden;flex:none}
.item:hover button{visibility:visible}
.hide{display:none}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);
  background:var(--accent);color:#fff;padding:7px 16px;border-radius:16px;
  font-size:13px;opacity:0;transition:.2s;pointer-events:none}
.toast.on{opacity:1}
</style></head><body>
<header>
  <h1>__H1__</h1>
  <div class="meta">__META__</div>
  <div class="bar">
    <input type="search" id="q" placeholder="搜尋代碼、摘要、畫面、BITE…">
    <span id="cnt" class="count"></span>
  </div>
  <div class="bar" id="fsrc"></div>
  <div class="bar" id="fmark"></div>
  <div class="bar" id="fbig"></div>
  <div class="bar">
    <button class="act" id="copyAll">複製目前篩選結果</button>
    <button class="act" id="reset">清除篩選</button>
  </div>
</header>
<main id="list"></main>
<div class="toast" id="toast"></div>
<script>
const ROWS = __ROWS__;
const MARK_LABEL = {"△":"△ 晚班既有","▲":"▲ 無人值守","■":"■ 晨班","◆":"◆ 早班"};
const F = {src:new Set(), mark:new Set(), big:new Set(), q:""};

function uniq(k){return [...new Set(ROWS.map(r=>r[k]).filter(Boolean))];}

function chips(host, key, vals, label){
  const el = document.getElementById(host);
  vals.forEach(v=>{
    const b = document.createElement('span');
    b.className='chip'; b.textContent = label ? (label[v]||v) : v;
    b.onclick = ()=>{ F[key].has(v) ? F[key].delete(v) : F[key].add(v);
                      b.classList.toggle('on'); draw(); };
    el.appendChild(b);
  });
}

function pass(r){
  if(F.src.size && !F.src.has(r.src)) return false;
  if(F.mark.size && !F.mark.has(r.mark)) return false;
  if(F.big.size && !F.big.has(r.big)) return false;
  if(F.q && !r.q.includes(F.q)) return false;
  return true;
}

function toast(m){const t=document.getElementById('toast');
  t.textContent=m; t.classList.add('on'); setTimeout(()=>t.classList.remove('on'),1300);}

function copy(text, msg){
  navigator.clipboard.writeText(text).then(()=>toast(msg))
    .catch(()=>{ // file:// 下 clipboard API 可能被擋，退回舊招
      const ta=document.createElement('textarea'); ta.value=text; document.body.appendChild(ta);
      ta.select(); document.execCommand('copy'); ta.remove(); toast(msg); });
}

function btn(label, fn){
  const b=document.createElement('button'); b.className='act'; b.textContent=label;
  b.onclick=e=>{e.stopPropagation(); fn();}; return b;
}

function draw(){
  const list=document.getElementById('list'); list.innerHTML='';
  const rows=ROWS.filter(pass);
  document.getElementById('cnt').textContent=`${rows.length} / ${ROWS.length} 則`;
  // 分組時保持 ROWS 的原順序（那就是 txt 的順序）
  const tree=new Map();
  rows.forEach(r=>{
    if(!tree.has(r.big)) tree.set(r.big,new Map());
    const m=tree.get(r.big);
    if(!m.has(r.mid)) m.set(r.mid,new Map());
    const s=m.get(r.mid);
    if(!s.has(r.sub)) s.set(r.sub,[]);
    s.get(r.sub).push(r);
  });
  tree.forEach((mids,big)=>{
    const bh=document.createElement('div'); bh.className='big hd';
    bh.append(document.createTextNode(`======${big}======`));
    const all=[...mids.values()].flatMap(s=>[...s.values()].flat());
    bh.append(btn(`複製整格（${all.length}）`,()=>copy(blockText(big,mids),`已複製「${big}」${all.length} 則`)));
    list.append(bh);
    mids.forEach((subs,mid)=>{
      if(mid){
        const mh=document.createElement('div'); mh.className='mid hd';
        mh.append(document.createTextNode(`【${mid}】`));
        const n=[...subs.values()].flat().length;
        mh.append(btn(`複製（${n}）`,()=>copy(midText(mid,subs),`已複製「${mid}」${n} 則`)));
        list.append(mh);
      }
      subs.forEach((its,sub)=>{
        if(sub){
          const sh=document.createElement('div'); sh.className='sub hd';
          sh.append(document.createTextNode(sub));
          sh.append(btn(`複製（${its.length}）`,()=>copy(subText(sub,its),`已複製「${sub}」${its.length} 則`)));
          list.append(sh);
        }
        its.forEach(r=>{
          const d=document.createElement('div'); d.className='item';
          const mk=document.createElement('span'); mk.className='mark'; mk.textContent=r.mark;
          const tx=document.createElement('div'); tx.className='txt';
          tx.textContent=r.text.replace(/^\\s*[△▲■◆●]\\s*/,'');
          d.append(mk,tx,btn('複製',()=>copy(r.text,`已複製 ${r.id}`)));
          list.append(d);
        });
      });
    });
  });
  if(!rows.length){
    const e=document.createElement('div'); e.className='sub';
    e.textContent='沒有符合條件的素材。'; list.append(e);
  }
}

// 以下三個組字串的函式，輸出格式與 txt 完全一致（小分題之間用 +）
function subText(sub,its){return (sub?sub+"\\n":"")+its.map(r=>r.text).join("\\n");}
function midText(mid,subs){
  const parts=[...subs.entries()].map(([s,i])=>subText(s,i));
  return (mid?`【${mid}】\\n`:"")+parts.join("\\n+\\n");
}
function blockText(big,mids){
  const parts=[...mids.entries()].map(([m,s])=>midText(m,s));
  return `======${big}======\\n\\n`+parts.join("\\n\\n");
}

document.getElementById('q').oninput=e=>{F.q=e.target.value.trim().toLowerCase();draw();};
document.getElementById('copyAll').onclick=()=>{
  const rows=ROWS.filter(pass);
  copy(rows.map(r=>r.text).join("\\n"),`已複製篩選結果 ${rows.length} 則`);
};
document.getElementById('reset').onclick=()=>{
  F.src.clear();F.mark.clear();F.big.clear();F.q="";
  document.getElementById('q').value="";
  document.querySelectorAll('.chip.on').forEach(c=>c.classList.remove('on'));
  draw();
};
chips('fsrc','src',uniq('src'));
chips('fmark','mark',uniq('mark'),MARK_LABEL);
chips('fbig','big',uniq('big'));
draw();
</script></body></html>
"""


def build_html(state, base_mmdd, window):
    head = build_header(state, base_mmdd, window)
    rows = collect(state, base_mmdd)
    title = head[0] if head else "晚班交接"
    meta = "\n".join(head[1:])
    alerts = [h for h in head[1:] if h.startswith("🔴")]
    meta_html = html.escape(meta)
    for a in alerts:                       # 重大提醒要跳出來，不要跟一般檔頭同色
        meta_html = meta_html.replace(html.escape(a),
                                      f'<span class="alert">{html.escape(a)}</span>')
    return (TEMPLATE
            .replace("__TITLE__", html.escape(title))
            .replace("__H1__", html.escape(title))
            .replace("__META__", meta_html)
            .replace("__ROWS__", json.dumps(rows, ensure_ascii=False)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=R.DEFAULT_FILE, help="狀態檔路徑")
    p.add_argument("--out", help="輸出 html 路徑（省略＝印到 stdout）")
    p.add_argument("--base-date", default="", help="晚班當天 MMDD；省略自動推得")
    p.add_argument("--window", default="", help="時間窗；省略取狀態檔算出的累計窗")
    args = p.parse_args()

    state = R.load_state(args.file)
    base = args.base_date
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        base = m.group(1) if m else state.get("date", "")
    win = args.window or R.window_from_state(state, base) or state.get("window_local", "")
    out = build_html(state, base, win)

    if not args.out:
        sys.stdout.write(out)
        return
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    n = out.count('"id":')
    print(f"OK 已產出 {args.out}（{n} 則 / {len(out)} 字元）")
    print("⚠️ 從 Google Drive 網頁預覽開不會執行 JS，要開本機同步的那份檔案。")


if __name__ == "__main__":
    main()
