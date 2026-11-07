// Real browser checks of the local product. Proposal fixtures below are
// explicitly software tests, not evidence of a live Switch conversation.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';

const output = 'artifacts/browser';
await mkdir(output, {recursive: true});
const server = spawn('python3', ['ripple.py', 'serve'], {stdio: ['ignore', 'pipe', 'pipe']});
let logs = '';
server.stdout.on('data', data => {logs += data;});
server.stderr.on('data', data => {logs += data;});
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1440, height: 1000}, permissions: ['clipboard-read', 'clipboard-write']});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));

async function visible(selector) {await page.locator(selector).waitFor({state: 'visible'});}
async function screenshot(name) {await page.screenshot({path: `${output}/${name}.png`, fullPage: true});}
async function fixture(code, ...args) {
  const result = spawnSync('python3', ['-c', code, ...args], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

try {
  for (let i = 0; i < 50; i++) {
    try {const r = await fetch('http://127.0.0.1:8790/api/state'); if (r.ok) break;} catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await page.goto('http://127.0.0.1:8790/');
  await visible('#empty-state');
  await screenshot('01-empty-desktop');
  await page.getByRole('button', {name: 'Create a change'}).click();
  await visible('#new-dialog');
  await page.locator('#request-form button[type=submit]').click();
  await visible('#change-title');
  assert.match(await page.locator('#change-title').textContent(), /Basic file limit: 5 to 10/);
  assert.match(await page.locator('#next-step').textContent(), /Connect Switch/);
  const state = await (await fetch('http://127.0.0.1:8790/api/state')).json();
  const cid = state.changes.at(-1).id;
  assert.deepEqual(state.changes.at(-1).inspections, {});
  await screenshot('02-change-awaiting-switch');
  await page.locator('#next-step [data-action=connect]').click();
  await visible('#switch-dialog');
  assert.match(await page.locator('#switch-current-state').textContent(), /No room connected/);
  await page.locator('#switch-dialog [data-close]').click();
  await page.locator('#next-step [data-action=handoff]').click();
  await visible('#handoff-dialog');
  assert.match(await page.locator('#handoff-message').inputValue(), new RegExp(cid));
  await page.locator('#copy-handoff').click();
  assert.match(await page.evaluate(() => navigator.clipboard.readText()), /@ripple-docs/);
  await page.keyboard.press('Escape');
  await page.locator('[data-tab=files]').click();
  assert.match(await page.locator('#file-list').textContent(), /No proposed file edits/);
  await page.locator('[data-tab=systems]').click();
  await page.locator('#test-ten').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('rejected'));
  await fixture(`import sys\nfrom pathlib import Path\nsys.path.insert(0,'tests')\nfrom test_workflow import WorkflowTests\nfrom ripple.core import Ripple\nf=WorkflowTests(); f.root=Path.cwd(); f.app=Ripple(f.root); f.cid=sys.argv[1]\nfor area, patch in f.patches().items(): f.app.propose(f.cid,area,patch,'Browser test fixture: update '+area,actor='browser test fixture')`, cid);
  await page.locator('[data-tab=overview]').click();
  await page.waitForFunction(() => document.querySelector('#next-step').textContent.includes('proposals are ready'));
  await page.locator('[data-action=check]').click();
  await page.waitForFunction(() => document.querySelector('#change-status').textContent === 'Your review needed');
  await page.locator('#next-step [data-action=files]').click();
  assert.equal(await page.locator('.file-diff').count(), 5);
  await page.locator('.file-diff').first().locator('summary').click();
  await visible('.file-diff[open] .diff-grid');
  await screenshot('03-file-review-test-fixture');
  await page.locator('[data-tab=overview]').click();
  await page.locator('[data-action=approve]').click();
  await page.waitForFunction(() => document.querySelector('#change-status').textContent === 'Approved');
  await fixture(`import sys\nfrom pathlib import Path\nfrom ripple.core import Ripple,AREAS\na=Ripple(Path.cwd())\nfor area in AREAS: a.apply(sys.argv[1],area,actor='browser test fixture')`, cid);
  await page.waitForFunction(() => document.querySelector('#change-status').textContent === 'Verified');
  await page.locator('[data-tab=systems]').click();
  await page.locator('#test-ten').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('accepted'));
  await page.locator('#test-eleven').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('rejected'));
  assert.match(await page.locator('#forecast').textContent(), /7.81/);
  await page.locator('[data-tab=overview]').click();
  await page.setViewportSize({width: 390, height: 844});
  await screenshot('04-mobile-test-fixture');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile page overflows horizontally');
  await page.setViewportSize({width: 1440, height: 1000});
  await page.locator('.new-button').click();
  await visible('#new-dialog');
  assert.equal(await page.locator('#limit').inputValue(), '15');
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, [], 'Browser JavaScript errors');
  await writeFile(`${output}/result.json`, JSON.stringify({passed: true, screenshots: 4, note: 'Real browser interaction. Proposal preparation and application used explicit deterministic test fixtures. No live Switch run was simulated or claimed.'}, null, 2));
  console.log('Browser checks passed: create change, explicit connection state, manual handoff/copy, file review, approval, verified result, mobile layout, and another change.');
} catch (error) {
  await screenshot('failure');
  throw error;
} finally {
  await writeFile(`${output}/server.log`, logs);
  await browser.close();
  server.kill('SIGTERM');
}
