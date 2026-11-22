import { readFileSync } from 'node:fs';
import { createRetriever, retrieveAnswer } from '../public/retrieval.mjs';
import { notebookRecords } from '../public/notebook-data.mjs';
import { validateEvidence } from './evidence.mjs';
const source=JSON.parse(readFileSync(new URL('../public/data/notebook-source.json',import.meta.url),'utf8'));
const spec=JSON.parse(readFileSync(new URL('../rag_backend/notebook_spec.json',import.meta.url),'utf8'));
const records=notebookRecords(source),search=createRetriever(records);
function backend(){const address=process.env.RAG_BACKEND_URL||(!process.env.VERCEL?process.env.ORIGINAL_RAG_URL:'');if(!address)return null;const url=new URL(address);if(process.env.VERCEL&&url.protocol!=='https:')throw new Error('Hosted RAG backend requires HTTPS');return url;}
function headers(){return {'Content-Type':'application/json',...(process.env.RAG_BACKEND_TOKEN?{Authorization:'Bearer '+process.env.RAG_BACKEND_TOKEN}:{})};}
export async function status(){
  const remote=backend();
  if(remote){try{const response=await fetch(new URL('/api/status',remote),{headers:headers(),signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error('Backend unavailable');return await response.json();}catch{return {ready:false,mode:'backend-unavailable',notebook:true,error:'The configured Python RAG backend is unavailable.'};}}
  return {ready:true,mode:process.env.GROQ_API_KEY?'notebook-groq':'notebook-faq',records:records.length,chunks:records.length,pages:source.pages.length,notebook:true,source:source.source_document,sourceSha256:source.dataset_sha256,chunkSize:1000,overlap:200,topK:3,vectorStore:'BM25 fallback'};
}
export async function chat(data){
  if(!data||typeof data.message!=='string'||!data.message.trim())return {status:400,body:{error:'Please enter a library question.'}};
  if(data.message.length>1000)return {status:400,body:{error:'Keep your question under 1,000 characters.'}};
  const started=performance.now(),remote=backend();
  if(remote){try{const response=await fetch(new URL('/api/chat',remote),{method:'POST',headers:headers(),body:JSON.stringify({message:data.message}),signal:AbortSignal.timeout(55000)});return {status:response.status,body:await response.json()};}catch{return {status:502,body:{error:'The Python RAG backend is unavailable. Start it locally or check RAG_BACKEND_URL.'}};}}
  // Same PDF/chunks, explicitly labelled lexical fallback. Each query is independent.
  const result=retrieveAnswer(data.message,search);result.mode='notebook-faq';
  if(result.sources.length&&!result.refused){
    result.answer='Retrieved PDF passage (not a generated answer):\n\n'+result.answer;
    if(process.env.GROQ_API_KEY){
      const evidence=result.sources.map(s=>({source_id:s.id,text:s.text,page:s.page,chunk_id:s.chunk_id,source_document:source.source_document}));
      try{
        const response=await fetch('https://api.groq.com/openai/v1/chat/completions',{
          method:'POST',headers:{Authorization:'Bearer '+process.env.GROQ_API_KEY,'Content-Type':'application/json'},signal:AbortSignal.timeout(45000),
          body:JSON.stringify({model:process.env.GROQ_MODEL||'openai/gpt-oss-20b',temperature:0,max_completion_tokens:2048,reasoning_effort:'low',include_reasoning:false,
            messages:[{role:'system',content:spec.FAQ_SYSTEM_PROMPT},{role:'user',content:JSON.stringify({question:data.message,sources:evidence})}],response_format:{type:'json_schema',json_schema:{name:'jru_faq_answer',strict:true,schema:spec.FAQ_RESPONSE_SCHEMA}}})
        });
        if(!response.ok)throw new Error('Provider unavailable');
        const payload=await response.json(),choice=payload.choices?.[0];if(choice?.finish_reason!=='stop')throw new Error('Incomplete generation');
        const verified=validateEvidence(JSON.parse(choice.message.content||''),evidence),numbers=new Map(result.sources.map(s=>[s.id,s.n]));
        result.answer=verified.answer.replace(/\[(S\d+)\]/g,(match,id)=>numbers.has(id)?`[${numbers.get(id)}]`:match);
        if(verified.citations.length)result.answer+='\n\n'+[...new Set(verified.citations.map(c=>`[${numbers.get(c.source_id)}]`))].join(' ');
        result.mode='notebook-groq';result.status=verified.status;result.citations=verified.citations;
        if(verified.status==='insufficient'){result.sources=[];result.refused=true;}
      }catch(error){console.error('Generation/evidence validation failed:',error.name);return {status:502,body:{error:'The generated answer failed the provider or evidence checks. No generated answer was displayed. Please retry.'}};}
    }
  }
  return {status:200,body:{...result,elapsedMs:Math.round(performance.now()-started)}};
}
