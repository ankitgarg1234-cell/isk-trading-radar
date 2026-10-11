/* Local visual QA; no app UI or production changes. */
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const out=path.resolve(__dirname,'..'),dir=path.join(out,'visual_qa');fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const checks=[];
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000},deviceScaleFactor:1});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('file://'+path.join(out,'research_report.html'));await page.waitForLoadState('load');
  await page.screenshot({path:path.join(dir,width===1440?'opening.png':'mobile.png')});
  const state=await page.evaluate(()=>({bodyWidth:document.body.scrollWidth,viewWidth:innerWidth,tables:document.querySelectorAll('table').length,images:[...document.images].map(i=>({complete:i.complete,width:i.naturalWidth})),links:[...document.querySelectorAll('a')].map(a=>a.getAttribute('href'))}));
  const missing=state.links.filter(v=>!v.startsWith('#')&&!v.includes('://')&&!fs.existsSync(path.resolve(out,v)));
  checks.push({width,...state,missingLocalLinks:missing,pageErrors:errors,pass:state.bodyWidth<=width&&state.images.every(i=>i.complete&&i.width>0)&&!missing.length&&!errors.length});
  if(width===1440){for(const id of ['finding','cohort','decision']){await page.locator('#'+id).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,id+'.png')});}}
  await page.close();
 }
 await browser.close();fs.writeFileSync(path.join(dir,'checks.json'),JSON.stringify(checks,null,2)+'\n');
 console.log(JSON.stringify(checks.map(({width,tables,missingLocalLinks,pageErrors,pass})=>({width,tables,missingLocalLinks,pageErrors,pass})),null,2));
 if(!checks.every(x=>x.pass))process.exit(1);
})();
