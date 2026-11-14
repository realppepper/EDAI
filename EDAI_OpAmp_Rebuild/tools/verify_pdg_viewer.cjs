// Local UI smoke check; no remote resources or circuit execution.
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const {chromium} = require(process.argv[4]);
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
    assert.equal(await page.locator('#ports').innerText(),'8');
    await page.locator('[data-node]').first().focus();
    await page.locator('[data-node]').first().press('Enter');
    assert.equal(await page.locator('#detail-title').innerText(),'OUT1');
    await page.locator('[data-edge]').first().focus();
    await page.locator('[data-edge]').first().press('Enter');
    assert.match(await page.locator('#detail').innerText(),/수치 지연: 미정/);
    await page.selectOption('#origin','engineering_interpretation');
    assert.equal(await page.locator('.edge[data-origin="datasheet_statement"]').first().evaluate(el=>el.style.opacity),'0.1');
    await page.selectOption('#analysis','ac');
    assert.match(await page.locator('#operations').innerText(),/AC 주파수 스윕/);
    await page.selectOption('#analysis','tran');
    assert.match(await page.locator('#schedule-status').innerText(),/입력 대기/);
    assert.equal(errors.length,0,errors.join('\n'));
    await page.selectOption('#origin','all');
    await page.selectOption('#analysis','ac');
    await page.screenshot({path:path.resolve(process.argv[3]),fullPage:true});
    process.stdout.write('Viewer smoke checks passed: node/edge details, origin filter, analysis selection; zero page errors.\n');
  } finally { await browser.close(); }
})().catch(e=>{process.stderr.write(String(e)+'\n');process.exitCode=1;});
