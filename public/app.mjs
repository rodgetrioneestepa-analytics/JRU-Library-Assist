const $=id=>document.getElementById(id);
const state={messages:[],busy:false,ready:false};
const storageKey='library-assist-conversation-v4';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let toastTimer;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3000);}
function closeMenu(){$('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');}
function save(){try{localStorage.setItem(storageKey,JSON.stringify(state.messages.slice(-50)));}catch{}}
function render(){
  $('welcome').hidden=state.messages.length>0;
  $('messages').innerHTML=state.messages.map((m,index)=>{
    const sources=m.role==='assistant'?(m.sources||[]):[];
    const body=escape(m.content).replace(/\[(\d+)\]/g,(match,n)=>sources.some(s=>s.n===Number(n))?`<button class="inline-citation" data-citation="${index}-${Number(n)}" aria-label="View source ${Number(n)}">${match}</button>`:match);
    const evidence=sources.length?`<details class="citation-details" id="citations-${index}"><summary>Sources (${sources.length})</summary>${sources.map(s=>`<div class="citation-source" id="citation-${index}-${Number(s.n)}"><strong>[${Number(s.n)}] ${escape(s.ref)}</strong><p>${escape(s.text)}</p></div>`).join('')}</details>`:'';
    return `<article class="message ${m.role}"><div class="message-header">${m.role==='user'?'<span class="avatar">YOU</span>':'<img class="avatar assistant-avatar" src="assets/library-assist-logo.png" alt="" width="27" height="35">'}${m.role==='user'?'You':'Library-Assist'}</div><div class="message-body">${body}</div>${evidence}</article>`;
  }).join('');
  if(state.busy)$('messages').insertAdjacentHTML('beforeend','<article class="message pending"><div class="message-header"><img class="avatar assistant-avatar" src="assets/library-assist-logo.png" alt="" width="27" height="35">Library-Assist</div><div class="message-body">Let me check that for you</div></article>');
  requestAnimationFrame(()=>$('chat-scroll').scrollTop=state.messages.length?$('chat-scroll').scrollHeight:0);
}
async function send(question){
  if(state.busy)return;
  if(!state.ready){toast('The assistant is connecting. Please try again shortly.');return;}
  const message=question.trim();if(!message)return;if(message.length>1000){toast('Please keep your message under 1,000 characters.');return;}
  const history=state.messages.slice(-6).map(m=>({role:m.role,content:m.content}));
  state.messages.push({role:'user',content:message});state.busy=true;closeMenu();$('question').value='';$('question').disabled=true;$('send').disabled=true;$('chat-notice').textContent='';render();
  try{
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,history}),signal:AbortSignal.timeout(240000)});
    const result=await response.json();if(!response.ok||typeof result.answer!=='string')throw new Error(result.error||"I couldn't complete that request. Please try again.");
    state.messages.push({role:'assistant',content:result.answer,sources:Array.isArray(result.sources)?result.sources:[]});save();
  }catch(error){$('chat-notice').textContent=error.name==='TimeoutError'?'That took longer than expected. Please try again.':error.message;}
  finally{state.busy=false;$('question').disabled=false;$('send').disabled=false;render();$('question').focus();}
}
$('chat-form').addEventListener('submit',event=>{event.preventDefault();send($('question').value);});
$('question').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();send(event.currentTarget.value);}});
document.addEventListener('click',event=>{const button=event.target.closest('[data-question]');if(button)send(button.dataset.question);});
$('messages').addEventListener('click',event=>{const button=event.target.closest('[data-citation]');if(!button)return;const [index,n]=button.dataset.citation.split('-');const details=$(`citations-${index}`);if(details){details.open=true;$(`citation-${index}-${n}`)?.scrollIntoView({block:'nearest',behavior:'smooth'});}});
$('new-chat').addEventListener('click',()=>{if(state.busy){toast('Please wait for the current reply.');return;}state.messages=[];save();closeMenu();$('question').value='';$('chat-notice').textContent='';render();$('question').focus();});
document.querySelectorAll('a[href="#chat"]').forEach(link=>link.addEventListener('click',closeMenu));
$('menu-toggle').addEventListener('click',()=>{const open=$('sidebar').classList.toggle('open');$('menu-toggle').setAttribute('aria-expanded',String(open));});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
$('export-chat').addEventListener('click',()=>{if(!state.messages.length){toast('Start a conversation before downloading it.');return;}const text=state.messages.map(m=>`${m.role==='user'?'You':'Library-Assist'}\n${m.content}\n${(m.sources||[]).map(s=>`[${s.n}] ${s.ref}`).join('\n')}\n`).join('\n');const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));link.download='library-assist-conversation.txt';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);});
async function init(){
  try{const saved=JSON.parse(localStorage.getItem(storageKey)||'[]');if(Array.isArray(saved))state.messages=saved.filter(m=>m&&['user','assistant'].includes(m.role)&&typeof m.content==='string').slice(-50);}catch{}
  render();
  try{const response=await fetch('/api/status',{signal:AbortSignal.timeout(90000)});const info=await response.json();state.ready=response.ok&&info.ready;}catch{state.ready=false;}
  $('connection-status').textContent=state.ready?'Ready to help':'Temporarily unavailable';$('question').disabled=!state.ready;$('send').disabled=!state.ready;
  if(!state.ready)$('chat-notice').textContent='The assistant is unavailable right now. Please reload the page to reconnect.';
}
init();
