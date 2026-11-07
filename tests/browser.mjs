// Browser fixtures below are deterministic tests, not Switch or model runs.
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
const state = async () => (await fetch('http://127.0.0.1:8790/api/state')).json();
const visible = async selector => page.locator(selector).waitFor({state: 'visible'});
const screenshot = async name => page.screenshot({path: `${output}/${name}.png`, fullPage: true});
async function fixture(code, ...args) {
  const result = spawnSync('python3', ['-c', code, ...args], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr || result.stdout);
}
const status = async text => page.waitForFunction(value => document.querySelector('#change-status').textContent === value, text);
const helper = "import sys\nfrom pathlib import Path\nsys.path.insert(0,'tests')\nfrom test_general import GeneralTests\nfrom ripple.core import Ripple\nf=GeneralTests(); f.root=Path.cwd(); f.app=Ripple(f.root); f.cid=sys.argv[1]\n";

try {
  for (let i = 0; i < 50; i++) {
    try {if ((await fetch('http://127.0.0.1:8790/api/state')).ok) break;} catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await page.goto('http://127.0.0.1:8790/');
  await visible('#empty-state');
  await screenshot('01-empty-desktop');
  await page.getByRole('button', {name: 'Create a change'}).click();
  await visible('#new-dialog');
  assert.equal(await page.locator('#plan, #limit').count(), 0);
  assert.equal(await page.locator('#request').inputValue(), '');
  await page.locator('[data-example=rename]').click();
  assert.match(await page.locator('#request').inputValue(), /Rename Parcel to Relay/);
  await screenshot('02-free-text-composer');
  await page.locator('#request-form [data-mode=create]').click();
  await visible('#change-title');
  const originalId = (await state()).changes.at(-1).id;
  assert.match(await page.locator('#change-title').textContent(), /Rename Parcel/);
  assert.equal((await state()).changes.at(-1).kind, 'general');
  await page.locator('.new-button').click();
  await visible('#new-dialog');
  assert.equal((await state()).changes.find(c => c.id === originalId).status, 'draft');
  await page.keyboard.press('Escape');
  await page.locator('#next-step [data-action=resume]').click();
  await status('Awaiting agents');
  await page.locator('.new-button').click();
  await visible('#new-dialog');
  await page.locator('[data-example=rename]').click();
  await page.locator('#request-form [data-mode=create]').click();
  await page.waitForFunction(id => document.querySelector('#change-id').textContent !== id, originalId);
  const cid = (await state()).changes.at(-1).id;
  assert.deepEqual((await state()).changes.at(-1).inspections, {});
  await page.locator('#next-step [data-action=connect]').click();
  await visible('#switch-dialog');
  assert.match(await page.locator('#switch-current-state').textContent(), /No room connected/);
  await page.keyboard.press('Escape');
  await page.locator('#next-step [data-action=handoff]').click();
  await visible('#handoff-dialog');
  const handoff = await page.locator('#handoff-message').inputValue();
  assert.match(handoff, /@ripple-app Coordinate existing change/);
  assert.doesNotMatch(handoff, /Structured target:/);
  await page.locator('#copy-handoff').click();
  assert.match(await page.evaluate(() => navigator.clipboard.readText()), new RegExp(cid));
  await page.keyboard.press('Escape');
  await fixture("from pathlib import Path\nfrom ripple.core import Ripple\nimport sys\nRipple(Path.cwd()).inspect(sys.argv[1], 'application', actor='browser test fixture')", cid);
  await page.waitForFunction(() => document.querySelector('#next-step').textContent.includes('workspaces have assessed'));
  await page.locator('.new-button').click();
  await visible('#new-dialog');
  await page.locator('#request').fill('Add a separate customer guide later.');
  await page.locator('#request-form [data-mode=draft]').click();
  await status('Draft');
  assert.equal((await state()).changes.find(c => c.id === cid).status, 'discovering');
  await page.locator(`#history [data-change="${cid}"]`).click();
  await fixture(helper + 'f.rename()', cid);
  await status('Ready to check');
  assert.match(await page.locator('#impact-list').textContent(), /UNAFFECTED/);
  assert.equal(await page.locator('.agent-node.unaffected').count(), 1);
  await page.locator('#next-step [data-action=check]').click();
  await status('Your review needed');
  assert.match(await page.locator('#checks-panel').textContent(), /agent-declared acceptance/);
  await screenshot('03-impact-assessment-test-fixture');
  if (process.env.RIPPLE_CI_PREVIEW === '1') {
    console.log('RIPPLE_PREVIEW_BASE64=' + (await page.screenshot({type: 'jpeg', quality: 35, fullPage: true})).toString('base64'));
  }
  await page.locator('#next-step [data-action=files]').click();
  assert.equal(await page.locator('.file-diff').count(), 2);
  await page.locator('.file-diff').first().locator('summary').click();
  await visible('.file-diff[open] .diff-grid');
  await screenshot('04-file-review-test-fixture');
  await page.locator('[data-tab=overview]').click();
  await page.locator('#next-step [data-action=approve]').click();
  await status('Approved');
  await page.locator('#next-step [data-action=handoff]').click();
  await visible('#handoff-dialog');
  assert.doesNotMatch(await page.locator('#handoff-message').inputValue(), /@ripple-report/);
  await page.keyboard.press('Escape');
  await fixture("import sys\nfrom pathlib import Path\nfrom ripple.core import Ripple\na=Ripple(Path.cwd())\na.apply(sys.argv[1],'application',actor='browser test fixture')\na.apply(sys.argv[1],'documentation',actor='browser test fixture')", cid);
  await status('Verified');
  assert.match(await page.locator('#next-step').textContent(), /2 affected workspaces/);
  await page.locator('[data-tab=systems]').click();
  assert.match(await page.locator('#documents').textContent(), /Relay/);
  assert.match(await page.locator('#workspace-files').textContent(), /Relay/);
  await page.locator('[data-tab=overview]').click();
  await page.setViewportSize({width: 390, height: 844});
  await screenshot('05-mobile-test-fixture');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile page overflows horizontally');
  await page.setViewportSize({width: 1440, height: 1000});

  // A second kind of request only involves documentation and adds a file.
  await page.locator('.new-button').click();
  await visible('#new-dialog');
  await page.locator('[data-example=guide]').click();
  await page.locator('#request-form [data-mode=create]').click();
  await status('Awaiting agents');
  const guideId = (await state()).changes.at(-1).id;
  await fixture(helper + "f.assess(('documentation',))\noriginal='1. Create a project and give it a name.'\np=f.patch('documentation', {'getting-started.md':(original,'1. Create a project and choose a descriptive name. See [Project names](guides/naming.md).')},new={'guides/naming.md':'# Project names\\nUse a descriptive project name.\\n'})\nf.app.propose(f.cid,'documentation',p,'Browser test fixture: add and link a guide')", guideId);
  await status('Ready to check');
  await page.locator('#next-step [data-action=check]').click();
  await status('Your review needed');
  await page.locator('#next-step [data-action=approve]').click();
  await status('Approved');
  await fixture("import sys\nfrom pathlib import Path\nfrom ripple.core import Ripple\nRipple(Path.cwd()).apply(sys.argv[1],'documentation',actor='browser test fixture')", guideId);
  await status('Verified');
  assert.match(await page.locator('#next-step').textContent(), /1 affected workspace/);
  assert.deepEqual((await state()).changes.at(-1).required_areas, ['documentation']);

  // The legacy plan-limit path still has its independent behavior checks.
  await fixture("import sys\nfrom pathlib import Path\nsys.path.insert(0,'tests')\nfrom test_workflow import WorkflowTests\nfrom ripple.core import Ripple\nf=WorkflowTests(); f.root=Path.cwd(); f.app=Ripple(f.root); f.cid=f.app.start('Increase Basic to 10. Keep Pro unchanged.',limit=10)['id']\nfor area,p in f.patches().items(): f.app.propose(f.cid,area,p,'Browser test fixture: legacy compatibility')");
  const legacyId = (await state()).changes.at(-1).id;
  await page.waitForFunction(id => !!document.querySelector(`[data-change="${id}"]`), legacyId);
  await page.locator(`#history [data-change="${legacyId}"]`).click();
  assert.match(await page.locator('#change-title').textContent(), /Basic file limit: 5 to 10/);
  await page.locator('#next-step [data-action=check]').click();
  await status('Your review needed');
  await page.locator('#next-step [data-action=approve]').click();
  await status('Approved');
  await fixture("import sys\nfrom pathlib import Path\nfrom ripple.core import Ripple,AREAS\na=Ripple(Path.cwd())\nfor area in AREAS: a.apply(sys.argv[1],area,actor='browser test fixture')", legacyId);
  await status('Verified');
  await page.locator('[data-tab=systems]').click();
  await page.locator('#test-ten').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('accepted'));
  await page.locator('#test-eleven').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('rejected'));
  assert.match(await page.locator('#forecast').textContent(), /7.81/);
  assert.deepEqual(errors, [], 'Browser JavaScript errors');
  await writeFile(`${output}/result.json`, JSON.stringify({passed: true, screenshots: 5, note: 'Browser-tested free text, drafts, two-area rename, one-area new guide, and legacy behavior. Proposals are deterministic test fixtures; no live Switch execution is claimed.'}, null, 2));
  console.log('Browser checks passed: free-text requests, drafts/resume, impact routing, selective approval/application, new files, legacy compatibility, and mobile layout.');
} catch (error) {
  await screenshot('failure');
  if (process.env.RIPPLE_CI_PREVIEW === '1') console.log('RIPPLE_FAILURE_PREVIEW_BASE64=' + (await page.screenshot({type: 'jpeg', quality: 35, fullPage: true})).toString('base64'));
  throw error;
} finally {
  await writeFile(`${output}/server.log`, logs);
  await browser.close();
  server.kill('SIGTERM');
}
