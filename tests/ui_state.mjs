// Exercise the actual dashboard script with company state, without browser downloads.
// This covers rendering contracts. Playwright verifies browser behavior and layout.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const html = await readFile(new URL('../web/index.html', import.meta.url), 'utf8');
const script = await readFile(new URL('../web/app.js', import.meta.url), 'utf8');

function documentFromSource() {
  const nodes = [...html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/g)].map(([, tag, text]) => {
    const attrs = Object.fromEntries([...text.matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(([, key, value]) => [key, value || '']));
    const classes = new Set((attrs.class || '').split(' '));
    let markup = '';
    return {
      tag, attrs, id: attrs.id, content: attrs.content, hidden: 'hidden' in attrs,
      value: attrs.value || '', options: [], textContent: '', className: attrs.class || '',
      dataset: Object.fromEntries(Object.entries(attrs).filter(([key]) => key.startsWith('data-')).map(([key, value]) => [key.slice(5), value])),
      classList: {add: value => classes.add(value), remove: value => classes.delete(value), toggle(value, force) {if (force ?? !classes.has(value)) classes.add(value); else classes.delete(value); return classes.has(value);}},
      addEventListener() {}, setAttribute(key, value) {this.attrs[key] = value;},
      querySelectorAll() {return [];},
      set innerHTML(value) {markup = value; this.options = [...value.matchAll(/<option value="([^"]*)"/g)].map(([, option]) => ({value: option}));},
      get innerHTML() {return markup;},
    };
  });
  const find = selector => {
    if (selector.startsWith('#')) return nodes.filter(node => node.id === selector.slice(1));
    if (selector.startsWith('.')) return nodes.filter(node => node.attrs.class?.split(' ').includes(selector.slice(1)));
    if (selector === '[data-tab]') return nodes.filter(node => 'data-tab' in node.attrs);
    if (selector === 'meta[name="ripple-token"]') return nodes.filter(node => node.tag === 'meta' && node.attrs.name === 'ripple-token');
    return [];
  };
  return {querySelector: selector => find(selector)[0] || null, querySelectorAll: find, addEventListener() {}};
}

for (const [workspaceCount, agentCount] of [[1, 7], [5, 2], [12, 64]]) {
  const areas = Object.fromEntries(Array.from({length: workspaceCount}, (_, i) => [`company-${i}`, {title: `Company workspace ${i}`, path: `services/${i}`}])) ;
  const ids = Object.keys(areas);
  const agents = Object.fromEntries(Array.from({length: agentCount}, (_, i) => [`worker-${i}`, {workspaces: [ids[i % workspaceCount]], title: `Worker ${i}`}])) ;
  const files = Object.fromEntries(ids.map(area => [area + '/policy.md', '# Policy\n']));
  const change = {id: 'R-COMPANY', kind: 'general', request: 'Revise company policies.', target: {}, status: 'discovering', created: new Date().toISOString(),
    workspace_config: areas, proposals: {}, inspections: {}, assessments: {}, applied: {}, approval: null, check: null, required_areas: [], clarifications: []};
  const state = {api_version: 6, name: 'Company project', areas, agents, changes: [change], events: [], switch: {configured: false, connected: false},
    systems: {files, application: {}, documentation: {}, reporting: []}, example: null};
  const document = documentFromSource();
  const context = vm.createContext({document, URL, URLSearchParams, location: {hash: ''}, history: {replaceState() {}},
    fetch: async () => ({ok: true, json: async () => state}), setInterval() {}, setTimeout() {}, clearTimeout() {}});
  vm.runInContext(script, context, {filename: 'web/app.js'});
  await new Promise(resolve => setImmediate(resolve));
  const element = selector => document.querySelector(selector);
  assert.equal(element('#error').hidden, true, element('#error').textContent);
  assert.equal(element('#project-name').textContent, 'Company project');
  assert.equal((element('#route-map').innerHTML.match(/data-area=/g) || []).length, workspaceCount);
  assert.equal(element('#file-filter').options.length, workspaceCount + 1);
  assert.equal((element('#impact-list').innerHTML.match(/class="impact-row/g) || []).length, workspaceCount);
  assert.equal(element('#example-systems').hidden, true);
  assert.equal(element('.request-examples').hidden, true);
  assert.match(element('#route-map').innerHTML, new RegExp(`worker-${agentCount - 1}`));
  for (const area of ids) assert.ok(element('#workspace-files').innerHTML.includes(area + '/policy.md'));
}
console.log('Dashboard render checks passed for 1, 5, and 12 workspaces with independent agent rosters.');
