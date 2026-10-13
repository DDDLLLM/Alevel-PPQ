/* Original PDF pixels + an aligned selectable text layer. No remote viewer/CDN. */
(()=>{
const config=JSON.parse(document.querySelector('#reader-config').textContent);
const grid=document.querySelector('#reader-grid'),panels={},savedKey=id=>'biology-reader-v2-'+id;
let currentLabel=config.question,answer=null,question=null,resolveSerial=0;
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
const readSaved=id=>{try{return JSON.parse(localStorage.getItem(savedKey(id))||'{}')}catch{return {}}};
async function copy(text){try{await navigator.clipboard.writeText(text);notify('已复制文字')}catch{notify('剪贴板不可用，请展开文字后选择并复制。')}}
function setMode(mode){grid.dataset.mode=mode;for(const [k,p] of Object.entries(panels)){const position=p.root.hidden?(p.lastPosition||{top:0,left:0}):{top:p.scroller.scrollTop,left:p.scroller.scrollLeft};p.lastPosition=position;p.root.hidden=mode!=='both'&&mode!==k;if(!p.root.hidden)requestAnimationFrame(()=>{p.scroller.scrollTop=position.top;p.scroller.scrollLeft=position.left})}}
function paintHighlights(p){p.sheet.querySelectorAll('.range-highlight').forEach(n=>n.remove());if(p.role!=='answer'||!answer)return;for(const s of answer.segments||[]){if(s.page!==p.page)continue;const r=el('div','range-highlight');r.style.cssText=`left:${s.box[0]/s.width*100}%;top:${s.box[1]/s.height*100}%;width:${(s.box[2]-s.box[0])/s.width*100}%;height:${(s.box[3]-s.box[1])/s.height*100}%`;p.sheet.append(r)}}
function makePanel(doc,role){
 const state=readSaved(doc.id),root=el('section','reader-panel'),bar=el('div','reader-controls'),title=el('strong','',role==='answer'?'评分标准 MS':(doc.kind==='qp'?'题目 QP':'文件'));
 root.dataset.role=role;const name=el('small','muted',doc.filename);const prev=el('button','secondary','←'),next=el('button','secondary','→'),input=el('input');input.type='number';input.min=1;input.max=doc.page_count;input.setAttribute('aria-label',role==='answer'?'答案 PDF 页码':'题目 PDF 页码');const total=el('span','',`/ ${doc.page_count}`),jump=el('button','secondary','跳转');
 const zoom=el('button','secondary','放大'),original=el('a','', '原 PDF ↗');original.target='_blank';original.rel='noopener';
 bar.append(title,prev,input,total,next,jump,zoom,original);const info=el('p','layer-status','正在加载文字层…'),scroller=el('div','page-scroll'),sheet=el('div','page-sheet'),img=el('img');img.draggable=false;img.alt=doc.filename;sheet.append(img);scroller.append(sheet);
 const details=el('details','page-text'),summary=el('summary','','本页文字（可复制）'),pre=el('pre'),copyPage=el('button','secondary','复制本页文字');details.append(summary,copyPage,pre);
 const form=el('form','within-search'),search=el('input');search.placeholder='卷内题号或英文关键词';search.setAttribute('aria-label','卷内搜索');const searchBtn=el('button','secondary','卷内搜索'),hits=el('div','within-hits');form.append(search,searchBtn);
 root.append(bar,name,info,form,hits,scroller,details);grid.append(root);
 const p={doc,role,root,input,info,scroller,sheet,img,pre,original,page:1,layout:null,serial:0,scale:state.scale||1,spans:[]};panels[role]=p;
 // Supply line breaks to clipboard without adding visible text over the PDF.
 root.addEventListener('copy',event=>{
  const selection=getSelection();if(!selection?.rangeCount||!p.spans.length)return;
  const range=selection.getRangeAt(0),layer=sheet.querySelector('.text-layer');
  if(!layer?.contains(range.startContainer)||!layer.contains(range.endContainer))return;
  let text='',lastY=null;
  for(const [span,w] of p.spans){if(!range.intersectsNode(span))continue;let value=span.textContent;
   if(span.contains(range.endContainer)&&range.endContainer.nodeType===3)value=value.slice(0,range.endOffset);
   if(span.contains(range.startContainer)&&range.startContainer.nodeType===3)value=value.slice(range.startOffset);
   if(!value)continue;if(lastY!==null&&Math.abs(lastY-w.box[1])>3)text=text.trimEnd()+'\n';text+=value;lastY=w.box[1];
  }
  if(text&&event.clipboardData){event.clipboardData.setData('text/plain',text);event.preventDefault()}
 });
 const save=()=>{if(root.hidden)return;p.lastPosition={top:scroller.scrollTop,left:scroller.scrollLeft};try{localStorage.setItem(savedKey(doc.id),JSON.stringify({page:p.page,top:scroller.scrollTop,left:scroller.scrollLeft,scale:p.scale}))}catch{}};
 const resize=()=>{if(!p.layout||root.hidden||!scroller.clientWidth)return;sheet.style.width=(Math.max(300,scroller.clientWidth-24)*p.scale)+'px';const scale=sheet.clientWidth/p.layout.width;const ctx=document.createElement('canvas').getContext('2d');for(const [span,w] of p.spans){const b=w.box;const font=(b[3]-b[1])*.78*scale;span.style.fontSize=font+'px';span.style.lineHeight=(b[3]-b[1])*scale+'px';ctx.font=`${font}px Arial`;const natural=ctx.measureText(w.text+' ').width;span.style.transform=`scaleX(${(b[2]-b[0])*scale/Math.max(natural,1)})`;}};
 new ResizeObserver(resize).observe(scroller);
 p.load=async(number,opts={})=>{
  number=Number(number);if(!Number.isInteger(number)||number<1||number>doc.page_count){notify('PDF 页码超出范围');return}
  const serial=++p.serial;p.page=number;input.value=number;p.layout=null;p.spans=[];info.textContent='正在加载页面与文字层…';img.src=`/page/${doc.id}/${number}.png`;original.href=`/pdf/${doc.id}#page=${number}`;sheet.querySelectorAll('.text-layer,.range-highlight').forEach(n=>n.remove());pre.textContent='正在加载…';scroller.scrollTop=0;
  try{
   const data=await api(`/api/reader/${doc.id}/page/${number}`);if(serial!==p.serial)return;p.layout=data;pre.textContent=data.text||'本页尚无可提取文字。';
   const layer=el('div','text-layer');layer.setAttribute('aria-label',data.source==='ocr'?'OCR 可选择文字层':'原生可选择文字层');
   const tokens=(config.query.match(/[a-z0-9]+/ig)||[]).map(t=>t.toLowerCase());
   // Words follow visual lines even when the source PDF uses rotated text objects.
   const words=[...data.words].sort((a,b)=>Math.abs(a.box[1]-b.box[1])<3?a.box[0]-b.box[0]:a.box[1]-b.box[1]);
   for(const w of words){const span=el('span',tokens.some(t=>w.text.toLowerCase().includes(t))?'word hit':'word',w.text+' ');span.style.left=w.box[0]/data.width*100+'%';span.style.top=w.box[1]/data.height*100+'%';span.dataset.text=w.text;layer.append(span);p.spans.push([span,w]);}
   sheet.append(layer);sheet.style.aspectRatio=`${data.width}/${data.height}`;paintHighlights(p);resize();
   info.replaceChildren(document.createTextNode(data.needs_coordinates?'本页保留已有 OCR 文字，但缺少坐标。':data.source==='ocr'?'OCR 文字层 · 可选择复制，请核对原卷':'原生文字层 · 可选择复制'));
   if(data.needs_coordinates){const repair=el('button','secondary','补齐本页文字坐标');repair.onclick=async()=>{repair.disabled=true;info.firstChild.textContent='正在识别此页坐标，已有 OCR 和索引保持不变…';try{await api(`/api/reader/${doc.id}/page/${number}/coordinates`,{method:'POST'});await p.load(number);if(role==='answer')await loadDirectory(true)}catch(e){notify(e.message);repair.disabled=false;info.firstChild.textContent='补齐失败；原有文字仍可在下方查看。'}};info.append(repair)}
   if(opts.y!==undefined)scroller.scrollTop=Math.max(0,opts.y/data.height*sheet.clientHeight-30);else if(opts.restore){scroller.scrollTop=state.top||0;scroller.scrollLeft=state.left||0}save();
  }catch(e){if(serial!==p.serial)return;info.textContent='加载失败：'+e.message;const retry=el('button','secondary','重试');retry.onclick=()=>p.load(number,opts);info.append(retry);pre.textContent='文字加载失败，请重试。'}
 };
 prev.onclick=()=>p.load(p.page-1);next.onclick=()=>p.load(p.page+1);jump.onclick=()=>p.load(input.value);input.onkeydown=e=>{if(e.key==='Enter')p.load(input.value)};zoom.onclick=()=>{p.scale=p.scale===1?1.6:1;zoom.textContent=p.scale===1?'放大':'适应宽度';resize();save()};scroller.addEventListener('scroll',save,{passive:true});copyPage.onclick=()=>copy(p.pre.textContent);
 form.onsubmit=async e=>{e.preventDefault();searchBtn.disabled=true;hits.textContent='正在搜索…';try{const data=await api(`/api/reader/${doc.id}/find?q=${encodeURIComponent(search.value)}`);hits.replaceChildren();if(!data.items.length)hits.textContent='本卷没有找到匹配文字；可以查看题号目录或核对原 PDF。';for(const item of data.items){const b=el('button','secondary',`PDF 第 ${item.page} 页 · ${item.text}`);b.onclick=()=>p.load(item.page);hits.append(b)}}catch(e){hits.textContent=e.message}finally{searchBtn.disabled=false}};
 return p;
}
const qp=makePanel(config.doc,'question');const ms=config.ms?makePanel(config.ms,'answer'):null;
document.querySelector('#show-both').onclick=()=>setMode(ms?'both':'question');document.querySelector('#show-question').onclick=()=>setMode('question');document.querySelector('#show-answer')?.addEventListener('click',()=>setMode('answer'));
function showAnswer(a){
 answer=a;document.querySelector('#answer-status').textContent=({'manual':'已人工确认','automatic':'自动定位','unlocated':'尚未定位'}[a.status]||'')+' · '+a.message;
 document.querySelector('#copy-answer').disabled=!a.complete||!a.text;document.querySelector('#answer-text').textContent=a.text||'答案范围尚未确定，请在 MS 中核对；可选择本页文字复制。';
 const pages=document.querySelector('#answer-pages');pages.replaceChildren();for(const [i,s] of (a.segments||[]).entries()){const b=el('button','secondary',`${a.label} · MS 第 ${s.page} 页${a.segments.length>1?' · 第 '+(i+1)+' 段':''}`);b.onclick=()=>ms.load(s.page,{y:s.box[1]});pages.append(b)}
 if(ms){const s=a.segments?.[0];if(s)ms.load(s.page,{y:s.box[1]});else if(a.page)ms.load(a.page);else paintHighlights(ms)}
}
async function lookup(value,navigateQuestion=true){
 const serial=++resolveSerial;currentLabel=value.trim();document.querySelector('#question-label').value=currentLabel;const manual=document.querySelector('#answer-correction');if(manual)manual.elements.label.value=currentLabel;
 document.querySelector('#answer-status').textContent='正在查找题号与评分标准位置…';document.querySelector('#copy-answer').disabled=true;document.querySelector('#copy-question').disabled=true;
 try{const a=await api(`/api/reader/${config.doc.id}/answer?question=${encodeURIComponent(currentLabel)}`);if(serial!==resolveSerial)return;showAnswer(a);
  question=currentLabel?await api(`/api/reader/${config.doc.id}/question?question=${encodeURIComponent(currentLabel)}`):null;if(serial!==resolveSerial)return;
  document.querySelector('#copy-question').disabled=!question?.complete;
  document.querySelector('#question-status').textContent=question?.complete?`题目 ${currentLabel} · ${question.confidence==='manual'?'已人工确认':'自动识别'} · PDF 第 ${question.page}–${question.page_end} 页`:'题号或子题范围尚未确认；左侧保留当前阅读页，请核对原卷。';
  if(navigateQuestion&&question?.complete)await qp.load(question.page,{y:question.segments?.[0]?.box[1]||0});document.querySelector('#question-text').textContent=question?.text||'当前题目范围未确认。请核对原卷，可复制本页文字，或在“文件详情”修正题目范围。';
  const u=new URL(location.href);u.searchParams.set('question',currentLabel);history.replaceState(null,'',u);
 }catch(e){document.querySelector('#answer-status').textContent='定位失败：'+e.message}
}
async function loadDirectory(){if(!ms)return;const out=document.querySelector('#answer-labels');try{const d=await api(`/api/reader/${ms.doc.id}/directory`);out.replaceChildren();if(!Object.keys(d.entries).length)out.textContent=d.reason;for(const k of Object.keys(d.entries).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}))){const b=el('button','secondary',k);b.onclick=()=>lookup(k);out.append(b)}if(d.pending_pages.length)out.append(el('p','muted',`以下 MS 页面缺少文字坐标：${d.pending_pages.join('、')}；可在相应页补齐。`))}catch(e){out.textContent='目录加载失败：'+e.message}}
if(config.doc.kind==='qp'){
 document.querySelector('#question-form').onsubmit=e=>{e.preventDefault();lookup(document.querySelector('#question-label').value)};
 document.querySelector('#copy-question').onclick=()=>question?.complete&&copy(question.text);document.querySelector('#copy-answer').onclick=()=>answer?.complete&&copy(answer.text);
 document.querySelector('#answer-directory').addEventListener('toggle',e=>{if(e.target.open)loadDirectory()});
 document.querySelector('#answer-correction')?.addEventListener('submit',async e=>{e.preventDefault();const f=e.target,b=f.querySelector('button');b.disabled=true;try{
  const v=Object.fromEntries(new FormData(f)),start=Number(v.start),end=Number(v.end),ranges=[];
  if(end<start||end-start>99)throw Error('页码范围错误或过长');
  for(let n=start;n<=end;n++){const p=await api(`/api/reader/${ms.doc.id}/page/${n}`);ranges.push({page:n,box:[p.width*Number(v.left)/100,n===start?p.height*Number(v.top)/100:0,p.width*Number(v.right)/100,n===end?p.height*Number(v.bottom)/100:p.height]})}
  await api(`/api/reader/${config.doc.id}/answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:v.label,ms_doc_id:ms.doc.id,ranges})});await lookup(v.label);notify('答案范围已保存，重建索引后仍保留。');
 }catch(err){notify(err.message)}finally{b.disabled=false}});
 document.querySelector('#remove-answer-correction')?.addEventListener('click',async()=>{if(!currentLabel||!confirm('撤销当前题号的新答案范围修正？旧题目目录中的页码修正不受影响。'))return;try{await api(`/api/reader/${config.doc.id}/answer/reset`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:currentLabel})});await lookup(currentLabel)}catch(e){notify(e.message)}});
}
(async()=>{setMode(ms?'both':'question');await qp.load(config.explicit_page?config.page:(readSaved(config.doc.id).page||config.page),{restore:!config.explicit_page});if(ms)await ms.load(readSaved(ms.doc.id).page||1,{restore:true});if(config.doc.kind==='qp')await lookup(currentLabel,false);if(config.focus==='answer'&&ms&&innerWidth<900)setMode('answer')})();
})();
