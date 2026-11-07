'use strict';

const $ = selector => document.querySelector(selector);
const token = $('meta[name="ripple-token"]').content;
const areas = ['application', 'documentation', 'reporting'];
const names = {application: 'Application', documentation: 'Documentation', reporting: 'Reporting'};
const actors = {application: 'ripple-app', documentation: 'ripple-docs', reporting: 'ripple-report'};
const labels = {draft: 'Draft', discovering: 'Awaiting agents', ready_to_check: 'Ready to check', awaiting_approval: 'Your review needed', needs_revision: 'Revision needed', approved: 'Approved', applying: 'Applying edits', verifying: 'Verifying result', complete: 'Verified', verification_failed: 'Verification failed', cancelled: 'Cancelled'};
const initialRoute = new URLSearchParams(location.hash.slice(1));
let state, current, selectedId = initialRoute.get('change'), tab = initialRoute.get('tab') || 'overview', refreshing = false, busy = false, toastTimer;

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const titleCase = value => value.charAt(0).toUpperCase() + value.slice(1);
const time = value => new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
const safeURL = value => {try {const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) ? u.href : null;} catch {return null;}};
const connection = () => state?.switch || {configured: false, connected: false, message: 'Connect a Switch room to dispatch this change.'};
const phase = () => current?.approval ? 'approval' : 'request';
const receipt = () => current?.dispatches?.[phase()];
const events = () => state?.events.filter(e => e.change === current?.id) || [];

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Ripple-Token': token}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {$('#toast').hidden = true;}, 4200);
}
function error(message, target = '#error') {
  const node = $(target);
  node.textContent = message instanceof Error ? message.message : String(message);
  node.hidden = false;
}
function showDialog(id) {const dialog = $('#' + id); if (!dialog.open) dialog.showModal();}
function setTab(value) {
  tab = value;
  document.querySelectorAll('.tab-panel').forEach(e => {e.hidden = e.id !== `panel-${value}`;});
  document.querySelectorAll('[data-tab]').forEach(e => {
    e.classList.toggle('active', e.dataset.tab === value);
    e.setAttribute('aria-selected', String(e.dataset.tab === value));
  });
  if (current) history.replaceState(null, '', '#change=' + encodeURIComponent(current.id) + '&tab=' + encodeURIComponent(value));
  $('#breadcrumb-current').textContent = {overview: 'Overview', files: 'File changes', systems: 'Workspaces', activity: 'Activity'}[value];
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const next = await api('/api/state');
    const changed = JSON.stringify(next) !== JSON.stringify(state);
    state = next;
    current = state.changes.find(c => c.id === selectedId) || [...state.changes].reverse().find(c => c.status !== 'cancelled') || null;
    if (current) selectedId = current.id;
    $('#restart-notice').hidden = state.api_version === 3;
    $('#local-server-state').textContent = 'Local workspace server available';
    if (changed) render();
  } catch (exc) {
    $('#local-server-state').textContent = 'Local server unavailable';
    error(exc);
  } finally {refreshing = false;}
}
function render() {
  renderHistory(); renderConnection(); renderChange(); renderSystems(); renderActivity();
  setTab(['overview', 'files', 'systems', 'activity'].includes(tab) ? tab : 'overview');
}
function renderHistory() {
  const query = $('#history-search').value.toLowerCase();
  const changes = [...state.changes].reverse().filter(c => `${c.id} ${c.request} ${c.target.plan}`.toLowerCase().includes(query));
  $('#history-count').textContent = String(state.changes.length).padStart(2, '0');
  $('#history').innerHTML = changes.length ? changes.map(c => `<button class="history-item ${c.id === current?.id ? 'selected' : ''}" data-change="${esc(c.id)}"><span class="status-dot ${c.status === 'complete' ? 'green' : ['cancelled', 'draft'].includes(c.status) ? '' : 'orange'}"></span><span><strong>${esc(titleCase(c.target.plan))}: ${c.before} → ${c.target.limit} files</strong><small>${esc(c.id)} / ${esc(labels[c.status])}</small></span></button>`).join('') : '<p class="history-empty">No changes here yet.<br>Create a change to begin.</p>';
}
function renderConnection() {
  const c = connection();
  const label = c.connected ? 'Switch verified' : c.configured ? 'Switch needs attention' : 'Switch / manual handoff';
  $('#switch-badge').innerHTML = `<span class="status-dot ${c.connected ? 'green' : ''}"></span>${esc(label)} <span>↗</span>`;
  $('#rail-switch-state').textContent = c.connected ? 'Room access verified' : c.configured ? 'Saved / not verified' : 'Manual handoff available';
  $('#rail-switch-dot').className = 'status-dot ' + (c.connected ? 'green' : '');
  const room = safeURL(c.room_url);
  $('#open-room').hidden = !room;
  if (room) $('#open-room').href = room;
  $('#switch-current-state').innerHTML = `<strong>${esc(c.connected ? 'Connection verified' : c.configured ? 'Connection saved' : 'No room connected yet')}</strong><div>${esc(c.message)}</div>${(c.checks || []).map(item => `<div class="connection-check ${item.passed ? '' : 'failed'}">${item.passed ? '✓' : '×'} ${esc(item.name)}</div>`).join('')}${c.tested_at ? `<div class="small-note">Last tested ${esc(time(c.tested_at))}</div>` : ''}`;
  $('#test-connection').disabled = !c.configured || busy;
  $('#switch-key').placeholder = c.configured ? 'Leave blank to keep the saved key' : 'Stored only on this computer';
}
function renderChange() {
  const c = current;
  $('#empty-state').hidden = !!c;
  $('#change-workspace').hidden = !c;
  if (!c) return;
  $('#change-id').textContent = c.id;
  $('#change-title').textContent = `${titleCase(c.target.plan)} file limit: ${c.before} to ${c.target.limit}`;
  $('#request-origin').textContent = c.origin === 'mattermost' ? 'From Mattermost' : 'Created in Ripple';
  $('#change-created').textContent = `Created ${time(c.created)}`;
  $('#change-status').textContent = labels[c.status] || c.status;
  $('#change-status').className = 'status-label ' + c.status;
  $('#change-request').textContent = c.request;
  $('#before-value').textContent = c.before;
  $('#after-value').textContent = c.target.limit;
  $('#decision-label').textContent = `${titleCase(c.target.plan)} / files per project`;
  const files = Object.values(c.proposals).reduce((sum, p) => sum + p.files.length, 0);
  $('#scope-stats').innerHTML = `<div class="stat"><span>Workspaces inspected</span><strong>${Object.keys(c.inspections).length} / 3</strong></div><div class="stat"><span>File updates proposed</span><strong>${files}</strong></div><div class="stat"><span>Workspaces applied</span><strong>${Object.keys(c.applied).length} / 3</strong></div>`;
  $('#tab-file-count').textContent = files;
  $('#tab-event-count').textContent = events().length;
  renderMap(); renderNextStep(); renderImpact(); renderChecks(); renderFiles();
}
function renderMap() {
  const c = current, sw = connection(), sent = c.dispatches?.request?.status === 'sent';
  const activity = Object.keys(c.inspections).length > 0;
  const switchLabel = sent ? 'Request accepted' : sw.connected ? 'Room verified' : sw.configured ? 'Connection unavailable' : 'Manual handoff';
  $('#route-map').innerHTML = `<svg class="route-wires" viewBox="0 0 1000 300" preserveAspectRatio="none" aria-hidden="true"><path class="${sent ? 'dispatched' : ''}" d="M160 150 H440"/><path d="M440 150 H610 Q625 150 625 135 V69 Q625 54 640 54 H790"/><path d="M440 150 H790"/><path d="M440 150 H610 Q625 150 625 165 V231 Q625 246 640 246 H790"/></svg><div class="route-node decision-node"><span class="node-type">YOUR DECISION <span>↗</span></span><strong>${c.before} → ${c.target.limit} files</strong><small>${esc(titleCase(c.target.plan))} plan</small></div><button class="route-node switch-node" data-action="connect"><span class="node-type">SHARED ROOM <span>↔</span></span><strong>Switch</strong><small>${esc(switchLabel)}</small></button>${areas.map(area => {
    const proposed = c.proposals[area], inspected = c.inspections[area], applied = c.applied[area];
    const status = applied ? 'Applied to workspace' : proposed ? `${proposed.files.length} file edits proposed` : inspected ? 'Inspection received' : 'No tool activity yet';
    return `<button class="route-node agent-node area-${area} ${applied ? 'applied' : ''}" data-area="${area}"><span class="node-type">${esc(actors[area])} <span class="status-dot ${applied ? 'green' : proposed ? 'orange' : ''}"></span></span><strong>${esc(names[area])}</strong><small>${esc(status)}</small></button>`;
  }).join('')}`;
  $('#route-mode').textContent = sent ? 'Real Switch dispatch recorded' : activity ? 'Actual tool activity received' : 'No API dispatch recorded';
  $('#transport-summary').textContent = sent ? `Switch accepted the request for room ${c.dispatches.request.room_id}. Replies are in the actual room; tool results appear here.` : sw.connected ? 'The server, dispatch identity, and room were tested. Send this change to begin the agent workflow.' : activity ? 'Actual workspace tool activity has arrived. Review your real Switch room for the conversation. Direct API dispatch is not configured.' : 'Direct API dispatch is not configured. Use Manual handoff to send the request into your real Switch room.';
}
function button(text, action, style = '') {return `<button class="button compact ${style}" data-action="${action}" ${busy ? 'disabled' : ''}>${esc(text)}</button>`;}
function renderNextStep() {
  const c = current, sw = connection(), r = receipt();
  let heading, detail, buttons, style = '', icon = '↗';
  if (c.status === 'draft') {
    const active = state.changes.find(other => other.id !== c.id && !['draft', 'complete', 'cancelled'].includes(other.status));
    heading = 'Saved as a draft.';
    detail = active ? `${active.id} is active. This request stays in your ledger and can be resumed after that work finishes.` : 'Your request is preserved. Resume it when you are ready to send it to the agents.';
    buttons = active ? `<button class="button compact" data-change="${esc(active.id)}">View active request ↗</button>` : button('Resume this request ↗', 'resume', 'accent');
  } else if (c.status === 'complete') {
    heading = 'The change has reached every workspace.';
    detail = 'All three areas applied their edits. The final checks passed against actual files and application behavior.';
    buttons = button('Inspect the result ↗', 'systems', 'dark'); style = 'complete'; icon = '✓';
  } else if (c.status === 'cancelled') {
    heading = 'This change was cancelled.'; detail = 'No edits were applied. The request stays in the ledger.'; buttons = button('New change ↗', 'new');
  } else if (c.status === 'awaiting_approval') {
    heading = 'Your review is the next step.'; detail = 'Read the actual file changes. Approval covers this exact checked bundle.';
    buttons = button('Review files', 'files') + button('Approve changes ↗', 'approve', 'accent');
  } else if (['ready_to_check', 'needs_revision', 'verification_failed'].includes(c.status)) {
    heading = c.status === 'ready_to_check' ? 'The proposals are ready to check together.' : 'An inconsistency needs attention.';
    detail = c.status === 'ready_to_check' ? 'Run the application, documentation, and workbook checks before approving.' : 'Read the failed checks below. Ask the responsible agent to revise its proposal in the room.';
    buttons = button('Run combined checks ↗', 'check', 'accent');
  } else if (r?.status === 'sent') {
    const count = Object.keys(c.inspections).length;
    heading = phase() === 'approval' ? 'Approval sent. Waiting for application.' : count ? `${count} of 3 workspaces have reported an inspection.` : 'Switch accepted your request. Waiting for agents.';
    detail = phase() === 'approval' ? `${Object.keys(c.applied).length} of 3 workspaces applied. Each agent will post its result in the room.` : 'The next update comes from a real agent tool call. If nothing arrives, check that the three sessions are running in Console.';
    buttons = button('Connection details ↗', 'connect'); style = 'waiting'; icon = '↳';
  } else if (!sw.configured && c.approval) {
    heading = 'Approved. Send the decision to your Switch room.';
    detail = 'Open the manual handoff, copy the approval message, and paste it into the same real chat. Each agent will apply its own reviewed changes.';
    buttons = button('Open approval message ↗', 'handoff', 'accent');
  } else if (Object.keys(c.inspections).length && !sw.configured) {
    heading = `${Object.keys(c.inspections).length} of 3 workspaces have reported an inspection.`;
    detail = 'Actual agent tool activity has arrived. Follow the conversation in your Switch room while the remaining proposals are prepared.';
    buttons = button('View proposed files ↗', 'files'); style = 'waiting'; icon = '↳';
  } else if (sw.configured) {
    heading = phase() === 'approval' ? 'Send your approval to the working agents.' : 'Ready to send this change to Switch.';
    detail = r?.status === 'failed' ? r.message : 'This sends a real message to the configured room. Your three working agent sessions must be running.';
    buttons = button(busy ? 'Sending…' : phase() === 'approval' ? 'Send approval ↗' : 'Send to Switch ↗', 'dispatch', 'accent');
  } else {
    heading = 'Your change is saved. Send it to your Switch room.';
    detail = 'Manual handoff copies the exact request for your existing Switch room. Configure direct dispatch if you prefer sending from this page.';
    buttons = button('Manual handoff', 'handoff') + button('Connect Switch ↗', 'connect', 'accent');
  }
  const cancel = !Object.keys(c.applied).length && !['complete', 'cancelled'].includes(c.status) ? '<button class="text-button" data-action="cancel">Cancel</button>' : '';
  $('#next-step').className = 'next-step ' + style;
  $('#next-step').innerHTML = `<span class="step-icon">${icon}</span><div class="step-copy"><h2>${esc(heading)}</h2><p>${esc(detail)}</p></div><div class="step-buttons">${buttons}${cancel}</div>`;
}
function renderImpact() {
  const c = current;
  $('#impact-summary').textContent = `${Object.keys(c.proposals).length} of 3 areas proposed edits`;
  $('#impact-list').innerHTML = areas.map((area, i) => {
    const p = c.proposals[area], inspection = c.inspections[area], applied = c.applied[area];
    const summary = p?.summary || (inspection ? 'Inspection received. Waiting for proposed edits.' : 'No inspection received. The agent will check this workspace after the request reaches the room.');
    return `<article class="impact-row"><span class="impact-number">0${i + 1}</span><button class="impact-name" data-area="${area}"><strong>${esc(names[area])} ↗</strong><small>${esc(actors[area])}</small></button><div><p class="impact-detail">${esc(summary)}</p>${p?.findings.length ? `<ul class="impact-findings">${p.findings.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}</div><span class="impact-state ${applied ? 'applied' : ''}">${applied ? 'APPLIED' : p ? 'PROPOSED' : inspection ? 'INSPECTED' : 'AWAITING'}</span></article>`;
  }).join('');
}
function renderChecks() {
  const check = current.check;
  $('#checks-panel').hidden = !check;
  if (!check) return;
  $('#checks-panel').innerHTML = `<div class="panel-heading"><span class="section-index">03 / ${check.mode === 'actual' ? 'VERIFIED RESULT' : 'PROPOSED BUNDLE CHECK'}</span><span class="small-note">${check.passed ? 'All checks passed' : 'Revision needed'}</span></div>${check.checks.map(item => `<div class="check-row ${item.passed ? '' : 'failed'}"><span>${item.passed ? '✓' : '×'}</span><div><strong>${esc(item.name)}</strong><p>${esc(item.detail)}</p></div></div>`).join('')}`;
}
function renderFiles() {
  if (!current) return;
  const filter = $('#file-filter').value;
  const files = Object.entries(current.proposals).flatMap(([area, p]) => p.files.map(f => ({...f, area}))).filter(f => filter === 'all' || f.area === filter);
  const opened = new Set([...$('#file-list').querySelectorAll('details[open]')].map(e => e.dataset.path));
  $('#file-list').innerHTML = files.length ? files.map(f => {
    const path = f.area + '/' + f.path;
    return `<details class="file-diff" data-path="${esc(path)}" ${opened.has(path) ? 'open' : ''}><summary>${esc(path)}<span>${current.applied[f.area] ? 'APPLIED' : 'PROPOSED'}</span></summary><div class="diff-grid"><div><label>BEFORE</label><pre>${esc(f.before)}</pre></div><div><label>AFTER</label><pre>${esc(f.content)}</pre></div></div></details>`;
  }).join('') : '<div class="file-empty">No proposed file edits yet.<br>Agent proposals will appear here after they inspect their workspaces.</div>';
}
function renderSystems() {
  const systems = state.systems;
  $('#plan-values').innerHTML = Object.entries(systems.application).map(([plan, value]) => `<div class="plan-value"><span>${esc(plan.toUpperCase())}</span><strong>${value.files_per_project}</strong><small>files per project</small></div>`).join('');
  $('#forecast').innerHTML = `<div class="table-wrap"><table><thead><tr><th>PLAN</th><th>ACCOUNTS</th><th>FILE LIMIT</th><th>CAPACITY GiB</th></tr></thead><tbody>${systems.reporting.map(row => `<tr><td>${esc(titleCase(row.plan))}</td><td>${esc(row.accounts)}</td><td>${esc(row.files_per_project)}</td><td><strong>${esc(row.capacity_gib)}</strong></td></tr>`).join('')}</tbody></table></div>`;
  $('#documents').innerHTML = Object.entries(systems.documentation).map(([path, content]) => `<article class="document ${path.startsWith('archive/') ? 'historical' : ''}"><span>${esc(path)}${path.startsWith('archive/') ? ' / HISTORICAL FACTS' : ''}</span><pre>${esc(content)}</pre></article>`).join('');
}
function renderActivity() {
  const log = [...events()].reverse();
  $('#feed-state').textContent = log.length ? `${log.length} entries` : 'Waiting';
  $('#live-feed').innerHTML = log.slice(0, 5).map(e => `<article class="feed-item ${e.kind.startsWith('switch_') ? 'transport' : ''}"><strong>${esc(e.actor)}</strong><p>${esc(e.message)}</p><time>${esc(time(e.time))}</time></article>`).join('') || '<p class="feed-empty">Real tool and transport activity will appear here as it happens.</p>';
  $('#activity-log').innerHTML = log.map(e => `<article class="activity-entry"><time>${esc(time(e.time))}</time><div><strong>${esc(e.actor)}</strong><span class="event-kind">${esc(e.kind)}</span><p>${esc(e.message)}</p>${e.room_id ? `<div class="event-transport-detail">ROOM ${esc(e.room_id)}${e.message_id ? `<br>MESSAGE ${esc(e.message_id)}` : ''}</div>` : ''}${safeURL(e.room_url) ? `<a class="text-button" href="${esc(safeURL(e.room_url))}" target="_blank" rel="noreferrer">Open reported room ↗</a>` : ''}</div></article>`).join('') || '<p class="feed-empty">No recorded activity for this change.</p>';
}
async function newChange() {
  if (busy) return;
  if (state.api_version !== 3) {
    error('Restart the Ripple server once to enable saved drafts, then refresh this page.');
    return;
  }
  busy = true;
  let saved = false;
  try {
    if (current?.can_save_as_draft) {
      await api(`/api/changes/${current.id}/draft`, {});
      saved = true;
      await refresh();
    }
    const plan = $('#plan').value, before = state.systems.application[plan].files_per_project;
    const next = before < 100 ? Math.min(100, before + 5) : 95;
    $('#limit').value = next;
    $('#request').value = `Change the ${titleCase(plan)} plan's file limit from ${before} to ${next}. Update the application, current help documentation, and storage forecast. Keep the other plan unchanged.`;
    $('#request').dataset.generated = $('#request').value;
    $('#new-error').hidden = true;
    showDialog('new-dialog');
    if (saved) toast('Previous request saved as a draft. Create your new request.');
  } catch (exc) {error(exc);}
  finally {busy = false; if (current) renderNextStep();}
}

function connect() {
  const c = connection();
  $('#switch-server').value = c.server || '';
  $('#switch-room').value = c.room_id || '';
  $('#switch-room-url').value = c.room_url || '';
  $('#switch-agent').value = c.agent_id || '';
  $('#switch-key').value = '';
  $('#switch-error').hidden = true; renderConnection(); showDialog('switch-dialog');
}
function manualPrompt() {
  const script = "'" + (state.workspace_root + '/ripple.py').replace(/'/g, "'\\''") + "'";
  const c = current;
  if (!c) return '';
  if (phase() === 'approval') return `@ripple-app @ripple-docs @ripple-report The local reviewer approved ${c.id} in Ripple. Each of you run python3 ${script} apply ${c.id} YOUR_AREA --actor YOUR_AGENT_NAME, using your assigned area. Report the real result here. The last agent triggers actual verification.`;
  return `@ripple-app @ripple-docs @ripple-report Change ${c.id}: ${c.request}\nStructured target: ${c.target.plan} = ${c.target.limit} files per project. Read your role under agents/ and agents/WORKFLOW.md. Inspect actual files and submit your own area's proposal with the Ripple CLI. Preserve unaffected plans and historical facts. Do not edit live files directly. Once all proposals exist, @ripple-app run python3 ${script} check ${c.id}. Wait for human review before applying.`;
}
function handoff() {
  if (!current) return toast('Create a change first.');
  if (current.status === 'draft') return toast('Resume this draft before sending it to the agents.');
  $('#handoff-message').value = manualPrompt();
  $('#handoff-feedback').textContent = 'Copy this message, then paste it into your actual Switch room.';
  showDialog('handoff-dialog');
}
async function runAction(action) {
  if (busy || !current) return;
  busy = true; $('#error').hidden = true; renderNextStep();
  try {
    if (action === 'dispatch') {
      const result = await api(`/api/changes/${current.id}/dispatch`, {phase: phase()});
      if (result.status !== 'sent') throw new Error(result.message);
      toast('Switch accepted the message. Waiting for actual agent activity.');
    } else {
      await api(`/api/changes/${current.id}/${action}`, {});
      if (action === 'approve') toast('Approved. Send the approval to your Switch room.');
      if (action === 'cancel') toast('Cancelled before application. The record is preserved.');
      if (action === 'check') toast('Combined check finished. Review the actual results.');
      if (action === 'resume') toast('Draft resumed. Send it to Switch when ready.');
    }
    await refresh();
  } catch (exc) {error(exc); await refresh();}
  finally {busy = false; renderNextStep();}
}
document.addEventListener('click', event => {
  const close = event.target.closest('[data-close]');
  if (close) return $('#' + close.dataset.close).close();
  const history = event.target.closest('[data-change]');
  if (history) {selectedId = history.dataset.change; current = state.changes.find(c => c.id === selectedId); render(); setTab('overview'); return;}
  const area = event.target.closest('[data-area]');
  if (area) {$('#file-filter').value = area.dataset.area; renderFiles(); setTab('files'); return;}
  const tabButton = event.target.closest('[data-tab]');
  if (tabButton) return setTab(tabButton.dataset.tab);
  const control = event.target.closest('[data-action]');
  if (!control || !state) return;
  const action = control.dataset.action;
  if (action === 'new') return newChange();
  if (action === 'connect') return connect();
  if (action === 'handoff') return handoff();
  if (['files', 'systems', 'activity'].includes(action)) return setTab(action);
  runAction(action);
});
$('#refresh').addEventListener('click', refresh);
$('#history-search').addEventListener('input', renderHistory);
$('#file-filter').addEventListener('change', renderFiles);
function syncExampleDescription() {
  const field = $('#request');
  if (field.value !== field.dataset.generated) return;
  const plan = $('#plan').value, before = state.systems.application[plan].files_per_project;
  field.value = `Change the ${titleCase(plan)} plan's file limit from ${before} to ${$('#limit').value}. Update the application, current help documentation, and storage forecast. Keep the other plan unchanged.`;
  field.dataset.generated = field.value;
}
$('#plan').addEventListener('change', syncExampleDescription);
$('#limit').addEventListener('input', syncExampleDescription);
$('#request-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = event.submitter; submit.disabled = true;
  try {
    const statedPlan = $('#request').value.match(/(?:change|increase|raise|reduce|decrease|set|update)\s+(?:the\s+)?(basic|pro)(?:['’]s)?\s+(?:plan(?:['’]s)?\s+)?(?:file|upload)/i);
    if (statedPlan && statedPlan[1].toLowerCase() !== $('#plan').value) throw new Error('The description and selected customer plan disagree. Make them match before creating the request.');
    const result = await api('/api/changes', {request: $('#request').value, plan: $('#plan').value, limit: Number($('#limit').value), draft: submit.dataset.mode === 'draft'});
    selectedId = result.id; $('#new-dialog').close(); await refresh(); setTab('overview');
    toast(result.status === 'draft' ? 'Request saved as a draft in your ledger.' : 'Change created. Use the next-step panel to send it to Switch.');
  } catch (exc) {error(exc, '#new-error');} finally {submit.disabled = false;}
});
$('#switch-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = event.submitter; submit.disabled = true; submit.textContent = 'Testing connection…'; $('#switch-error').hidden = true;
  try {
    await api('/api/switch/configure', {server: $('#switch-server').value, room_id: $('#switch-room').value, room_url: $('#switch-room-url').value, agent_id: $('#switch-agent').value, api_key: $('#switch-key').value});
    $('#switch-key').value = '';
    const result = await api('/api/switch/test', {});
    await refresh();
    if (!result.connected) error(result.message, '#switch-error');
    else toast('Switch server, dispatch identity, and room verified.');
  } catch (exc) {error(exc, '#switch-error');} finally {submit.disabled = false; submit.textContent = 'Save & test connection ↗';}
});
$('#test-connection').addEventListener('click', async event => {
  const submit = event.currentTarget; submit.disabled = true; submit.textContent = 'Testing…';
  try {const result = await api('/api/switch/test', {}); await refresh(); if (!result.connected) error(result.message, '#switch-error'); else {$('#switch-error').hidden = true; toast('Saved connection verified.');}}
  catch (exc) {error(exc, '#switch-error');} finally {submit.disabled = false; submit.textContent = 'Test saved connection';}
});
$('#copy-handoff').addEventListener('click', async () => {
  try {await navigator.clipboard.writeText($('#handoff-message').value); $('#handoff-feedback').textContent = 'Copied. Paste the message into your Switch room to notify the agents.'; toast('Message copied. Paste it into the real room.');}
  catch {$('#handoff-message').focus(); $('#handoff-message').select(); $('#handoff-feedback').textContent = 'Clipboard access was unavailable. The message is selected; press Command+C to copy it.';}
});
async function validateFiles(files) {
  try {const result = await api('/api/validate', {plan: $('#test-plan').value, files}); $('#validation-result').textContent = result.message; $('#validation-result').className = 'validation-result ' + (result.accepted ? 'accepted' : 'rejected');}
  catch (exc) {error(exc);}
}
$('#validate-form').addEventListener('submit', event => {event.preventDefault(); const files = [...$('#test-files').files]; if (!files.length) return toast('Choose files or use a sample filename check.'); validateFiles(files.map(f => f.name));});
$('#test-ten').addEventListener('click', () => validateFiles(Array.from({length: 10}, (_, i) => `sample-${i + 1}.txt`)));
$('#test-eleven').addEventListener('click', () => validateFiles(Array.from({length: 11}, (_, i) => `sample-${i + 1}.txt`)));
$('#export-receipts').addEventListener('click', () => {
  const output = {change: current, events: events(), exported_at: new Date().toISOString(), note: 'Actor labels are caller-supplied. Use the actual chat recording as evidence of human-agent interaction.'};
  const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = `${current.id}-receipts.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.addEventListener('keydown', event => {
  if (event.target.closest('input,textarea,select') || event.metaKey || event.ctrlKey || document.querySelector('dialog[open]')) return;
  if (event.key.toLowerCase() === 'n' && state) {event.preventDefault(); newChange();}
  if (current && ['1', '2', '3', '4'].includes(event.key)) setTab(['overview', 'files', 'systems', 'activity'][Number(event.key) - 1]);
});
refresh();
setInterval(refresh, 2000);
