// Run against an isolated, empty test server: BIOLOGY_PORT=9701 BIOLOGY_DATA=<temp> python app.py
// Supply REAL_PDF_DIR containing the two real m16 qp12/ms12 PDF files.
const {chromium}=require('playwright');
const path=require('path');
const fs=require('fs');
const assert=require('assert');
(async()=>{
 const base=process.env.TEST_URL||'http://127.0.0.1:9701';
 if(!process.env.REAL_PDF_DIR)throw Error('REAL_PDF_DIR is required; no fabricated seed data');
 const files=['9700_m16_qp_12.pdf','9700_m16_ms_12.pdf'].map(n=>path.join(process.env.REAL_PDF_DIR,n));
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(base+'/import');
  await page.locator('#files').setInputFiles(files);
  await page.getByRole('button',{name:'导入并建立索引'}).click();
  await page.waitForFunction(()=>document.querySelector('#upload-state').textContent.includes('已处理 2'),{timeout:30000});
  assert.equal(await page.locator('#upload-results .success').count(),2);
  const health=await (await page.request.get(base+'/health')).json();assert.equal(health.documents,2);
  await page.getByRole('button',{name:'导入并建立索引'}).click();
  await page.waitForFunction(()=>document.querySelectorAll('#upload-results .success').length===2&&document.querySelector('#upload-state').textContent.includes('已处理 2'));
  assert((await page.locator('#upload-results').innerText()).includes('已存在'));
  assert.equal((await (await page.request.get(base+'/health')).json()).documents,2);
  await page.goto(base+'/?year=2016&season=m&component=12&kind=qp');await page.locator('#q').fill('mitochondria');
  await Promise.all([page.waitForURL(/q=mitochondria/),page.locator('#search-form button').click()]);
  assert.equal(await page.locator('.result').count(),1);
  assert((await page.locator('.location').innerText()).includes('第 6 页'));
  assert((await page.locator('mark').first().innerText()).includes('mitochondria'));
  const ms=page.locator('.result-bottom a').filter({hasText:'查看对应答案'});assert.equal(await ms.count(),1);
  const msHref=await ms.getAttribute('href');assert.equal((await page.request.get(base+msHref)).status(),200);
  await page.getByRole('link',{name:'查看题目'}).click();assert(page.url().includes('page=6'));
  await page.locator('[data-role=question] .page-sheet img').waitFor();await page.waitForFunction(()=>document.querySelector('.page-sheet img').naturalWidth>0);
  await page.goto(base+'/?q=zzzzzznovalue');assert(await page.getByText('没有找到匹配内容').isVisible());
  await page.goto(base+'/coverage');assert(await page.getByRole('link',{name:'2026',exact:true}).isVisible());
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',browser:'Chromium',new_real_pdf_upload:true,duplicate_import:true,
    real_keyword_search:true,combined_filters:true,highlight:true,page6_viewer:true,mark_scheme_opens:true,
    empty_state:true,year_coverage:true,mobile_no_overflow:true,page_errors:errors},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
