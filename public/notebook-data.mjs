export function notebookRecords(source) {
  const records=[];
  const {chunk_size:size,chunk_overlap:overlap}=source.baseline;
  if(!(size>0&&overlap>=0&&overlap<size))throw new Error('Invalid notebook chunking configuration');
  for(const page of source.pages)for(let start=0;start<page.text.length;start+=size-overlap){
    const answer=page.text.slice(start,start+size).trim();if(!answer)continue;
    const id=records.length,ref=`PDF page ${page.page} · chunk ${id}`;
    records.push({id:`S${id}`,chunk_id:id,page:page.page,source_sheet:`PDF page ${page.page}`,source_ref:ref,source_refs:[ref],source_document:source.source_document,category:'Notebook PDF passage',question:`PDF page ${page.page} · passage ${id}`,option:'',answer});
  }
  return records;
}
