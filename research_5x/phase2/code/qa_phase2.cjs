// Local report QA. No network, trades or production interaction.
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../2026-10-11_earnings_acceleration');
(async()=>{
 const out=path.join(root,'visual_qa');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.join(root,'research_report.html')).href);
 await page.screenshot({path:path.join(out,'opening.png')});
 const links=await page.locator('a[href]').evaluateAll(as=>as.map(a=>a.getAttribute('href')));
 const broken=links.filter(h=>!h.startsWith('#')&&!/^https?:/.test(h)).filter(h=>!fs.existsSync(path.resolve(root,h.split('#')[0])));
 const anchors=links.filter(h=>h.startsWith('#'));let missing=[];
 for(const h of anchors)if(!await page.locator(h).count())missing.push(h);
 const desktopOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await page.locator('#holding').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'holding.png')});
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'mobile.png')});
 const mobileOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 const check={brokenLocalLinks:broken,missingAnchors:missing,desktopOverflow,mobileOverflow,pageErrors:errors,links:links.length,tables:await page.locator('table').count()};
 check.pass=!broken.length&&!missing.length&&!desktopOverflow&&!mobileOverflow&&!errors.length;
 fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify(check,null,2));console.log(JSON.stringify(check));await browser.close();if(!check.pass)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
