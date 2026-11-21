import { chat } from '../lib/chat.mjs';
export default async function handler(req,res) {
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='POST') { res.setHeader('Allow','POST'); return res.status(405).json({error:'Use POST.'}); }
  try {
    let data=req.body;
    if(typeof data==='string') { if(data.length>12000) return res.status(413).json({error:'Request too large.'}); data=JSON.parse(data); }
    if(JSON.stringify(data??{}).length>12000) return res.status(413).json({error:'Request too large.'});
    const result=await chat(data); return res.status(result.status).json(result.body);
  } catch(error) { console.error('Chat request failed:',error.name); return res.status(400).json({error:'Unable to read this request.'}); }
}
