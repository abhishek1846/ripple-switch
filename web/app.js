'use strict';

const $ = selector => document.querySelector(selector);
const token = $('meta[name="ripple-token"]').content;
let areas = [], names = {};
const agentNames = area => Object.entries(state?.agents || {}).filter(([, agent]) => agent.workspaces.includes(area)).map(([id]) => id);
const agentLabel = area => agentNames(area).map(id => state.agents[id].title && state.agents[id].title !== id ? `${state.agents[id].title} (${id})` : id).join(', ') || 'CLI participants';
const labels = {needs_clarification: 'Question for you', no_changes: 'No changes needed', draft: 'Draft', discovering: 'Awaiting agents', ready_to_check: 'Ready to check', awaiting_approval: 'Your review needed', needs_revision: 'Revision needed', approved: 'Approved', applying: 'Applying edits', verifying: 'Verifying result', complete: 'Verified', verification_failed: 'Verification failed', cancelled: 'Cancelled'};
const initialRoute = new URLSearchParams(location.hash.slice(1));
let state, current, selectedId = initialRoute.get('change'), tab = initialRoute.get('tab') || 'overview', refreshing = false, busy = false, toastTimer;

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const titleCase = value => value.charAt(0).toUpperCase() + value.slice(1);
const time = value => new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
const safeURL = value => {try {const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) ? u.href : null;} catch {return null;}};
const connection = () => state?.switch || {configured: false, connected: false, message: 'Connect a Switch room to dispatch this change.'};
const phase = () => current?.approval ? 'approval' : 'request';
const receipt = () => current?.dispatches?.[phase()];
const general = c => c?.kind === 'general';
const required = c => c?.required_areas || areas;
const statusLabel = c => c.status === 'complete' && c.git_delivery ? c.git_delivery.status === 'published' ? 'Git published' : 'Verified in Git' : labels[c.status] || c.status;
const closed = c => ['no_changes', 'complete', 'cancelled'].includes(c.status);
const shortRequest = c => {const line = c.request.split('\n')[0]; const first = line.match(/^.*?[.!?](?:\s|$)/)?.[0].trim() || line; return first.length > 80 ? first.slice(0, 77).trimEnd() + '...' : first;};
const changeTitle = c => general(c) ? shortRequest(c) : `${titleCase(c.target.plan)} file limit: ${c.before} to ${c.target.limit}`;
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
    const next = await api('/api/state' + (selectedId ? '?change=' + encodeURIComponent(selectedId) : ''));
    const changed = JSON.stringify(next) !== JSON.stringify(state);
    state = next;
    areas = Object.keys(state.areas);
    names = Object.fromEntries(Object.entries(state.areas).map(([area, info]) => [area, info.title]));
    current = state.changes.find(c => c.id === selectedId) || [...state.changes].reverse().find(c => c.status !== 'cancelled') || null;
    if (current) selectedId = current.id;
    $('#restart-notice').hidden = state.api_version === 6;
    $('#local-server-state').textContent = 'Local workspace server available';
    if (changed) render();
  } catch (exc) {
    $('#local-server-state').textContent = 'Local server unavailable';
    error(exc);
  } finally {refreshing = false;}
}
function render() {
  const workspaceConfig = current?.workspace_config || state.areas;
  areas = Object.keys(workspaceConfig);
  names = Object.fromEntries(Object.entries(workspaceConfig).map(([area, info]) => [area, info.title]));
  $('#project-name').textContent = state.name || 'Project';
  $('.request-examples').hidden = state.example !== 'parcel';
  $('#empty-workspace-names').innerHTML = Object.values(state.areas).map(info => esc(info.title)).join('<br>');
  renderHistory(); renderConnection(); renderChange(); renderSystems(); renderActivity();
  setTab(['overview', 'files', 'systems', 'activity'].includes(tab) ? tab : 'overview');
}
function renderHistory() {
  const query = $('#history-search').value.toLowerCase();
  const changes = [...state.changes].reverse().filter(c => `${c.id} ${c.request} ${c.target?.plan || ""}`.toLowerCase().includes(query));
  $('#history-count').textContent = String(state.changes.length).padStart(2, '0');
  $('#history').innerHTML = changes.length ? changes.map(c => `<button class="history-item ${c.id === current?.id ? 'selected' : ''}" data-change="${esc(c.id)}"><span class="status-dot ${c.status === 'complete' ? 'green' : ['cancelled', 'draft', 'no_changes'].includes(c.status) ? '' : 'orange'}"></span><span><strong>${esc(general(c) ? shortRequest(c) : titleCase(c.target.plan) + ": " + c.before + " → " + c.target.limit + " files")}</strong><small>${esc(c.id)} / ${esc(statusLabel(c))}</small></span></button>`).join('') : '<p class="history-empty">No changes here yet.<br>Create a change to begin.</p>';
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
  $('#change-title').textContent = changeTitle(c);
  $('#request-origin').textContent = c.origin === 'mattermost' ? 'From Mattermost' : 'Created in Ripple';
  $('#change-created').textContent = `Created ${time(c.created)}`;
  $('#change-status').textContent = statusLabel(c);
  $('#change-status').className = 'status-label ' + c.status;
  renderDelivery(c);
  $('#change-request').textContent = c.request + (c.clarifications || []).map(item => '\nClarification: ' + item.answer).join('');
  $('#decision-numbers').hidden = general(c);
  $('#decision-text').hidden = !general(c);
  const assessedAreas = c.assessments || {}, affectedNames = required(c).map(a => names[a]);
  $('#decision-heading').textContent = general(c) ? 'IMPACT' : 'THE DECISION';
  $('#decision-text').textContent = Object.values(assessedAreas).some(a => a.outcome === 'blocked') ? 'Waiting for your clarification.' : affectedNames.length ? affectedNames.join(' / ') + (affectedNames.length === 1 ? ' needs changes.' : ' need changes.') : Object.keys(assessedAreas).length === areas.length ? 'No workspace needs edits.' : 'Waiting for workspace assessments.';
  if (!general(c)) {
    $('#before-value').textContent = c.before;
    $('#after-value').textContent = c.target.limit;
  }
  $('#decision-label').textContent = general(c) ? 'Impact comes from workspace assessments.' : `${titleCase(c.target.plan)} / files per project`;
  const files = Object.values(c.proposals).reduce((sum, p) => sum + p.files.length, 0);
  const assessed = Object.keys(c.assessments || {}).length, involved = required(c).length;
  $('#scope-stats').innerHTML = `<button class="stat" data-action="impact"><span>${general(c) ? 'Workspaces assessed' : 'Workspaces inspected'}</span><strong>${general(c) ? assessed : Object.keys(c.inspections).length} / ${areas.length}</strong></button><button class="stat" data-action="files"><span>File updates proposed</span><strong>${files}</strong></button><button class="stat" data-action="impact"><span>Workspaces applied</span><strong>${Object.keys(c.applied).length} / ${involved || '?'}</strong></button>`;
  $('#tab-file-count').textContent = files;
  $('#tab-event-count').textContent = events().length;
  renderMap(); renderNextStep(); renderImpact(); renderChecks(); renderFiles();
}
function renderDelivery(change) {
  const delivery = change.git_delivery;
  $('#delivery-panel').hidden = !delivery;
  if (!delivery) return;
  const repositories = Object.values(delivery.repositories);
  $('#delivery-panel').innerHTML = `<strong>Isolated Git delivery</strong><p>Git workspace edits stay on these branches. Publish them for review; Ripple does not merge them or update the source files.</p>${repositories.map(repo => {
    const url = safeURL(repo.pull_request);
    return `<div class="delivery-repository"><code>${esc(repo.branch)}</code><span>${esc(repo.status)}</span>${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">Review pull request ↗</a>` : ''}${repo.error ? `<p class="inline-error">${esc(repo.error)}</p>` : ''}</div>`;
  }).join('')}`;
}
function renderMap() {
  const c = current, sw = connection(), sent = c.dispatches?.request?.status === 'sent';
  const activity = Object.keys(c.inspections).length > 0;
  const switchLabel = sent ? 'Request accepted' : sw.connected ? 'Room verified' : 'Optional chat connection';
  $('#route-map').classList.add('configured-route');
  const nodes = areas.map(area => {
    const proposed = c.proposals[area], inspected = c.inspections[area], applied = c.applied[area];
    const assessment = c.assessments?.[area];
    const status = assessment?.outcome === 'unaffected' ? 'Unaffected' : assessment?.outcome === 'blocked' ? 'Question for you' : applied ? 'Applied to workspace' : proposed ? `${proposed.files.length} file edits proposed` : inspected ? 'Inspection received' : 'No tool activity yet';
    return `<button class="route-node workspace-node ${applied ? 'applied' : assessment?.outcome === 'unaffected' ? 'unaffected' : ''}" data-area="${esc(area)}">
      <span class="node-type">${esc(agentLabel(area))}</span><strong>${esc(names[area])}</strong><small>${esc(status)}</small>
    </button>`;
  }).join('');
  $('#route-map').innerHTML = `<div class="route-source">
    <div class="route-node decision-node"><span class="node-type">YOUR REQUEST</span><strong>${esc(general(c) ? shortRequest(c) : changeTitle(c))}</strong></div>
    <button class="route-node switch-node" data-action="connect"><span class="node-type">TEAM CHAT</span><strong>Switch</strong><small>${esc(switchLabel)}</small></button>
    </div><div class="route-workspaces">${nodes}</div>`;
  $('#route-mode').textContent = sent ? 'Switch dispatch recorded' : activity ? 'Workspace tool activity received' : 'Waiting for workspace activity';
  $('#transport-summary').textContent = sent ? `Switch accepted the request for room ${c.dispatches.request.room_id}. Follow replies in that room.` : 'Use your CLI agents directly, or connect a Switch room for chat handoffs. Creating a request alone does not start agents.';
}
function button(text, action, style = '') {return `<button class="button compact ${style}" data-action="${action}" ${busy ? 'disabled' : ''}>${esc(text)}</button>`;}
function renderNextStep() {
  const c = current, sw = connection(), r = receipt();
  let heading, detail, buttons, style = '', icon = '↗';
  if (c.status === 'draft') {
    const active = state.changes.find(other => other.id !== c.id && other.status !== 'draft' && !closed(other));
    heading = 'Saved as a draft.';
    detail = active ? `${active.id} is active. This request stays in your ledger and can be resumed after that work finishes.` : 'Your request is preserved. Resume it when you are ready to send it to the agents.';
    buttons = active ? `<button class="button compact" data-change="${esc(active.id)}">View active request ↗</button>` : button('Resume this request ↗', 'resume', 'accent');
  } else if (c.status === 'no_changes') {
    heading = 'The agents found no changes to make.';
    detail = 'Each workspace has recorded its reasoning below. Review those findings in the room if you expected a different result.';
    buttons = button('View assessments', 'impact');
  } else if (c.status === 'needs_clarification') {
    heading = 'A workspace needs your answer.';
    detail = 'Read the question below. Reply through your coordinator or record your answer with the clarify command before reassessment.';
    buttons = button('View the question', 'impact');
  } else if (c.status === 'complete' && c.git_delivery) {
    const published = c.git_delivery.status === 'published';
    heading = published ? 'Git branches published for review.' : c.git_delivery.status === 'publish_failed' ? 'Git publication needs attention.' : 'Verified on isolated Git branches.';
    detail = published ? 'Review the linked pull requests and project CI. Merge through your Git review process. Ripple has not updated the source checkout.' : 'Publish pushes the reviewed branches and opens GitHub pull requests. Other Git remotes receive branches for your review process.';
    buttons = button('Inspect branch files', 'systems') + (published ? '' : button(c.git_delivery.status === 'publish_failed' ? 'Retry publication ↗' : 'Publish branches / PRs ↗', 'publish', 'accent'));
  } else if (c.status === 'complete') {
    heading = 'The affected work is complete.';
    detail = general(c) ? `${required(c).length} affected ${required(c).length === 1 ? "workspace applied its proposal" : "workspaces applied their proposals"}. The recorded acceptance conditions pass against the updated files.` : 'All affected areas applied their edits. The final checks passed against actual files and application behavior.';
    buttons = button('Inspect the result ↗', 'systems', 'dark'); style = 'complete'; icon = '✓';
  } else if (c.status === 'cancelled') {
    heading = 'This change was cancelled.'; detail = 'No edits were applied. The request stays in the ledger.'; buttons = button('New change ↗', 'new');
  } else if (c.status === 'awaiting_approval') {
    heading = 'Your review is the next step.'; detail = general(c) ? 'Review the file changes and whether the acceptance conditions cover your request. Approval covers this checked bundle.' : 'Read the actual file changes. Approval covers this exact checked bundle.';
    buttons = button('Review files', 'files') + button('Approve changes ↗', 'approve', 'accent');
  } else if (['ready_to_check', 'needs_revision', 'verification_failed'].includes(c.status)) {
    heading = c.status === 'ready_to_check' ? 'The proposals are ready to check together.' : 'An inconsistency needs attention.';
    detail = c.status === 'ready_to_check' ? 'Check the affected proposals together before approving.' : 'Read the failed checks below. Ask the responsible agent to revise its proposal in the room.';
    buttons = button('Run combined checks ↗', 'check', 'accent');
  } else if (general(c) && !c.approval && (Object.keys(c.inspections).length || c.origin === 'mattermost')) {
    const assessed = Object.keys(c.assessments || {}).length;
    heading = `${assessed} of ${areas.length} workspaces have assessed the impact.`;
    detail = 'Affected owners prepare proposals. Unaffected owners record why their workspace can stay as it is. Follow progress through CLI activity or your connected room.';
    buttons = button('View assessments', 'impact'); style = 'waiting'; icon = '↳';
  } else if (r?.status === 'sent') {
    const count = Object.keys(c.inspections).length;
    heading = phase() === 'approval' ? 'Approval sent. Waiting for application.' : count ? `${count} of ${areas.length} workspaces have reported an inspection.` : 'Switch accepted your request. Waiting for agents.';
    detail = phase() === 'approval' ? `${Object.keys(c.applied).length} of ${required(c).length} affected workspaces applied. Each agent will post its result in the room.` : 'The next update comes from a real agent tool call. If nothing arrives, check that the assigned sessions are running in Console.';
    buttons = button('Connection details ↗', 'connect'); style = 'waiting'; icon = '↳';
  } else if (!sw.configured && c.approval) {
    heading = 'Approved. Ask the affected agents to apply.';
    detail = 'Use the apply command through your CLI agents, or send the approval handoff to your connected room. Only affected workspaces are applied.';
    buttons = button('Open approval message ↗', 'handoff', 'accent');
  } else if (Object.keys(c.inspections).length && !sw.configured) {
    heading = `${Object.keys(c.inspections).length} of ${areas.length} workspaces have reported an inspection.`;
    detail = 'Actual agent tool activity has arrived. Follow the conversation in your Switch room while the remaining proposals are prepared.';
    buttons = button('View proposed files ↗', 'files'); style = 'waiting'; icon = '↳';
  } else if (sw.configured) {
    heading = phase() === 'approval' ? 'Send your approval to the working agents.' : 'Ready to send this change to Switch.';
    detail = r?.status === 'failed' ? r.message : 'This sends a real message to the configured room. Your assigned agent sessions must be running.';
    buttons = button(busy ? 'Sending…' : phase() === 'approval' ? 'Send approval ↗' : 'Send to Switch ↗', 'dispatch', 'accent');
  } else {
    heading = 'Your change is saved. Give it to your agents.';
    detail = 'Your CLI agents can inspect this request ID and prepare proposals. Manual handoff provides the full instructions. Switch is optional.';
    buttons = button('Manual handoff', 'handoff') + button('Connect Switch ↗', 'connect', 'accent');
  }
  const cancel = !Object.keys(c.applied).length && !closed(c) ? '<button class="text-button" data-action="cancel">Cancel</button>' : '';
  $('#next-step').className = 'next-step ' + style;
  $('#next-step').innerHTML = `<span class="step-icon">${icon}</span><div class="step-copy"><h2>${esc(heading)}</h2><p>${esc(detail)}</p></div><div class="step-buttons">${buttons}${cancel}</div>`;
}
function renderImpact() {
  const c = current, assessments = c.assessments || {};
  $('#impact-summary').textContent = general(c) ? Object.keys(assessments).length < areas.length || Object.values(assessments).some(a => a.outcome === 'blocked') ? `${Object.keys(assessments).length} assessed / impact discovery open` : `${Object.keys(assessments).length} assessed / ${required(c).length} affected` : `${Object.keys(c.proposals).length} of ${areas.length} areas proposed edits`;
  $('#impact-list').innerHTML = areas.map((area, i) => {
    const p = c.proposals[area], inspection = c.inspections[area], applied = c.applied[area], assessment = assessments[area];
    const summary = p?.summary || assessment?.reason || (inspection ? 'Inspection received. Waiting for the impact assessment.' : 'The agent has not inspected this workspace yet.');
    const status = applied ? 'APPLIED' : p ? 'PROPOSED' : assessment ? assessment.outcome.toUpperCase() : inspection ? 'INSPECTED' : 'AWAITING';
    return `<article id="impact-${area}" class="impact-row ${assessment?.outcome || ''}"><span class="impact-number">${String(i + 1).padStart(2, '0')}</span><button class="impact-name" data-area="${area}"><strong>${esc(names[area])} ↗</strong><small>${esc(agentLabel(area))}</small></button><div><p class="impact-detail">${esc(summary)}</p>${p && assessment ? `<p class="impact-reason">${esc(assessment.reason)}</p>` : ''}${p?.findings.length ? `<ul class="impact-findings">${p.findings.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}</div><span class="impact-state ${applied ? 'applied' : ''}">${status}</span></article>`;
  }).join('');
}
function renderChecks() {
  const check = current.check;
  $('#checks-panel').hidden = !check;
  if (!check) return;
  $('#checks-panel').innerHTML = `<div class="panel-heading"><span class="section-index">03 / ${check.mode === 'actual' ? 'VERIFIED RESULT' : 'PROPOSED BUNDLE CHECK'}</span><span class="small-note">${check.passed ? 'All checks passed' : 'Revision needed'}</span></div>${check.scope ? `<p class="check-scope">${esc(check.scope)}</p>` : ''}${check.checks.map(item => `<div class="check-row ${item.passed ? '' : 'failed'}"><span>${item.passed ? '✓' : '×'}</span><div><strong>${esc(item.name)}</strong><p>${esc(item.detail)}</p></div></div>`).join('')}`;
}
function renderFiles() {
  if (!current) return;
  const filterSelect = $('#file-filter');
  if (state?.areas && filterSelect) {
    const currentVal = filterSelect.value || 'all';
    const options = Object.entries(current.workspace_config || state.areas).map(([k, v]) => `<option value="${esc(k)}">${esc(v.title || k)}</option>`).join('');
    filterSelect.innerHTML = `<option value="all">All workspaces</option>${options}`;
    if ([...filterSelect.options].some(o => o.value === currentVal)) filterSelect.value = currentVal;
  }
  const filter = filterSelect ? filterSelect.value : 'all';
  const files = Object.entries(current.proposals).flatMap(([area, p]) => p.files.map(f => ({...f, area}))).filter(f => filter === 'all' || f.area === filter);
  const opened = new Set([...$('#file-list').querySelectorAll('details[open]')].map(e => e.dataset.path));
  $('#file-list').innerHTML = files.length ? files.map(f => {
    const path = f.area + '/' + f.path;
    const diff = (f.diff || '').split('\n').map(line => {
      const kind = line.startsWith('+++') || line.startsWith('---') ? 'header'
        : line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed'
        : line.startsWith('@@') ? 'hunk' : 'context';
      return `<span class="diff-line ${kind}">${esc(line)}</span>`;
    }).join('');
    return `<details class="file-diff" data-path="${esc(path)}" ${opened.has(path) ? 'open' : ''}>
      <summary>${esc(path)}<span>${current.applied[f.area] ? 'APPLIED' : f.new_file ? 'NEW FILE' : 'PROPOSED'}</span></summary>
      <div class="unified-diff" aria-label="Changes in ${esc(path)}"><pre>${diff}</pre></div>
      <details class="full-file-contents"><summary>Full before and after</summary>
        <div class="diff-grid"><div><label>BEFORE</label><pre>${esc(f.before)}</pre></div><div><label>AFTER</label><pre>${esc(f.content)}</pre></div></div>
      </details>
    </details>`;
  }).join('') : '<div class="file-empty">No proposed file edits yet.<br>Agent proposals will appear here after they inspect their workspaces.</div>';
}
function renderSystems() {
  const systems = state.systems;
  $('#plan-values').innerHTML = Object.entries(systems.application).map(([plan, value]) => `<div class="plan-value"><span>${esc(plan.toUpperCase())}</span><strong>${value.files_per_project}</strong><small>files per project</small></div>`).join('');
  const columns = Object.keys(systems.reporting[0] || {});
  $('#forecast').innerHTML = columns.length ? `<div class="table-wrap"><table><thead><tr>${columns.map(name => `<th>${esc(name.replaceAll('_', ' ').toUpperCase())}</th>`).join('')}</tr></thead><tbody>${systems.reporting.map(row => `<tr>${columns.map(name => `<td>${esc(row[name])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '<p>No report rows available. Inspect the source files below.</p>';
  $('#example-systems').hidden = state.example !== 'parcel';
  $('#workspace-files').innerHTML = Object.keys(state.areas).map(area => {
    const files = Object.entries(systems.files || {}).filter(([path]) => path.startsWith(area + '/'));
    return `<section class="workspace-group"><h3>${esc(state.areas[area].title)}</h3><p>${esc(systems.workspaces?.[area]?.effective_path || state.areas[area].path)}</p>${files.map(([path, content]) => `<details class="workspace-source"><summary>${esc(path)}</summary><pre>${esc(content)}</pre></details>`).join('') || '<p>No supported text files in this workspace.</p>'}</section>`;
  }).join('');
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
  if (state.api_version !== 6) {
    error('Restart the Ripple server once to load free-text requests, then refresh this page.');
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
    $('#request').value = '';
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
function manualPrompt() {return current?.handoff_messages?.[phase()] || 'Restart the Ripple server to load the current handoff instructions.';}
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
      if (action === 'approve') toast('Approved. Your agents can apply the affected proposals.');
      if (action === 'cancel') toast('Cancelled before application. The record is preserved.');
      if (action === 'check') toast('Combined check finished. Review the actual results.');
      if (action === 'resume') toast('Draft resumed. Give it to your agents when ready.');
      if (action === 'publish') toast('Git branches published. Review their pull requests before merging.');
    }
    await refresh();
  } catch (exc) {error(exc); await refresh();}
  finally {busy = false; renderNextStep();}
}
document.addEventListener('click', event => {
  const close = event.target.closest('[data-close]');
  if (close) return $('#' + close.dataset.close).close();
  const history = event.target.closest('[data-change]');
  if (history) {
    selectedId = history.dataset.change;
    current = state.changes.find(c => c.id === selectedId);
    $('.rail').classList.remove('history-open');
    $('#mobile-history-toggle').setAttribute('aria-expanded', 'false');
    render(); setTab('overview'); refresh(); return;
  }
  const example = event.target.closest('[data-example]');
  if (example) {$('#request').value = example.dataset.example === 'rename' ? 'Rename Parcel to Relay in current product references. Preserve historical release notes and keep product behavior unchanged.' : 'Add a customer guide explaining how to choose a descriptive project name. Link it from the getting started guide. Keep application behavior and reporting unchanged.'; return;}
  const area = event.target.closest('[data-area]');
  if (area) {const name = area.dataset.area; if (!current.proposals[name]) {setTab('overview'); $('#impact-' + name).scrollIntoView({behavior: 'smooth', block: 'center'});} else {$('#file-filter').value = name; renderFiles(); setTab('files');} return;}
  const tabButton = event.target.closest('[data-tab]');
  if (tabButton) return setTab(tabButton.dataset.tab);
  const control = event.target.closest('[data-action]');
  if (!control || !state) return;
  const action = control.dataset.action;
  if (action === 'impact') {setTab('overview'); $('#impact-list').scrollIntoView({behavior: 'smooth', block: 'center'}); return;}
  if (action === 'new') return newChange();
  if (action === 'connect') return connect();
  if (action === 'handoff') return handoff();
  if (['files', 'systems', 'activity'].includes(action)) return setTab(action);
  runAction(action);
});
$('#refresh').addEventListener('click', refresh);
$('#history-search').addEventListener('input', renderHistory);
$('#mobile-history-toggle').addEventListener('click', event => {
  const open = $('.rail').classList.toggle('history-open');
  event.currentTarget.setAttribute('aria-expanded', String(open));
});
$('#file-filter').addEventListener('change', renderFiles);
$('#request-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = event.submitter || $('#request-form [data-mode=create]'); submit.disabled = true;
  try {
    const result = await api('/api/changes', {request: $('#request').value, draft: submit?.dataset.mode === 'draft'});
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
$('#validate-form')?.addEventListener('submit', event => {event.preventDefault(); const files = [...$('#test-files').files]; if (!files.length) return toast('Choose files to test plan validation.'); validateFiles(files.map(f => f.name));});
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
