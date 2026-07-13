#!/usr/bin/env python3
"""產出單檔 data/dashboard.html：每集摘要 / 標的追蹤 / 產業追蹤 三個分頁。"""
import json

from common import ANALYSES, DATA, TRANSCRIPTS

TEMPLATE = """<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>股癌 Podcast 追蹤器</title><style>
:root{--bg:#111418;--card:#1b2027;--fg:#e6e9ee;--dim:#8a93a3;--acc:#4da3ff;
--bull:#e05656;--bear:#39b56a;--flat:#8a93a3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 "Noto Sans TC",system-ui,sans-serif}
header{padding:14px 20px;border-bottom:1px solid #2a303a;display:flex;gap:16px;
align-items:baseline;flex-wrap:wrap}
h1{font-size:18px;margin:0}#meta{color:var(--dim);font-size:12px}
nav button{background:none;border:1px solid #2a303a;color:var(--fg);padding:6px 14px;
border-radius:6px;cursor:pointer;font-size:14px}
nav button.on{background:var(--acc);border-color:var(--acc);color:#08131f}
main{max-width:1080px;margin:0 auto;padding:16px 20px}
input{width:100%;max-width:360px;background:var(--card);border:1px solid #2a303a;
color:var(--fg);padding:8px 12px;border-radius:6px;margin-bottom:12px}
.card{background:var(--card);border:1px solid #2a303a;border-radius:10px;
padding:14px 16px;margin-bottom:12px}
.card h3{margin:0 0 6px;font-size:16px}.dim{color:var(--dim);font-size:12px}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;
margin-right:6px;border:1px solid}
.看多,.持有中{color:var(--bull);border-color:var(--bull)}
.看空,.已出場{color:var(--bear);border-color:var(--bear)}
.中性,.觀察{color:var(--flat);border-color:var(--flat)}
details{margin-top:6px}summary{cursor:pointer;color:var(--acc);font-size:13px}
.tl{margin:6px 0 0;padding-left:0;list-style:none}
.tl li{padding:6px 0;border-top:1px dashed #2a303a;font-size:14px}
ul.plain{margin:6px 0;padding-left:18px}
.disc{color:var(--dim);font-size:11px;padding:20px;text-align:center}
.lock{max-width:420px;margin:40px auto;text-align:center}
.lock h2{font-size:18px;margin-bottom:8px}
.lock p.dim{margin-bottom:16px}
.lock input{display:block;margin:0 auto 10px}
.lock input.mask{-webkit-text-security:disc}
.lock details{margin:10px 0;text-align:left;color:var(--dim);font-size:13px}
.lock summary{cursor:pointer;color:var(--acc)}
.lock button.go{background:var(--acc);color:#08131f;border:none;padding:8px 22px;
border-radius:6px;cursor:pointer;font-size:14px;margin-top:6px}
.chatwrap{display:flex;flex-direction:column;height:calc(100vh - 150px);min-height:320px}
.chathead{display:flex;justify-content:space-between;align-items:center;
padding:0 0 8px;border-bottom:1px solid #2a303a;gap:8px}
.logout{background:none;border:1px solid #2a303a;color:var(--dim);padding:3px 10px;
border-radius:6px;cursor:pointer;font-size:12px;white-space:nowrap}
.msglist{flex:1;overflow-y:auto;padding:10px 0;display:flex;flex-direction:column;gap:10px}
.msgrow{display:flex}.msgrow.me{justify-content:flex-end}
.bub{max-width:75%;padding:8px 12px;border-radius:12px;font-size:14px;
white-space:pre-wrap;word-break:break-word}
.msgrow.me .bub{background:var(--acc);color:#08131f;border-bottom-right-radius:2px}
.msgrow.bot .bub{background:var(--card);border:1px solid #2a303a;border-bottom-left-radius:2px}
.srcs{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}
.srcchip{font-size:11px;color:var(--dim);border:1px solid #2a303a;border-radius:8px;
padding:1px 6px}
.typing span{display:inline-block;width:6px;height:6px;margin:0 2px;
background:var(--dim);border-radius:50%;animation:blink 1.2s infinite ease-in-out}
.typing span:nth-child(2){animation-delay:.2s}.typing span:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
.chatbar{display:flex;gap:8px;padding:8px 0 2px;border-top:1px solid #2a303a}
.chatbar textarea{flex:1;resize:none;background:var(--card);border:1px solid #2a303a;
color:var(--fg);border-radius:8px;padding:8px 10px;font:14px/1.4 inherit;max-height:120px}
.chatbar button{background:var(--acc);color:#08131f;border:none;border-radius:8px;
padding:0 16px;cursor:pointer;font-size:14px}
@media(max-width:600px){.bub{max-width:85%}.chatwrap{height:calc(100vh - 130px)}
.chatbar{position:sticky;bottom:0;background:var(--bg);
padding-bottom:env(safe-area-inset-bottom,8px)}}
</style></head><body>
<header><h1>🎙️ 股癌 Gooaye 追蹤器</h1>
<nav><button data-v="eps" class="on">每集摘要</button>
<button data-v="tk">標的追蹤</button><button data-v="ind">產業追蹤</button>
<button data-v="chat">AI 分身</button></nav>
<span id="meta"></span></header>
<main><input id="q" placeholder="搜尋 代號 / 公司 / 關鍵字…"><div id="view"></div></main>
<div class="disc">純資訊彙整、AI 生成摘要可能有誤，非投資建議。</div>
<script>
const EPS=__EPS__,TK=__TK__,IND=__IND__;
const DEF_EP="https://35-254-238-132.sslip.io/gooaye";
let cur="eps",chatHist=[],chatBusy=false,lockErr="";
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const tag=s=>`<span class="tag ${esc(s)}">${esc(s)}</span>`;
const twinTok=()=>localStorage.getItem("twin_token")||"";
const twinEp=()=>localStorage.getItem("twin_endpoint")||DEF_EP;
const loadHist=()=>{try{return JSON.parse(sessionStorage.getItem("twin_hist")||"[]")}catch(e){return[]}};
const saveHist=h=>sessionStorage.setItem("twin_hist",JSON.stringify(h));
function render(){
 $("#q").style.display=cur==="chat"?"none":"";
 if(cur==="chat"){renderChat();return;}
 const q=$("#q").value.trim().toLowerCase(),v=$("#view");let h="";
 if(cur==="eps"){
  for(const a of EPS){
   const txt=JSON.stringify(a).toLowerCase();
   if(q&&!txt.includes(q))continue;
   h+=`<div class="card"><h3>${esc(a.ep_key)} ｜ ${esc(a.title)}</h3>
   <div class="dim">${esc(a.pubdate)} · ${Math.round(a.duration_s/60)} 分鐘${a.has_tr?` · <a href="transcripts/${esc(a.ep_key)}.md" style="color:var(--acc)">📄 逐字稿</a>`:""}</div>
   <p>${esc(a.summary)}</p>
   ${a.market_view?`<p>📊 <b>大盤觀點：</b>${esc(a.market_view)}</p>`:""}
   <div>${(a.tickers||[]).map(t=>tag(t.stance)+esc(t.symbol)).join(" ")}</div>
   <details><summary>主題與論點</summary>
   <ul class="plain">${(a.topics||[]).map(t=>`<li>${esc(t)}</li>`).join("")}</ul>
   <ul class="plain">${(a.quotes||[]).map(t=>`<li>💬 ${esc(t)}</li>`).join("")}</ul>
   <ul class="tl">${(a.tickers||[]).map(t=>`<li>${tag(t.stance)}<b>${esc(t.symbol)}</b> ${esc(t.name)} — ${esc(t.argument)}</li>`).join("")}</ul>
   </details></div>`;}
 }else{
  const src=cur==="tk"?TK:IND;
  const keys=Object.keys(src).sort((a,b)=>src[b].mentions-src[a].mentions);
  for(const k of keys){
   const r=src[k],txt=(k+JSON.stringify(r)).toLowerCase();
   if(q&&!txt.includes(q))continue;
   h+=`<div class="card"><h3>${esc(k)} ${r.name&&r.name!==k?esc(r.name):""}
   ${tag(r.latest_stance)}</h3>
   <div class="dim">提及 ${r.mentions} 次 · 最近 ${esc(r.latest_date)}</div>
   <details ${q?"open":""}><summary>立場時間軸</summary><ul class="tl">
   ${r.timeline.map(e=>`<li>${tag(e.stance)}<b>${esc(e.ep)}</b> <span class="dim">${esc(e.date)}</span> ${esc(e.argument||e.view)}</li>`).join("")}
   </ul></details></div>`;}
 }
 v.innerHTML=h||'<p class="dim">沒有符合的資料</p>';
}
function renderChat(){
 const v=$("#view");
 if(!twinTok()){
  v.innerHTML=`<div class="lock"><h2>🧑‍💻 股癌 AI 分身</h2>
  <p class="dim">輸入通行碼開始與股癌 AI 分身對談</p>
  ${lockErr?`<p style="color:var(--bull)">${esc(lockErr)}</p>`:""}
  <input id="tkIn" type="text" class="mask" autocomplete="off" autocapitalize="off" placeholder="通行碼（可輸入中文）">
  <details><summary>進階：自訂端點</summary>
  <input id="epIn" placeholder="端點網址" value="${esc(twinEp())}"></details>
  <button class="go" id="enterBtn">進入</button></div>`;
  lockErr="";
  $("#enterBtn").onclick=()=>{
   const tk=$("#tkIn").value.trim();
   if(!tk)return;
   const ep=($("#epIn").value||"").trim()||DEF_EP;
   localStorage.setItem("twin_token",tk);
   localStorage.setItem("twin_endpoint",ep);
   renderChat();
  };
  $("#tkIn").onkeydown=e=>{if(e.key==="Enter"){e.preventDefault();$("#enterBtn").click();}};
  return;
 }
 chatHist=loadHist();
 v.innerHTML=`<div class="chatwrap">
  <div class="chathead"><span class="dim" style="font-size:11px">AI 分身非本人・非投資建議</span>
  <button class="logout" id="logoutBtn">登出</button></div>
  <div class="msglist" id="msgList"></div>
  <div class="chatbar"><textarea id="chatIn" rows="1"
  placeholder="輸入訊息…（Enter 送出，Shift+Enter 換行）"></textarea>
  <button id="sendBtn">送出</button></div></div>`;
 drawMsgs(false);
 $("#logoutBtn").onclick=()=>{
  localStorage.removeItem("twin_token");localStorage.removeItem("twin_endpoint");renderChat();};
 $("#sendBtn").onclick=sendMsg;
 $("#chatIn").onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMsg();}};
}
function drawMsgs(busy){
 const list=$("#msgList");if(!list)return;
 let h=chatHist.map(m=>{
  const cls=m.role==="user"?"me":"bot";
  let srcs="";
  if(m.sources&&m.sources.length)srcs=`<div class="srcs">${m.sources.map(s=>
   `<span class="srcchip">${esc(s.ep||"")}${s.kind?"·"+esc(s.kind):""}${s.date?"·"+esc(s.date):""}</span>`
  ).join("")}</div>`;
  return `<div class="msgrow ${cls}"><div class="bub">${esc(m.content)}${srcs}</div></div>`;
 }).join("");
 if(busy)h+=`<div class="msgrow bot"><div class="bub typing"><span></span><span></span><span></span></div></div>`;
 list.innerHTML=h;
 list.scrollTop=list.scrollHeight;
}
function sendMsg(){
 if(chatBusy)return;
 const ta=$("#chatIn"),msg=ta.value.trim();
 if(!msg)return;
 chatHist.push({role:"user",content:msg});
 saveHist(chatHist);
 ta.value="";
 chatBusy=true;
 drawMsgs(true);
 const sb=$("#sendBtn");if(sb)sb.disabled=true;
 const hist=chatHist.slice(0,-1).slice(-10).map(m=>({role:m.role,content:m.content}));
 fetch(twinEp()+"/chat",{method:"POST",
  headers:{"Content-Type":"application/json","Authorization":"Bearer "+encodeURIComponent(twinTok())},
  body:JSON.stringify({message:msg,history:hist})
 }).then(res=>{
  if(res.status===401){const e=new Error("auth");e.kind="auth";throw e;}
  if(res.status===429){const e=new Error("rate");e.kind="rate";throw e;}
  if(!res.ok){const e=new Error("http");e.kind="http";throw e;}
  return res.json();
 }).then(data=>{
  chatHist.push({role:"assistant",content:data.reply||"",sources:data.sources||[]});
  saveHist(chatHist);
 }).catch(err=>{
  if(err&&err.kind==="auth"){
   localStorage.removeItem("twin_token");
   lockErr="通行碼錯誤，請重新輸入";
   chatBusy=false;renderChat();return;
  }
  if(err&&err.kind==="rate"){
   chatHist.push({role:"assistant",content:"⏳ 請求太頻繁，請稍等一下再試"});
  }else{
   chatHist.push({role:"assistant",content:"⚠️ 端點無法連線，服務可能尚未開通，請稍後再試"});
  }
  saveHist(chatHist);
 }).finally(()=>{
  chatBusy=false;
  const sb2=$("#sendBtn");if(sb2)sb2.disabled=false;
  drawMsgs(false);
 });
}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{
 cur=b.dataset.v;document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("on",x===b));render();});
$("#q").oninput=render;
$("#meta").textContent=`${EPS.length} 集 · ${Object.keys(TK).length} 檔標的 · ${Object.keys(IND).length} 個產業`;
render();
</script></body></html>"""


def main():
    eps = [json.loads(f.read_text(encoding="utf-8"))
           for f in ANALYSES.glob("*.json") if not f.name.startswith(".")]
    for a in eps:
        a["has_tr"] = (TRANSCRIPTS / f"{a['ep_key']}.md").exists()
    eps.sort(key=lambda a: a["pubdate"], reverse=True)
    tk = json.loads((DATA / "tickers.json").read_text(encoding="utf-8")) \
        if (DATA / "tickers.json").exists() else {}
    ind = json.loads((DATA / "industries.json").read_text(encoding="utf-8")) \
        if (DATA / "industries.json").exists() else {}
    html = (TEMPLATE
            .replace("__EPS__", json.dumps(eps, ensure_ascii=False))
            .replace("__TK__", json.dumps(tk, ensure_ascii=False))
            .replace("__IND__", json.dumps(ind, ensure_ascii=False)))
    out = DATA / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"dashboard: {out} ({out.stat().st_size >> 10}KB, {len(eps)} 集)")


if __name__ == "__main__":
    main()
