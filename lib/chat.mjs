import {readFileSync} from 'node:fs';
import {createRetriever,retrieveAnswer} from './retrieval.mjs';
const source=JSON.parse(readFileSync(new URL('../server_data/faqs.json',import.meta.url),'utf8'));
const settings=JSON.parse(readFileSync(new URL('../rag_backend/notebook_spec.json',import.meta.url),'utf8'));
const search=createRetriever(source.records);
const normalize=s=>String(s).toLowerCase().replace(/\s+/g,' ').trim();
const safe=s=>String(s).replace(/(account\s*(?:number|no\.?)[^\n:]*[:\s]+)\d[\d -]{5,}/gi,'$1[REDACTED — CONFIRM WITH LIBRARY]');
export function cleanHistory(history){return Array.isArray(history)?history.filter(t=>t&&['user','assistant'].includes(t.role)&&typeof t.content==='string').slice(-6).map(t=>({role:t.role,content:safe(t.content.slice(0,1000))})):[];}
export function socialReply(message){const m=normalize(message).replace(/[!?. ]+$/,'');if(['hi','hello','hey','good morning','good afternoon','good evening'].includes(m))return 'Hi! I can help with library hours, borrowing, renewals, and more. What would you like to know?';if(['thanks','thank you','thank you so much','salamat','salamat po'].includes(m))return "You're welcome! Feel free to ask another library question.";if(['bye','goodbye','see you'].includes(m))return 'Take care! Come back anytime you need library help.';if(['help','what can you do','how can you help'].includes(m))return 'I can help with borrowing, renewals, fines, OPAC, electronic resources, and library facilities.';return null;}
function unsupported(q){return /(?:what is|tell me|give me).*?(?:wi.?fi password|network password)|right now|at this exact moment|currently available seats|on duty now/i.test(q);}
function backend(){if(!process.env.RAG_BACKEND_URL)return null;const url=new URL(process.env.RAG_BACKEND_URL);if(process.env.VERCEL&&url.protocol!=='https:')throw new Error('Hosted backend requires HTTPS');return url;}
function backendHeaders(){return {'Content-Type':'application/json',...(process.env.RAG_BACKEND_TOKEN?{Authorization:'Bearer '+process.env.RAG_BACKEND_TOKEN}:{})};}
export async function status(){const remote=backend();if(remote){try{const r=await fetch(new URL('/api/status',remote),{headers:backendHeaders(),signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error('Unavailable');const data=await r.json();return {ready:!!data.ready,service:'Library-Assist'};}catch{return {ready:false,service:'Library-Assist'};}}return {ready:true,service:'Library-Assist'};}
async function completion(messages,max_completion_tokens,timeout=45000){const r=await fetch('https://api.groq.com/openai/v1/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+process.env.GROQ_API_KEY,'Content-Type':'application/json'},signal:AbortSignal.timeout(timeout),body:JSON.stringify({model:process.env.GROQ_MODEL||settings.GROQ_MODEL,temperature:0,max_completion_tokens,messages})});if(!r.ok)throw new Error('Provider unavailable');return r.json();}
export async function standaloneQuestion(latest,history,requestCompletion=completion){if(!history.length)return latest;const compact=history.slice(-6).map(t=>`${t.role}: ${t.content.slice(0,350)}`).join('\n').slice(0,1600);try{const result=await requestCompletion([{role:'system',content:settings.REWRITE_PROMPT},{role:'user',content:`Recent chat:\n${compact}\n\nLatest message: ${latest}`}],450,20000);const text=result?.choices?.[0]?.message?.content||'';const lines=text.split('\n').map(s=>s.trim()).filter(Boolean);if(!lines.length)return latest;const rewritten=lines[0].replace(/^[ "'`•]+|[ "'`•]+$/g,'');return rewritten.length>=5&&rewritten.length<=350?rewritten:latest;}catch{return latest;}}
export async function chat(data){
  if(!data||typeof data.message!=='string'||!data.message.trim())return {status:400,body:{error:'Please type a message first.'}};
  const question=data.message.trim();if(question.length>1000)return {status:400,body:{error:'Keep your message under 1,000 characters.'}};
  const history=cleanHistory(data.history),remote=backend();
  if(remote){try{const r=await fetch(new URL('/api/chat',remote),{method:'POST',headers:backendHeaders(),body:JSON.stringify({message:question,history}),signal:AbortSignal.timeout(110000)});const result=await r.json();return {status:r.status,body:r.ok?{answer:result.answer,refused:!!result.refused}:{error:result.error||'Please try again shortly.'}};}catch{return {status:502,body:{error:"I couldn't complete that request. Please try again shortly."}};}}
  const social=socialReply(question);if(social)return {status:200,body:{answer:social,refused:false}};
  if(unsupported(question))return {status:200,body:{answer:settings.REFUSAL,refused:true}};
  const query=process.env.GROQ_API_KEY?await standaloneQuestion(question,history):question;
  if(unsupported(query))return {status:200,body:{answer:settings.REFUSAL,refused:true}};
  const result=retrieveAnswer(query,search,process.env.GROQ_API_KEY?[]:history);
  if(result.refused||!result.sources.length)return {status:200,body:{answer:settings.REFUSAL,refused:true}};
  if(!process.env.GROQ_API_KEY)return {status:200,body:{answer:safe(result.answer),refused:false}};
  try{
    const evidence=result.sources.map((s,i)=>`[${i+1}] (${s.ref}) Topic: ${s.category}\nQuestion: ${s.question}\nAnswer: ${safe(s.text)}`).join('\n\n').slice(0,7000);
    const recent=history.map(t=>`${t.role}: ${t.content.slice(0,450)}`).join('\n').slice(0,1800);
    const response=await completion([{role:'system',content:settings.ANSWER_PROMPT},{role:'user',content:`RECENT CHAT (reference resolution only; not a source of facts):\n${recent||'(none)'}\n\nCURRENT VERIFIED FAQ PASSAGES:\n${evidence}\n\nStudent's latest message: ${question}\nRetrieval interpretation: ${query}`}],700);
    const answer=safe(response?.choices?.[0]?.message?.content?.trim()||settings.REFUSAL);
    if([...answer.matchAll(/\[(\d+)\]/g)].some(m=>Number(m[1])<1||Number(m[1])>result.sources.length))throw new Error('Invalid citation');
    return {status:200,body:{answer,refused:/couldn't confirm|could not confirm|cannot confirm|cannot verify/i.test(answer)}};
  }catch(error){console.error('Chat generation failed:',error.name);return {status:502,body:{error:"I couldn't complete that request. Please try again shortly."}};}
}
