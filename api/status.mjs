import { status } from '../lib/chat.mjs';
export default async function handler(req,res) {
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='GET') {res.setHeader('Allow','GET');return res.status(405).json({error:'Use GET.'});}
  const result=await status();
  return res.status(result.ready?200:503).json(result);
}
