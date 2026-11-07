// Browser fixtures below are deterministic tests, not Switch or model runs.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { cp, mkdir, mkdtemp, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';

const source = dirname(dirname(fileURLToPath(import.meta.url)));
const output = join(source, 'artifacts/browser');
await mkdir(output, {recursive: true});
const scratch = await mkdtemp(join(tmpdir(), 'ripple-browser-'));
const root = await realpath(scratch);
let server, browser, page, logs = '';
const errors = [];
const env = {...process.env, PYTHONPATH: source, RIPPLE_TEST_SOURCE: source};
const port = await new Promise((resolve, reject) => {
  const probe = createServer();
  probe.once('error', reject);
  probe.listen(0, '127.0.0.1', () => {
    const selected = probe.address().port;
    probe.close(error => error ? reject(error) : resolve(selected));
  });
});
const baseURL = `http://127.0.0.1:${port}`;
const state = async () => (await fetch(baseURL + '/api/state')).json();
const visible = async selector => page.locator(selector).waitFor({state: 'visible'});
const screenshot = async name => page.screenshot({path: `${output}/${name}.png`, fullPage: true});
async function fixture(code, ...args) {
  const result = spawnSync('python3', ['-c', code, ...args], {encoding: 'utf8', cwd: root, env});
  assert.equal(result.status, 0, result.stderr || result.stdout);
}
const status = async text => page.waitForFunction(value => document.querySelector('#change-status').textContent === value, text);
const helper = "import sys\nfrom pathlib import Path\nimport os\nsys.path.insert(0,os.environ['RIPPLE_TEST_SOURCE']+'/tests')\nfrom test_general import GeneralTests\nfrom ripple.core import Ripple\nf=GeneralTests(); f.root=Path.cwd(); f.app=Ripple(f.root); f.cid=sys.argv[1]\n";

try {
  // Every run starts with the supplied config and isolated working files.
  await cp(join(source, 'workspaces'), join(root, 'workspaces'), {recursive: true});
  await cp(join(source, 'ripple.json'), join(root, 'ripple.json'));
  server = spawn('python3', [join(source, 'ripple.py'), '--root', root, 'serve', '--port', String(port)], {cwd: root, env, stdio: ['ignore', 'pipe', 'pipe']});
  server.stdout.on('data', data => {logs += data;});
  server.stderr.on('data', data => {logs += data;});
  server.on('error', error => {logs += error.message;});
  browser = await chromium.launch({headless: true});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, permissions: ['clipboard-read', 'clipboard-write']});
  page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  for (let i = 0; i < 50; i++) {
    try {if ((await fetch(baseURL + '/api/state')).ok) break;} catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.equal((await state()).workspace_root, root, 'Must use the isolated test project');
  await page.goto(baseURL + '/');
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
  assert.equal(await page.locator('.workspace-node.unaffected').count(), 1);
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
  await visible('.file-diff[open] .unified-diff');
  assert.ok(await page.locator('.file-diff[open] .diff-line.added').count());
  assert.ok(await page.locator('.file-diff[open] .diff-line.removed').count());
  await page.locator('.file-diff[open] .full-file-contents > summary').click();
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
  await page.locator('#mobile-history-toggle').click();
  await visible('#history');
  await page.locator(`#history [data-change="${originalId}"]`).click();
  await status('Draft');
  await page.locator('#mobile-history-toggle').click();
  await page.locator(`#history [data-change="${cid}"]`).click();
  await status('Verified');
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
  await fixture("import sys\nfrom pathlib import Path\nimport os\nsys.path.insert(0,os.environ['RIPPLE_TEST_SOURCE']+'/tests')\nfrom test_workflow import WorkflowTests\nfrom ripple.core import Ripple\nf=WorkflowTests(); f.root=Path.cwd(); f.app=Ripple(f.root); f.cid=f.app.start('Increase Basic to 10. Keep Pro unchanged.',limit=10)['id']\nfor area,p in f.patches().items(): f.app.propose(f.cid,area,p,'Browser test fixture: legacy compatibility')");
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
  const files = count => Array.from({length: count}, (_, i) => ({name: `file-${i}.txt`, mimeType: 'text/plain', buffer: Buffer.from('Browser fixture')}));
  await page.locator('#test-files').setInputFiles(files(10));
  await page.locator('#validate-form button[type=submit]').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('accepted'));
  await page.locator('#test-files').setInputFiles(files(11));
  await page.locator('#validate-form button[type=submit]').click();
  await page.waitForFunction(() => document.querySelector('#validation-result').classList.contains('rejected'));
  assert.match(await page.locator('#forecast').textContent(), /7.81/);
  // A company configuration has independent agent and workspace counts.
  await new Promise(resolve => {server.once('exit', resolve); server.kill('SIGTERM');});
  await rm(join(root, '.ripple'), {recursive: true, force: true});
  await fixture("import json\nfrom pathlib import Path\nareas=['billing','security','research','handbook','support']\nworkspaces={}\nfor area in areas:\n p=Path('company')/area; p.mkdir(parents=True,exist_ok=True); (p/'notes.md').write_text('Original policy.\\n'); workspaces[area]={'path':str(p),'title':area.title()}\nagents={'delivery-lead':{'workspaces':[]}}\nfor i in range(6): agents['worker-'+str(i)]={'workspaces':[areas[i%5],areas[(i+1)%5]]}\nPath('ripple.json').write_text(json.dumps({'name':'Acme','workspaces':workspaces,'agents':agents,'coordinator':'delivery-lead'}))");
  server = spawn('python3', [join(source, 'ripple.py'), '--root', root, 'serve', '--port', String(port)], {cwd: root, env, stdio: ['ignore', 'pipe', 'pipe']});
  server.stdout.on('data', data => {logs += data;});
  server.stderr.on('data', data => {logs += data;});
  for (let i = 0; i < 50; i++) {
    try {if ((await state()).name === 'Acme') break;} catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await page.goto(baseURL + '/');
  await visible('#empty-state');
  assert.equal(await page.locator('#project-name').textContent(), 'Acme');
  await page.getByRole('button', {name: 'Create a change'}).click();
  assert.equal(await page.locator('.request-examples').isVisible(), false);
  await page.locator('#request').fill('Revise billing and handbook policies. Preserve the other workspaces.');
  await page.locator('#request-form [data-mode=create]').click();
  await status('Awaiting agents');
  const companyId = (await state()).changes.at(-1).id;
  await fixture("import sys\nfrom pathlib import Path\nfrom ripple.core import Ripple\na=Ripple(Path.cwd()); cid=sys.argv[1]\nfor area in a.areas:\n inspection=a.inspect(cid,area,actor='company browser fixture'); affected=area in ('billing','handbook'); a.assess(cid,area,'affected' if affected else 'unaffected','Inspected policy scope',actor='company browser fixture')\n if affected:\n  old=inspection['files'][area+'/notes.md']; a.propose(cid,area,{'files':[{'path':'notes.md','before_sha256':old['sha256'],'content':'Revised policy.\\n'}],'checks':[{'path':'notes.md','kind':'contains','value':'Revised policy.'}]},'Revise policy',actor='company browser fixture')", companyId);
  await status('Ready to check');
  assert.equal(await page.locator('.workspace-node').count(), 5);
  assert.equal(await page.locator('.impact-row').count(), 5);
  assert.equal(await page.locator('#file-filter option').count(), 6);
  assert.match(await page.locator('#route-map').textContent(), /worker-5/);
  await page.locator('#next-step [data-action=check]').click();
  await status('Your review needed');
  await screenshot('06-company-five-workspaces');
  await page.locator('#next-step [data-action=approve]').click();
  await status('Approved');
  await fixture("import sys\nfrom pathlib import Path\nfrom ripple.core import Ripple\na=Ripple(Path.cwd())\nfor area in ('billing','handbook'): a.apply(sys.argv[1],area,actor='company browser fixture')", companyId);
  await status('Verified');
  await page.locator('[data-tab=systems]').click();
  assert.equal(await page.locator('#example-systems').isVisible(), false);
  assert.match(await page.locator('#workspace-files').textContent(), /billing\/notes.md/);
  assert.match(await page.locator('#workspace-files').textContent(), /Revised policy/);
  await page.setViewportSize({width: 390, height: 844});
  await screenshot('07-company-mobile');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Company layout overflows horizontally');
  assert.deepEqual(errors, [], 'Browser JavaScript errors');
  await writeFile(`${output}/result.json`, JSON.stringify({passed: true, screenshots: 7, note: 'Browser-tested free text, drafts, two-area rename, one-area new guide, legacy behavior, and a five-workspace company with seven agents. Proposals are deterministic test fixtures; no live Switch execution is claimed.'}, null, 2));
  console.log('Browser checks passed: free-text requests, drafts/resume, impact routing, selective approval/application, new files, legacy compatibility, and mobile layout.');
} catch (error) {
  if (page) await screenshot('failure');
  if (page && process.env.RIPPLE_CI_PREVIEW === '1') console.log('RIPPLE_FAILURE_PREVIEW_BASE64=' + (await page.screenshot({type: 'jpeg', quality: 35, fullPage: true})).toString('base64'));
  throw error;
} finally {
  await writeFile(`${output}/server.log`, logs);
  if (browser) await browser.close();
  if (server && server.exitCode === null) {
    await new Promise(resolve => {server.once('exit', resolve); server.kill('SIGTERM');});
  }
  await rm(root, {recursive: true, force: true});
}
