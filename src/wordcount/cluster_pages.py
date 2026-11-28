"""HTML for the classroom cluster: the page phones open, and the projector dashboard."""

WORKER_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Join the word-count cluster</title>
<style>
 :root{--navy:#1f3864;--blue:#4472c4;--green:#2e7d32;--amber:#bf9000;--bg:#f5f7fb}
 *{box-sizing:border-box} body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;background:var(--bg);color:#1b1b1b}
 main{max-width:460px;margin:0 auto;padding:24px 16px}
 h1{font-size:1.5rem;color:var(--navy);margin:0 0 4px} p.sub{margin:0 0 20px;color:#555}
 .card{background:#fff;border-radius:14px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:14px}
 input{width:100%;font-size:1.1rem;padding:12px;border:1px solid #c8cfdb;border-radius:10px}
 button{width:100%;font-size:1.1rem;padding:14px;border:0;border-radius:10px;margin-top:12px;color:#fff;background:var(--blue);font-weight:600}
 button.leave{background:#b3261e}
 .big{font-size:2.4rem;font-weight:700;color:var(--navy)} .state{font-size:1.15rem;font-weight:600}
 .muted{color:#666;font-size:.92rem} .hidden{display:none}
 .working{color:var(--amber)} .ok{color:var(--green)}
 pre{white-space:pre-wrap;background:#f0f3f8;border-radius:8px;padding:10px;font-size:.8rem;max-height:120px;overflow:auto}
</style></head><body><main>
<h1>Word-count cluster</h1><p class="sub">Your device becomes one worker of a distributed program.</p>
<section id="joinBox" class="card">
 <label for="name" class="muted">Your name (shown on the projector)</label>
 <input id="name" maxlength="24" placeholder="e.g. Phone 1">
 <button id="join">Join as a worker</button>
</section>
<section id="workBox" class="card hidden">
 <div class="muted">You are</div><div id="me" class="state"></div>
 <p id="status" class="state">Connecting…</p>
 <div class="muted">Tasks you completed</div><div id="done" class="big">0</div>
 <pre id="lines" class="hidden"></pre>
 <button id="leave" class="leave">Leave (simulate a crash)</button>
 <p class="muted">Leaving while you hold a task is like a computer crashing: after a few seconds the coordinator gives your task to someone else.</p>
</section>
</main>
<script>
const $=id=>document.getElementById(id);
let me=null, running=false, done=0;
$('name').value=localStorage.getItem('wc-name')||'';
const isWordChar=c=>/[\p{L}\p{N}_]/u.test(c);
function countWord(lines, word, ci){            // same rule as core.count_lines
  const target=ci?word.toLowerCase():word; let n=0;
  for(const line of lines){ let tok='';
    for(const c of line+' '){ if(isWordChar(c)) tok+=c;
      else if(tok){ if((ci?tok.toLowerCase():tok)===target) n++; tok=''; } } }
  return n; }
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path, body){
  const r=await fetch(path, body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  return r.json(); }
async function loop(){
  while(running){
    let reply; try{ reply=await api('/api/task?worker='+encodeURIComponent(me)); }
    catch(e){ $('status').textContent='Cannot reach the coordinator, retrying…'; await sleep(1500); continue; }
    const t=reply.task;
    if(!t){
      if(reply.phase==='finished'){ $('status').innerHTML='<span class="ok">✓ The whole job is finished. Stay here for the next one!</span>'; $('lines').classList.add('hidden'); await sleep(1500); continue; }
      $('status').textContent= reply.phase==='waiting' ? 'Waiting for the coordinator to press Start…' : 'No free task right now…';
      $('lines').classList.add('hidden'); await sleep(800); continue; }
    $('status').innerHTML=`<span class="working">Counting "${t.word.replace(/[<>&]/g,'')}" in task ${t.id} (lines ${t.start+1}–${t.stop})…</span>`;
    $('lines').textContent=t.lines.slice(0,4).join('')+(t.lines.length>4?'…':''); $('lines').classList.remove('hidden');
    const partial=countWord(t.lines, t.word, t.case_insensitive);
    await sleep(t.pace*1000);
    if(!running) break;                         // left while holding the task
    const res=await api('/api/result',{worker:me, task_id:t.id, partial, job:t.job});
    if(res.status==='accepted'){ done++; $('done').textContent=done; }
    $('status').innerHTML=`<span class="ok">Task ${t.id}: found ${partial} → ${res.status}</span>`;
    await sleep(200);
  } }
$('join').onclick=async()=>{
  const name=$('name').value.trim()||('phone-'+Math.floor(Math.random()*900+100));
  try{ localStorage.setItem('wc-name',name);}catch(e){}
  me=(await api('/api/join',{name})).name; $('me').textContent=me;
  $('joinBox').classList.add('hidden'); $('workBox').classList.remove('hidden');
  running=true; loop(); };
$('leave').onclick=()=>{ running=false; $('status').textContent='You left. Reload the page to join again.'; $('leave').disabled=true; };
</script></body></html>
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Classroom cluster dashboard</title>
<style>
 :root{--navy:#1f3864;--blue:#4472c4;--green:#70ad47;--dgreen:#2e7d32;--amber:#ffc000;--red:#c00000;--grey:#d9d9d9;--bg:#f5f7fb}
 *{box-sizing:border-box} body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;background:var(--bg);color:#1b1b1b}
 header{background:var(--navy);color:#fff;padding:14px 24px;display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between}
 header h1{margin:0;font-size:1.4rem} .join{font-size:1.25rem} .join b{font-size:1.6rem;color:#ffe699}
 main{padding:18px 24px;display:grid;grid-template-columns:2fr 1fr;gap:18px}
 @media(max-width:900px){main{grid-template-columns:1fr}}
 .card{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
 h2{margin:0 0 10px;font-size:1.05rem;color:var(--navy)}
 .stats{display:flex;flex-wrap:wrap;gap:22px;align-items:flex-end}
 .stat .v{font-size:2rem;font-weight:700;color:var(--navy)} .stat .k{color:#666;font-size:.85rem}
 .bar{height:14px;background:#e6e9ef;border-radius:7px;overflow:hidden;margin:12px 0 4px} .bar>div{height:100%;background:var(--green);transition:width .3s}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:8px}
 .task{border-radius:8px;padding:8px;min-height:72px;font-size:.82rem;border:2px solid transparent;transition:background .3s}
 .task .id{font-weight:700;font-size:1rem}
 .pending{background:var(--grey)} .running{background:#fff2cc;border-color:var(--amber)} .done{background:#e2f0d9;border-color:var(--green)}
 .again{box-shadow:0 0 0 3px var(--red) inset}
 .legend span{display:inline-block;margin-right:14px;font-size:.85rem} .sw{width:12px;height:12px;border-radius:3px;display:inline-block;vertical-align:-1px;margin-right:4px}
 table{width:100%;border-collapse:collapse;font-size:.9rem} td,th{padding:5px 4px;text-align:left;border-bottom:1px solid #eee}
 .gone{color:#999;text-decoration:line-through}
 ol{list-style:none;margin:0;padding:0;font-family:Consolas,monospace;font-size:.8rem;max-height:340px;overflow:auto}
 ol li{padding:3px 0;border-bottom:1px dashed #eee} .ev-LEASE{color:var(--red);font-weight:700} .ev-DUPLICATE{color:#7030a0;font-weight:700} .ev-FINISHED{color:var(--dgreen);font-weight:700}
 button{font-size:1rem;padding:9px 18px;border:0;border-radius:8px;background:var(--amber);font-weight:700;cursor:pointer;margin-left:8px}
 button.sec{background:#fff;color:var(--navy)}
 .result{font-size:1.25rem;font-weight:700;margin-top:8px}
 .current{font-size:1.05rem;color:#444;margin-bottom:10px} .current b{color:var(--navy)}
 #jobCard label{display:block;font-size:.85rem;color:#555;margin-top:8px}
 #jobCard input[type=text],#jobCard input[type=number],#jobCard input[type=file]{width:100%;font-size:.95rem;padding:7px;border:1px solid #c8cfdb;border-radius:7px;margin-top:3px;background:#fff}
 #jobCard .row{display:grid;grid-template-columns:2fr 1fr;gap:10px}
 #jobCard .chk{display:flex;gap:6px;align-items:center} #jobCard button{margin:12px 0 0;width:100%}
 #msg{display:block;margin-top:8px;font-size:.88rem}
</style></head><body>
<header><h1>Classroom cluster: distributed word count</h1>
 <div class="join">Join from your phone (same Wi-Fi): <b id="url">{{PHONE_URL}}</b></div>
 <div id="controls"><button id="start">Start</button><button id="reset" class="sec">Restart</button></div></header>
<main>
 <section class="card">
  <div class="current" id="current"></div>
  <div class="stats">
   <div class="stat"><div class="v" id="phase">…</div><div class="k">status</div></div>
   <div class="stat"><div class="v" id="prog">0/0</div><div class="k">tasks done</div></div>
   <div class="stat"><div class="v" id="sofar">0</div><div class="k">total so far</div></div>
   <div class="stat"><div class="v" id="exp">0</div><div class="k">expected total</div></div>
   <div class="stat"><div class="v" id="time">0</div><div class="k">seconds</div></div>
   <div class="stat"><div class="v" id="dups">0</div><div class="k">duplicates ignored</div></div>
  </div>
  <div class="bar"><div id="fill" style="width:0"></div></div>
  <div id="result" class="result"></div>
  <h2 style="margin-top:14px">Task queue</h2>
  <div class="legend"><span><i class="sw" style="background:var(--grey)"></i>waiting in queue</span><span><i class="sw" style="background:#fff2cc;border:1px solid var(--amber)"></i>running (leased)</span><span><i class="sw" style="background:#e2f0d9;border:1px solid var(--green)"></i>done</span><span><i class="sw" style="box-shadow:0 0 0 2px var(--red) inset"></i>was re-assigned</span></div>
  <div class="grid" id="tasks" style="margin-top:10px"></div>
 </section>
 <section style="display:grid;gap:18px;align-content:start">
  <div class="card" id="jobCard"><h2>Job: choose what to count</h2>
   <label>File (.txt or Word .docx), leave empty to keep the current one<input type="file" id="file" accept=".txt,.docx,text/plain"></label>
   <div class="row"><label>Word<input type="text" id="word" maxlength="40"></label><label>Tasks<input type="number" id="ntasks" min="1" max="200"></label></div>
   <label class="chk"><input type="checkbox" id="ci"> ignore upper/lower case</label>
   <button id="load">Load (resets the queue)</button><span id="msg"></span>
  </div>
  <div class="card"><h2>Workers</h2><table><thead><tr><th>Name</th><th>Doing</th><th>Done</th></tr></thead><tbody id="workers"></tbody></table></div>
  <div class="card"><h2>Messages</h2><ol id="events"></ol></div>
 </section>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function post(p){ const r=await fetch(p,{method:'POST',body:'{}'}); if(!r.ok) alert('Only the coordinator laptop can do this'); }
$('start').onclick=()=>post('/api/start'); $('reset').onclick=()=>post('/api/reset');
let shownJob=null;
$('load').onclick=async()=>{
  const f=$('file').files[0], q=new URLSearchParams({word:$('word').value.trim(), tasks:$('ntasks').value, ci:$('ci').checked?'1':'0'});
  if(f) q.set('name', f.name);
  $('msg').textContent='Loading…'; $('msg').style.color='#555';
  try{ const r=await fetch('/api/load?'+q, {method:'POST', body: f||''}); const d=await r.json();
    if(!r.ok) throw new Error(d.error||'failed');
    $('msg').textContent=`Loaded ${d.lines} lines. Expected total: ${d.expected}. Press Start.`; $('msg').style.color='var(--dgreen)'; $('file').value='';
  }catch(e){ $('msg').textContent='✗ '+e.message; $('msg').style.color='var(--red)'; } };
async function tick(){
  let s; try{ s=await (await fetch('/api/state')).json(); }catch(e){ $('phase').textContent='offline'; return; }
  $('controls').style.display=s.can_control?'':'none'; $('jobCard').style.display=s.can_control?'':'none';
  $('current').innerHTML=`Counting <b>"${esc(s.word)}"</b>${s.case_insensitive?' (any case)':''} in <b>${esc(s.source)}</b> · ${s.lines} lines · ${s.tasks_total} tasks`;
  if(shownJob!==s.job){ shownJob=s.job; $('word').value=s.word; $('ntasks').value=s.tasks_total; $('ci').checked=s.case_insensitive; }
  $('phase').textContent=s.phase; $('prog').textContent=`${s.done}/${s.tasks_total}`;
  $('sofar').textContent=s.total_so_far; $('exp').textContent=s.expected; $('time').textContent=s.elapsed; $('dups').textContent=s.duplicates;
  $('fill').style.width=(100*s.done/s.tasks_total)+'%';
  $('result').innerHTML = s.phase==='finished'
    ? (s.total_so_far===s.expected ? `<span style="color:var(--dgreen)">✓ Total ${s.total_so_far} = expected ${s.expected}: no task lost, none counted twice</span>`
                                    : `<span style="color:var(--red)">✗ Total ${s.total_so_far} ≠ expected ${s.expected}</span>`) : '';
  $('tasks').innerHTML=s.tasks.map(t=>`<div class="task ${t.state} ${t.expired?'again':''}">
    <div class="id">Task ${t.id}</div><div>lines ${t.start+1}–${t.stop}</div>
    <div>${t.state==='running'?`→ ${esc(t.worker)}<br>lease ${t.lease_left}s`:t.state==='done'?`partial ${t.partial}<br>by ${esc(t.done_by)}`:t.expired?'back in queue':''}</div></div>`).join('');
  $('workers').innerHTML=s.workers.map(w=>`<tr class="${w.active?'':'gone'}"><td>${esc(w.name)}</td><td>${w.current?'task '+w.current:(w.active?'idle':'gone')}</td><td>${w.done}</td></tr>`).join('')
    || '<tr><td colspan="3" style="color:#888">Nobody yet: open the address above on a phone</td></tr>';
  $('events').innerHTML=s.events.map(e=>`<li class="ev-${e.text.split(/[ :]/)[0]}">${e.t.toFixed(1)}s  ${esc(e.text)}</li>`).join('');
}
tick(); setInterval(tick,400);
</script></body></html>
"""
