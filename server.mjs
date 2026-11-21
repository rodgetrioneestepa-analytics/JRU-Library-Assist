import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// Node's built-in .env reader keeps credentials on the server.
const root=fileURLToPath(new URL('.',import.meta.url));
if(existsSync(path.join(root,'.env'))) process.loadEnvFile(path.join(root,'.env'));
const {chat,status}=await import('./lib/chat.mjs');
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml'};
const send=(res,code,body)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
const server=http.createServer(async(req,res)=> {
  res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('X-Frame-Options','DENY');
  const url=new URL(req.url,'http://localhost');
  if(url.pathname==='/api/status') return req.method==='GET'?send(res,200,status()):send(res,405,{error:'Use GET.'});
  if(url.pathname==='/api/chat') {
    if(req.method!=='POST') return send(res,405,{error:'Use POST.'});
    try {
      let body=''; for await(const chunk of req) {body+=chunk; if(body.length>12000) return send(res,413,{error:'Request too large.'});}
      const result=await chat(JSON.parse(body)); return send(res,result.status,result.body);
    } catch {return send(res,400,{error:'Unable to read this request.'});}
  }
  if(!['GET','HEAD'].includes(req.method)) return send(res,405,{error:'Method not allowed.'});
  try {
    const name=decodeURIComponent(url.pathname)==='/'?'index.html':decodeURIComponent(url.pathname).replace(/^\//,'');
    const base=path.join(root,'public'); const file=path.resolve(base,name);
    if(!file.startsWith(base+path.sep)) return send(res,403,{error:'Forbidden.'});
    const body=await readFile(file);res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:body);
  } catch {send(res,404,{error:'Page not found.'});}
});
const port=Number(process.env.PORT||3000);
server.listen(port,'127.0.0.1',()=>console.log(`Library-Assist: http://127.0.0.1:${port}`));
