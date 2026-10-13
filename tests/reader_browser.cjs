// Run against an isolated COPY of the real 330-PDF development library (see docs/READER-TESTS.md).
const {chromium}=require('playwright');
const assert=require('assert');
const fs=require('fs');
(async()=>{
 const base=process.env.TEST_URL||'http://127.0.0.1:9702';
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1600,height:1100},permissions:['clipboard-read','clipboard-write']});
 const page=await context.newPage();let errors=[];page.on('pageerror',e=>errors.push(e.message));
 const report={};
 const api=async url=>{const res=await page.request.get(base+url);assert.equal(res.status(),200);return res.json()};
 const waitLayer=async role=>{await page.locator(`[data-role=${role}] .text-layer .word`).first().waitFor();};
 async function selectWord(role,word){
  const target=page.locator(`[data-role=${role}] .word`).filter({hasText:word}).first();await target.scrollIntoViewIfNeeded();
  const box=await target.boundingBox();assert(box&&box.width>0&&box.height>0);await page.mouse.move(box.x+1,box.y+box.height*.55);await page.mouse.down();await page.mouse.move(box.x+box.width-1,box.y+box.height*.55,{steps:15});await page.mouse.up();
  const selected=await page.evaluate(()=>getSelection().toString());assert(selected.trim().length>1,'Native mouse selection must return actual text');
  await page.keyboard.press('Control+c');const copied=await page.evaluate(()=>navigator.clipboard.readText());assert(copied.trim().length>1);
  return {selected,copied};
 }
 try{
  await page.goto(base+'/?q=hybridoma&year=2019&season=s&component=21&kind=qp');
  assert.equal(await page.locator('.result').count(),1);assert((await page.locator('.location').innerText()).includes('第 3 页'));
  const hit=(await api('/api/search?q=hybridoma&year=2019&season=s&component=21&kind=qp')).items[0];assert.equal(hit.filename,'9700_s19_qp_21.pdf');assert.equal(hit.label,'1');
  report.real_search={filename:hit.filename,label:hit.label,page:hit.hit_page};
  await page.getByRole('button',{name:'复制题目文字',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('复制题目文字：已复制'));assert((await page.evaluate(()=>navigator.clipboard.readText())).includes('hybridoma'));
  await page.getByRole('button',{name:'复制答案文字',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('复制答案文字：已复制'));assert((await page.evaluate(()=>navigator.clipboard.readText())).includes('1(b)(iii)'));report.result_copy_buttons=true;

  await page.getByRole('link',{name:'查看对应答案',exact:true}).click();await waitLayer('question');await waitLayer('answer');
  await page.waitForFunction(()=>document.querySelector('#answer-status').textContent.includes('自动定位'));
  assert.equal(await page.locator('[aria-label="答案 PDF 页码"]').inputValue(),'5');
  assert((await page.locator('[data-role=answer]>small').innerText()).includes('9700_s19_ms_21.pdf'));
  report.native_selection=await selectWord('question','hybridoma');
  report.ms_selection=await selectWord('answer','secondary');
  await page.getByRole('button',{name:'复制答案文字',exact:true}).click();const fullAnswer=await page.evaluate(()=>navigator.clipboard.readText());assert(fullAnswer.includes('1(b)(iii)'));assert(!fullAnswer.includes('2(a)'));report.cross_page_answer={pages:[5,6],includes_subquestion:true};
  await page.locator('#question-label').fill('1(b)(iii)');await page.locator('#question-form button').first().click();await page.waitForFunction(()=>document.querySelector('[aria-label="答案 PDF 页码"]').value==='6');await waitLayer('answer');
  assert((await page.locator('#answer-text').textContent()).includes('target cells'));await page.waitForFunction(()=>document.querySelector('#copy-question').disabled===false);assert.equal(await page.locator('[aria-label="题目 PDF 页码"]').inputValue(),'4');assert(!(await page.locator('#copy-answer').isDisabled()));
  report.subquestion={label:'1(b)(iii)',qpPage:4,msPage:6};
  await page.getByRole('button',{name:'只看题目',exact:true}).click();assert(!(await page.locator('[data-role=answer]').isVisible()));await page.getByRole('button',{name:'只看答案',exact:true}).click();assert.equal(await page.locator('[aria-label="答案 PDF 页码"]').inputValue(),'6');await page.getByRole('button',{name:'题目 / 答案并排',exact:true}).click();
  await page.locator('[data-role=question] .page-scroll').evaluate(n=>n.scrollTop=180);await page.getByRole('button',{name:'只看答案',exact:true}).click();await page.getByRole('button',{name:'题目 / 答案并排',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[data-role=question] .page-scroll').scrollTop>=175);
  report.independent_reading_position=true;
  await page.locator('#question-label').fill('99(a)');await page.locator('#question-form button').first().click();await page.waitForFunction(()=>document.querySelector('#answer-status').textContent.includes('尚未定位到 99(a)'));
  assert(await page.locator('#copy-answer').isDisabled());
  await page.locator('[data-role=answer] [aria-label="卷内搜索"]').fill('phospholipids');await page.locator('[data-role=answer] .within-search button').click();await page.locator('[data-role=answer] .within-hits button').first().waitFor();report.honest_fallback=true;
  await page.locator('#question-label').fill('1(b)(iii)');await page.locator('#question-form button').first().click();await page.waitForFunction(()=>document.querySelector('#copy-answer').disabled===false);
  await page.locator('#manual-location summary').click();
  for(const [name,value] of Object.entries({label:'1(b)(iii)',start:'6',end:'6',top:'13.2',bottom:'59.2',left:'7.3',right:'93.5'}))await page.locator(`#answer-correction [name=${name}]`).fill(value);
  await page.getByRole('button',{name:'保存已核对范围',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#answer-status').textContent.includes('已人工确认答案范围'));
  assert(!(await page.locator('#copy-answer').isDisabled()));report.manual_ui_save=true;
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'撤销当前题号的新答案修正',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#answer-status').textContent.includes('自动定位'));
  await page.locator('#manual-location summary').click();
  await page.screenshot({path:'work/reader-split.png',fullPage:true});
  // Exercise old OCR text without coordinates. Only this one page is reprocessed.
  await page.goto(base+'/viewer/70?page=9');if((await api('/api/reader/70/page/9')).needs_coordinates){await page.getByRole('button',{name:'补齐本页文字坐标',exact:true}).click();report.single_page_coordinate_repair=true;}await page.waitForFunction(()=>document.querySelector('[data-role=question] .layer-status').textContent.startsWith('OCR 文字层'),{timeout:60000});await waitLayer('question');
  report.ocr_selection=await selectWord('question','Explain');
  const layout=await api('/api/reader/70/page/9');assert.equal(layout.source,'ocr');assert.equal(layout.needs_coordinates,false);
  await page.screenshot({path:'work/reader-ocr.png',fullPage:true});
  await page.goto(base+'/?year=2019&season=s&component=21&q=hybridoma');await page.screenshot({path:'work/reader-search.png',fullPage:true});
  assert.equal(await page.locator('select').count(),0);await page.getByRole('link',{name:'22',exact:true}).click();assert(page.url().includes('component=22'));assert(page.url().includes('year=2019'));assert(page.url().includes('season=s'));assert(page.url().includes('q=hybridoma'));report.button_combination=true;
  await page.goto(base+'/document/296');await page.locator('.unit-text[data-label="1"] summary').click();await page.waitForFunction(()=>document.querySelector('.unit-text[data-label="1"] pre').textContent.includes('hybridoma'));await page.locator('.unit-text[data-label="1"] [data-part=question]').click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('复制题目文字：已复制'));report.details_copy_text=true;
  await page.goto(base+'/?q=absurdnomatchword');assert(await page.getByText('没有找到匹配内容',{exact:true}).isVisible());
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.goto(base+'/viewer/296?page=3&question=1');await waitLayer('question');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));report.mobile_no_overflow=true;
  assert.deepEqual(errors,[]);report.js_errors=errors;report.status='PASS';fs.writeFileSync('work/reader-browser-results.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
