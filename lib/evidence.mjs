export function validateEvidence(payload,sources){
  if(!payload||typeof payload!=='object'||Array.isArray(payload)||Object.keys(payload).sort().join(',')!=='answer,citations,status')throw new Error('Unexpected response fields');
  if(!['answered','insufficient','conflict'].includes(payload.status)||typeof payload.answer!=='string'||!payload.answer.trim()||!Array.isArray(payload.citations))throw new Error('Invalid response shape');
  const norm=s=>s.replace(/\s+/g,' ').trim(),lookup=new Map(sources.map(s=>[s.source_id,s]));
  for(const c of payload.citations)if(!c||Object.keys(c).sort().join(',')!=='quote,source_id'||typeof c.source_id!=='string'||!lookup.has(c.source_id)||typeof c.quote!=='string'||!norm(c.quote)||!norm(lookup.get(c.source_id).text).includes(norm(c.quote)))throw new Error('Invalid evidence quote');
  if(payload.status==='answered'&&!payload.citations.length)throw new Error('Answered response needs evidence');
  if(payload.status==='conflict'&&new Set(payload.citations.map(c=>norm(c.quote))).size<2)throw new Error('Conflict needs two excerpts');
  if(payload.status==='insufficient')return {...payload,answer:'I could not confirm this from the supplied JRU Library FAQ passages. Please ask library staff.'};
  if(payload.status==='conflict')return {...payload,answer:'The supplied FAQ passages contain conflicting guidance. Please ask library staff to confirm which applies.'};
  return payload;
}
