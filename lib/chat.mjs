// Compatibility proxy for local Node development. Production runs the Python container.
// Missing configuration is an error, never permission to substitute another retrieval pipeline.
function backend(){
  if(!process.env.RAG_BACKEND_URL)return null;
  const url=new URL(process.env.RAG_BACKEND_URL);
  if(process.env.VERCEL&&url.protocol!=='https:')throw new Error('Hosted backend requires HTTPS');
  return url;
}
function headers(){return {'Content-Type':'application/json',...(process.env.RAG_BACKEND_TOKEN?{Authorization:'Bearer '+process.env.RAG_BACKEND_TOKEN}:{})};}
export function cleanHistory(history){return Array.isArray(history)?history.filter(t=>t&&['user','assistant'].includes(t.role)&&typeof t.content==='string').slice(-6).map(t=>({role:t.role,content:t.content.slice(0,1000)})):[];}
export async function status(){
  const remote=backend();if(!remote)return {ready:false,service:'Library-Assist'};
  try{const response=await fetch(new URL('/api/status',remote),{headers:headers(),signal:AbortSignal.timeout(90000)});const result=await response.json();return {...result,ready:response.ok&&!!result.ready};}
  catch{return {ready:false,service:'Library-Assist'};}
}
export async function chat(data){
  if(!data||typeof data.message!=='string'||!data.message.trim())return {status:400,body:{error:'Please type a message first.'}};
  if(data.message.trim().length>1000)return {status:400,body:{error:'Keep your message under 1,000 characters.'}};
  const remote=backend();if(!remote)return {status:503,body:{error:'The library assistant is not configured. Please try again later.'}};
  try{
    const response=await fetch(new URL('/api/chat',remote),{method:'POST',headers:headers(),body:JSON.stringify({message:data.message.trim(),history:cleanHistory(data.history)}),signal:AbortSignal.timeout(240000)});
    return {status:response.status,body:await response.json()};
  }catch{return {status:503,body:{error:'The library assistant is temporarily unavailable. Please try again shortly.'}};}
}
