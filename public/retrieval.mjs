// Lightweight BM25 retrieval. Original experimental MiniLM/Chroma metrics do not apply.
const STOP = new Set('a an the is are was were be been it its i me my we you your can could would should do does did how what when where which who why to of in at on for from and or with have has please tell about library libraries jru'.split(' '));
const ALIASES = { hours:['hour','open','opening','closing','schedule'], borrow:['borrowing','borrowed','loan','loans','checkout'], renew:['renewal','renewals','renewing'], fines:['fine','penalty','penalties','overdue'], resources:['resource','eresources','database','databases'], location:['located','locate'], return:['returning','returns'], opac:['catalog','catalogue'], wifi:['wi-fi','wireless'], books:['book'], students:['student'] };
function stem(t) { return t.length > 4 ? t.replace(/(?:ing|es|s)$/,'') : t; }
export function tokenize(text) {
  return (String(text).toLowerCase().replace(/wi-fi/g,'wifi').match(/[\p{L}\p{N}]+/gu)||[]).filter(t=>!STOP.has(t)).map(t=> {
    for (const [key,values] of Object.entries(ALIASES)) if (key===t||values.includes(t)) return key;
    return stem(t);
  });
}
export function createRetriever(records) {
  const docs = records.map(record=> {
    const title = tokenize(record.question+' '+record.option+' '+record.category);
    const tokens = [...title,...title,...title,...tokenize(record.answer)];
    const terms = new Map(); for(const t of tokens) terms.set(t,(terms.get(t)||0)+1);
    return {record,terms,length:tokens.length,title:new Set(title)};
  });
  const df = new Map(); for(const d of docs) for(const t of d.terms.keys()) df.set(t,(df.get(t)||0)+1);
  const average = docs.reduce((s,d)=>s+d.length,0)/Math.max(1,docs.length);
  return function search(query, limit=3) {
    const terms = [...new Set(tokenize(query))]; if (!terms.length) return [];
    return docs.map(d=> {
      let score=0, matched=0, titleMatched=0;
      for(const t of terms) {
        const tf=d.terms.get(t)||0; if(!tf) continue;
        matched++; if(d.title.has(t)) titleMatched++;
        const idf=Math.log(1+(docs.length-(df.get(t)||0)+0.5)/((df.get(t)||0)+0.5));
        score+=idf*(tf*2.2)/(tf+1.2*(0.25+0.75*d.length/average));
      }
      const coverage=matched/terms.length;
      return {...d.record,score:score*(0.3+0.7*coverage),coverage,titleCoverage:titleMatched/terms.length};
    }).filter(d=>d.score>0).sort((a,b)=>b.score-a.score).slice(0,limit);
  };
}
export const REFUSAL = "I couldn’t confirm that from the supplied JRU Library FAQs. Please check with library staff for an accurate answer.";
export function retrieveAnswer(question, search, history=[]) {
  const q=question.trim();
  if (/^(hi|hello|hey|good (morning|afternoon|evening))[!. ]*$/i.test(q)) return {answer:'Hello! I can help you find library hours, borrowing rules, online resources, and more. What would you like to know?',sources:[],mode:'faq',refused:false};
  if (/^(thank(s| you)|salamat)[!. ]*$/i.test(q)) return {answer:'You’re welcome! Let me know if you have another library question.',sources:[],mode:'faq',refused:false};
  if (/password|account\s*(?:number|no\.)|right now|at this exact moment|on duty now|currently available/i.test(q)) return {answer:REFUSAL,sources:[],mode:'faq',refused:true};
  let query=q;
  if (/^(and |what about |how about |does (it|that) |can (i|we) (do that|also)|is (it|that) )/i.test(q)) {
    const prior=[...history].reverse().find(t=>t.role==='user');
    if(prior) query=prior.content.slice(0,500)+' '+q;
  }
  const candidates=search(query,9);
  // Prefer a similarly ranked general policy to an isolated sub-option, such as
  // "Fiction: 2.00 per day", when the visitor asked about overdue fines broadly.
  const general=candidates.find(s=>!s.option && s.score>=candidates[0]?.score*0.85);
  const hits=(general?[general,...candidates.filter(s=>s.id!==general.id)]:candidates).slice(0,3);
  if(!hits.length || hits[0].score<2 || hits[0].coverage<0.5 || (hits[0].titleCoverage===0 && hits[0].coverage<1)) return {answer:REFUSAL,sources:[],mode:'faq',refused:true};
  const sources=hits.filter(s=>s.score>=hits[0].score*0.48).map((s,i)=>({n:i+1,id:s.id,ref:s.source_ref,refs:s.source_refs,question:s.question+(s.option?' · '+s.option:''),option:s.option,category:s.category,text:s.answer,score:Number(s.score.toFixed(2))}));
  return {answer:(sources[0].option?sources[0].option+': ':'')+sources[0].text+' [1]',sources,mode:'faq',refused:false,retrievalQuery:query};
}
