import { createRetriever, retrieveAnswer } from './retrieval.mjs';
const $=id=>document.getElementById(id);
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const MODE={faq:'FAQ retrieval',groq:'Groq · grounded answers',original:'Original semantic RAG',browser:'Browser · FAQ retrieval'};
const state={records:[],experiment:null,search:null,messages:[],busy:false,mode:'faq',api:false,faqLimit:25,session:crypto.randomUUID()};
let toastTimer;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function save(){try{localStorage.setItem('library-assist-chat-v1',JSON.stringify({session:state.session,messages:state.messages.slice(-50)}));}catch{}}
function restore(){try{const stored=JSON.parse(localStorage.getItem('library-assist-chat-v1')||'null');if(stored&&Array.isArray(stored.messages)){state.session=typeof stored.session==='string'?stored.session:state.session;state.messages=stored.messages.filter(t=>['user','assistant'].includes(t.role)&&typeof t.content==='string').slice(-50);}}catch{}}
function setMode(mode){state.mode=mode;$('mode-badge').textContent=MODE[mode]||MODE.faq;$('composer-mode').textContent=mode==='groq'?'Groq generation · FAQ evidence':mode==='original'?'MiniLM + ChromaDB · Groq':'Source-backed FAQ excerpts';}
function setPage(){const name=location.hash.slice(1)||'chat';const page=['chat','knowledge','experiments','about'].includes(name)?name:'chat';for(const el of document.querySelectorAll('.page'))el.hidden=el.id!=='page-'+page;for(const el of document.querySelectorAll('[data-page]')){const active=el.dataset.page===page;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');}$('page-name').textContent={chat:'Ask the library',knowledge:'Knowledge base',experiments:'Experiment results',about:'About the project'}[page];$('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');if(page==='knowledge')renderFaqs();}
function renderMessages(){
  $('welcome').hidden=state.messages.length>0;
  $('messages').innerHTML=state.messages.map((m,index)=>`<article class="message ${m.role}"><div class="message-header"><span class="avatar">${m.role==='user'?'YOU':'LA'}</span>${m.role==='user'?'You':'Library-Assist'}</div><div class="message-body">${escape(m.content)}</div>${m.role==='assistant'?`<div class="message-meta">${(m.sources||[]).map(s=>`<button class="source-chip" data-message="${index}" data-source="${Number(s.n)||1}">[${Number(s.n)||1}] ${escape(s.ref)}</button>`).join('')}</div><div class="message-note">${escape(MODE[m.mode]||MODE.faq)}${m.elapsedMs!==undefined?' · '+(m.elapsedMs/1000).toFixed(2)+'s':''}${m.notice?' · '+escape(m.notice):''}${(m.sources||[]).some(s=>/pandemic|until further notice|2020|2021/i.test(s.text))?' · Includes older policy wording. Confirm current details with library staff.':''}</div>`:''}</article>`).join('');
  if(state.busy)$('messages').insertAdjacentHTML('beforeend','<article class="message pending"><div class="message-header"><span class="avatar">LA</span>Library-Assist</div><div class="message-body">Finding the relevant FAQs</div></article>');
  const latest=[...state.messages].reverse().find(m=>m.role==='assistant');renderSources(latest?.sources||[]);
  requestAnimationFrame(()=>$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight);
}
function renderSources(sources,openNumber){
  $('source-count').textContent=sources.length;
  $('source-list').innerHTML=sources.length?sources.map(s=>`<details class="source-card" ${openNumber===Number(s.n)?'open':''}><summary><span>[${Number(s.n)||1}]</span> ${escape(s.question||s.ref)}</summary><small>${escape(s.ref)}${s.category?' · '+escape(s.category):''}</small><p>${escape(s.text)}</p>${s.refs?.length>1?`<small>Also appears in: ${escape(s.refs.slice(1).join(', '))}</small>`:''}</details>`).join(''):'<div class="empty-sources"><span aria-hidden="true">⌕</span><p>Your sources will appear here.</p><small>Ask a question to see the FAQ passages behind your answer.</small></div>';
}
async function sendQuestion(question){
  if(state.busy||!state.search)return;
  const message=question.trim();if(!message)return;if(message.length>1000){toast('Please keep your question under 1,000 characters.');return;}
  if(location.hash!=='#chat')location.hash='chat';
  const history=state.messages.map(m=>({role:m.role,content:m.content})).slice(-6);
  state.messages.push({role:'user',content:message});state.busy=true;$('question').value='';$('send').disabled=true;$('question').disabled=true;$('chat-notice').textContent='';renderMessages();
  try{
    let result;
    if(state.api){
      const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,history,session_id:state.session}),signal:AbortSignal.timeout(60000)});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'Unable to retrieve an answer. Please try again.');result=data;
    }else{
      const start=performance.now();result={...retrieveAnswer(message,state.search,history),mode:'browser',elapsedMs:Math.round(performance.now()-start)};
    }
    state.messages.push({role:'assistant',content:result.answer,sources:result.sources||[],mode:result.mode,elapsedMs:result.elapsedMs,notice:result.notice});save();
  }catch(error){$('chat-notice').textContent=error.name==='TimeoutError'?'The request timed out. Please try again.':error.message;}
  finally{state.busy=false;$('send').disabled=false;$('question').disabled=false;renderMessages();$('question').focus();}
}
function renderFaqs(){
  if(!state.records.length)return;
  const q=$('faq-search').value.trim().toLowerCase();const sheet=$('sheet-filter').value;
  const hits=state.records.filter(r=>(!sheet||r.source_refs.some(ref=>ref.startsWith(sheet+'!')))&&(!q||[r.question,r.option,r.answer,r.category].some(s=>s.toLowerCase().includes(q))));
  $('faq-count').textContent=`${hits.length} ${hits.length===1?'FAQ':'FAQs'}${q?' matching “'+q+'”':''} · '+state.records.length+' unique records in total';
  $('faq-list').innerHTML=hits.length?hits.slice(0,state.faqLimit).map(r=>`<details class="faq-card"><summary>${escape(r.question)}${r.option?' · '+escape(r.option):''}</summary><span class="faq-ref">${escape(r.category||'Library FAQ')} · ${escape(r.source_refs.join(' · '))}</span><p>${escape(r.answer)}</p><button class="text-button" data-ask="${escape(r.id)}">Ask about this FAQ</button></details>`).join(''):'<div class="experiment-card"><h2>No matching FAQs</h2><p>Try a broader keyword or choose another worksheet.</p></div>';
  $('load-more').hidden=hits.length<=state.faqLimit;
}
function renderExperiments(){
  const {manifest,chunking_comparison:configs}=state.experiment;
  const best=configs.reduce((a,b)=>Number(a['Recall@3'])>Number(b['Recall@3'])?a:b);
  $('metric-grid').innerHTML=`<div class="metric-tile"><span class="eyebrow">SOURCE COLLECTION</span><strong>${manifest.unique_records}</strong><p>Unique FAQs from ${manifest.raw_records} source records</p></div><div class="metric-tile"><span class="eyebrow">HIGHEST RECORDED RECALL@3</span><strong>${(Number(best['Recall@3'])*100).toFixed(1)}%</strong><p>Configuration ${escape(best.config)} · original experiment</p></div><div class="metric-tile"><span class="eyebrow">ORIGINAL DEFAULT</span><strong>${escape(manifest.active_config)}</strong><p>800-character chunks · 100 overlap · top 3</p></div>`;
  $('config-table').innerHTML=configs.map(c=>`<tr><td>${escape(c.config)}${c.config===manifest.active_config?'<span class="default-tag">DEFAULT</span>':''}</td><td>${escape(c.chunk_size)}</td><td>${escape(c.overlap)}</td><td>${escape(c.top_k)}</td><td>${(Number(c['Precision@3'])*100).toFixed(1)}%</td><td>${(Number(c['Recall@3'])*100).toFixed(1)}%</td><td>${Number(c['MRR@3']).toFixed(3)}</td><td>${Number(c.indexing_s).toFixed(2)}s</td></tr>`).join('');renderChart();
}
function renderChart(){const metric=$('metric-select').value;const configs=state.experiment.chunking_comparison;const max=Math.max(...configs.map(c=>Number(c[metric])));$('metric-chart').setAttribute('aria-label',metric+' by configuration: '+configs.map(c=>c.config+' '+(Number(c[metric])*100).toFixed(1)+'%').join(', '));$('metric-chart').innerHTML=configs.map(c=>`<div class="bar-row ${Number(c[metric])===max?'best':''}"><span>Config ${escape(c.config)}</span><div class="bar-track"><div class="bar-fill" style="width:${Number(c[metric])*100}%"></div></div><span class="bar-value">${(Number(c[metric])*100).toFixed(1)}%</span></div>`).join('');}
$('chat-form').addEventListener('submit',event=>{event.preventDefault();sendQuestion($('question').value);});
$('question').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();sendQuestion(event.currentTarget.value);}});
$('suggestions').addEventListener('click',event=>{const button=event.target.closest('[data-question]');if(button)sendQuestion(button.dataset.question);});
$('messages').addEventListener('click',event=>{const chip=event.target.closest('[data-message]');if(!chip)return;const sources=state.messages[Number(chip.dataset.message)]?.sources||[];renderSources(sources,Number(chip.dataset.source));if(matchMedia('(max-width:980px)').matches){const source=sources.find(s=>Number(s.n)===Number(chip.dataset.source));if(source){const detail=document.createElement('details');detail.className='source-card';detail.open=true;const summary=document.createElement('summary');summary.textContent='['+source.n+'] '+source.ref;const p=document.createElement('p');p.textContent=source.text;detail.append(summary,p);chip.closest('.message').append(detail);}}});
$('new-chat').addEventListener('click',()=>{if(state.busy){toast('Please wait for the current answer.');return;}state.messages=[];state.session=crypto.randomUUID();save();renderMessages();$('chat-notice').textContent='';location.hash='chat';$('question').focus();});
$('faq-search').addEventListener('input',()=>{state.faqLimit=25;renderFaqs();});$('sheet-filter').addEventListener('change',()=>{state.faqLimit=25;renderFaqs();});$('load-more').addEventListener('click',()=>{state.faqLimit+=25;renderFaqs();});
$('faq-list').addEventListener('click',event=>{const button=event.target.closest('[data-ask]');if(button){const record=state.records.find(r=>r.id===button.dataset.ask);if(record)sendQuestion(record.question+' '+record.option);}});
$('metric-select').addEventListener('change',renderChart);
$('menu-toggle').addEventListener('click',()=>{const open=$('sidebar').classList.toggle('open');$('menu-toggle').setAttribute('aria-expanded',String(open));});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){$('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');}});
$('export-chat').addEventListener('click',()=>{if(!state.messages.length){toast('Start a conversation before downloading it.');return;}const text=['Library-Assist conversation','Academic prototype — verify current policies with library staff.','',...state.messages.map(m=>`${m.role==='user'?'You':'Library-Assist'}\n${m.content}\n${(m.sources||[]).map(s=>'['+s.n+'] '+s.ref+' — '+s.text).join('\n')}\n`)].join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));a.download='library-assist-conversation.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('Conversation downloaded.');});
window.addEventListener('hashchange',setPage);
async function init(){
  setPage();
  try{
    const [faqs,experiments]=await Promise.all(['data/faqs.json','data/experiments.json'].map(async url=>{const r=await fetch(url);if(!r.ok)throw new Error('Unable to load the FAQ collection.');return r.json();}));
    state.records=faqs;state.experiment=experiments;state.search=createRetriever(faqs);$('faq-total').textContent=faqs.length;
    $('sheet-filter').innerHTML='<option value="">All worksheets</option>'+experiments.manifest.worksheets.map(sheet=>`<option value="${escape(sheet)}">${escape(sheet)}</option>`).join('');
    restore();renderMessages();renderFaqs();renderExperiments();
    try{const r=await fetch('/api/status',{signal:AbortSignal.timeout(4000)});if(r.ok){const s=await r.json();state.api=s.ready;setMode(s.mode);}else setMode('browser');}catch{setMode('browser');}
    $('question').disabled=false;$('send').disabled=false;
  }catch(error){$('mode-badge').textContent='Unable to load FAQs';$('chat-notice').textContent=error.message+' Reload the page to try again.';}
}
init();
