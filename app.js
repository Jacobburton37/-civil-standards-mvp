const state = { jurisdictions: [], documents: [], filters: {}, selectedJurisdiction: '' };
const $ = (id) => document.getElementById(id);
const escapeHtml = (value='') => String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const fmtDate = (s) => s ? new Date(s).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}) : 'Not yet checked';

async function api(path, opts={}) {
  const res = await fetch(path, {headers:{'Content-Type':'application/json'}, ...opts});
  if (!res.ok) throw new Error((await res.json()).error || `HTTP ${res.status}`);
  return res.json();
}

async function loadInitial() {
  try {
    const [stats, jurisdictions, filters] = await Promise.all([
      api('/api/stats'), api('/api/jurisdictions'), api('/api/filters')
    ]);
    state.jurisdictions = jurisdictions;
    state.filters = filters;
    renderAdminJurisdictions();
    renderStats(stats);
    renderJurisdictions();
    buildFilters();
    await loadDocuments();
  } catch (err) {
    $('documentList').innerHTML = `<div class="empty">Could not load the local API: ${escapeHtml(err.message)}</div>`;
  }
}

function renderStats(s) {
  const data = [
    [s.jurisdictions, 'Jurisdictions indexed'],
    [s.documents, 'Standards records'],
    [s.verified, 'Verified records'],
    [s.changes, 'Changes awaiting review']
  ];
  $('stats').innerHTML = data.map(([v,l]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join('');
}

function renderJurisdictions() {
  $('jurisdictionCount').textContent = `${state.jurisdictions.length} active`;
  $('jurisdictionList').innerHTML = state.jurisdictions.map(j => `
    <button class="jurisdiction-item ${String(j.id)===String(state.selectedJurisdiction)?'active':''}" data-jid="${j.id}">
      <span><strong>${escapeHtml(j.name)}</strong><small>${escapeHtml(j.state)} • ${escapeHtml(j.agency || 'Agency')}</small></span>
      <span class="count-pill">${j.document_count}</span>
    </button>`).join('');
  document.querySelectorAll('.jurisdiction-item').forEach(btn => btn.onclick = async () => {
    const id = btn.dataset.jid;
    state.selectedJurisdiction = String(state.selectedJurisdiction) === id ? '' : id;
    $('jurisdictionFilter').value = state.selectedJurisdiction;
    renderJurisdictions();
    await loadDocuments();
  });
}

function renderAdminJurisdictions() {
  const el = $('adminJurisdiction');
  if (!el) return;
  el.innerHTML = '<option value="">Select jurisdiction</option>' + state.jurisdictions.map(j => `<option value="${j.id}">${escapeHtml(j.state)} · ${escapeHtml(j.name)}</option>`).join('');
}

function buildFilters() {
  $('jurisdictionFilter').innerHTML += state.jurisdictions.map(j => `<option value="${j.id}">${escapeHtml(j.name)}</option>`).join('');
  $('disciplineFilter').innerHTML += state.filters.disciplines.map(x => `<option>${escapeHtml(x)}</option>`).join('');
  $('categoryFilter').innerHTML += state.filters.categories.map(x => `<option>${escapeHtml(x)}</option>`).join('');
}

async function loadDocuments() {
  const p = new URLSearchParams();
  const q = $('searchInput').value.trim();
  if (q) p.set('q', q);
  if ($('jurisdictionFilter').value) p.set('jurisdiction_id', $('jurisdictionFilter').value);
  if ($('disciplineFilter').value) p.set('discipline', $('disciplineFilter').value);
  if ($('categoryFilter').value) p.set('category', $('categoryFilter').value);
  state.documents = await api(`/api/documents?${p}`);
  renderDocuments();
}

function renderDocuments() {
  $('resultMeta').textContent = `${state.documents.length} record${state.documents.length===1?'':'s'} matching your search`;
  if (!state.documents.length) {
    $('documentList').innerHTML = '<div class="empty"><strong>No standards found.</strong><br>Try removing a filter or searching a broader term.</div>';
    return;
  }
  $('documentList').innerHTML = state.documents.map(d => {
    const changed = d.status === 'Change detected';
    const badgeClass = changed ? 'change' : (d.status === 'Verified' ? 'verified' : '');
    return `<article class="document-card">
      <div>
        <div class="doc-kicker">
          <span>${escapeHtml(d.state)} · ${escapeHtml(d.jurisdiction)}</span>
          <span class="badge">${escapeHtml(d.category)}</span>
          <span class="badge ${badgeClass}">${escapeHtml(d.status)}</span>
        </div>
        <h3>${escapeHtml(d.title)}</h3>
        <p>${escapeHtml(d.discipline)}${d.detail_number ? ` · ${escapeHtml(d.detail_number)}` : ''} · Last verified ${escapeHtml(fmtDate(d.last_verified))}</p>
      </div>
      <div class="doc-actions"><button class="open-btn" data-doc="${d.id}">View record →</button></div>
    </article>`;
  }).join('');
  document.querySelectorAll('[data-doc]').forEach(btn => btn.onclick = () => openDocument(btn.dataset.doc));
}

async function openDocument(id) {
  const d = await api(`/api/documents/${id}`);
  $('dialogContent').innerHTML = `<div class="dialog-body">
    <span class="eyebrow">${escapeHtml(d.state)} · ${escapeHtml(d.jurisdiction)}</span>
    <h2>${escapeHtml(d.title)}</h2>
    <p class="lead">${escapeHtml(d.notes || 'Official-source standards record.')}</p>
    <div class="detail-grid">
      <div class="detail-cell"><span>Agency</span><strong>${escapeHtml(d.agency || '—')}</strong></div>
      <div class="detail-cell"><span>Status</span><strong>${escapeHtml(d.status)}</strong></div>
      <div class="detail-cell"><span>Discipline</span><strong>${escapeHtml(d.discipline)}</strong></div>
      <div class="detail-cell"><span>Revision</span><strong>${escapeHtml(d.revision_label || 'Not stated')}</strong></div>
      <div class="detail-cell"><span>File type</span><strong>${escapeHtml(d.file_type || 'Web')}</strong></div>
      <div class="detail-cell"><span>Last verified</span><strong>${escapeHtml(fmtDate(d.last_verified))}</strong></div>
    </div>
    <a class="source-link" href="${escapeHtml(d.source_url)}" target="_blank" rel="noopener">Open official source ↗</a>
    <div class="history"><h3>Version history</h3>
      ${d.versions.length ? d.versions.map(v => `<div class="history-item"><strong>${v.is_current?'Current version':'Previous version'}</strong> · detected ${escapeHtml(fmtDate(v.detected_at))} · hash ${escapeHtml(v.content_hash.slice(0,12))}…</div>`).join('') : '<div class="history-item">Run <code>python monitor.py</code> to create the first source fingerprint.</div>'}
    </div>
  </div>`;
  $('documentDialog').showModal();
}

async function loadChanges() {
  const rows = await api('/api/changes');
  $('changeList').innerHTML = rows.length ? rows.map(c => `<article class="change-card">
    <div>
      <div class="change-meta">${escapeHtml(c.state)} · ${escapeHtml(c.jurisdiction)} · ${escapeHtml(fmtDate(c.detected_at))}</div>
      <h3>${escapeHtml(c.title)}</h3>
      <p>${escapeHtml(c.summary)}</p>
    </div>
    <span class="badge change">${escapeHtml(c.review_status)}</span>
  </article>`).join('') : '<div class="empty">No source changes have been detected yet. Run the monitor to establish baselines and check sources.</div>';
}

let searchTimer;
$('searchInput').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadDocuments, 180); });
['jurisdictionFilter','disciplineFilter','categoryFilter'].forEach(id => $(id).addEventListener('change', async () => {
  if (id === 'jurisdictionFilter') { state.selectedJurisdiction = $('jurisdictionFilter').value; renderJurisdictions(); }
  await loadDocuments();
}));
$('clearFilters').onclick = async () => {
  $('searchInput').value=''; $('jurisdictionFilter').value=''; $('disciplineFilter').value=''; $('categoryFilter').value='';
  state.selectedJurisdiction=''; renderJurisdictions(); await loadDocuments();
};
$('dialogClose').onclick = () => $('documentDialog').close();
$('documentDialog').addEventListener('click', e => { if (e.target === $('documentDialog')) $('documentDialog').close(); });
document.querySelectorAll('.nav-btn').forEach(btn => btn.onclick = async () => {
  document.querySelectorAll('.nav-btn').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.view').forEach(x => x.classList.remove('active'));
  btn.classList.add('active');
  $(`view-${btn.dataset.view}`).classList.add('active');
  if (btn.dataset.view === 'changes') await loadChanges();
  if (btn.dataset.view === 'admin') await loadAdminChanges();
});

loadInitial();


async function refreshCore() {
  const [stats, jurisdictions, filters] = await Promise.all([api('/api/stats'), api('/api/jurisdictions'), api('/api/filters')]);
  state.jurisdictions = jurisdictions; state.filters = filters;
  renderStats(stats); renderJurisdictions(); renderAdminJurisdictions();
  $('jurisdictionFilter').innerHTML = '<option value="">All jurisdictions</option>' + state.jurisdictions.map(j => `<option value="${j.id}">${escapeHtml(j.name)}</option>`).join('');
  $('disciplineFilter').innerHTML = '<option value="">All disciplines</option>' + state.filters.disciplines.map(x => `<option>${escapeHtml(x)}</option>`).join('');
  $('categoryFilter').innerHTML = '<option value="">All document types</option>' + state.filters.categories.map(x => `<option>${escapeHtml(x)}</option>`).join('');
  await loadDocuments();
}

$('jurisdictionForm').addEventListener('submit', async (e) => {
  e.preventDefault(); const form = new FormData(e.currentTarget); const payload = Object.fromEntries(form.entries());
  try {
    await api('/api/jurisdictions', {method:'POST', body:JSON.stringify(payload)});
    $('jurisdictionMessage').textContent = 'Jurisdiction added.'; e.currentTarget.reset(); await refreshCore();
  } catch(err) { $('jurisdictionMessage').textContent = err.message; }
});

$('documentForm').addEventListener('submit', async (e) => {
  e.preventDefault(); const form = new FormData(e.currentTarget); const payload = Object.fromEntries(form.entries());
  payload.jurisdiction_id = Number(payload.jurisdiction_id);
  try {
    await api('/api/documents', {method:'POST', body:JSON.stringify(payload)});
    $('documentMessage').textContent = 'Source added. Run the monitor to establish its baseline.'; e.currentTarget.reset(); renderAdminJurisdictions(); await refreshCore();
  } catch(err) { $('documentMessage').textContent = err.message; }
});

async function loadAdminChanges() {
  const rows = await api('/api/changes');
  const pending = rows.filter(x => x.review_status === 'Needs review');
  $('adminChangeList').innerHTML = pending.length ? pending.map(c => `<div class="review-row">
    <div><strong>${escapeHtml(c.title)}</strong><div class="change-meta">${escapeHtml(c.state)} · ${escapeHtml(c.jurisdiction)} · ${escapeHtml(c.summary)}</div></div>
    <div class="review-actions"><button class="approve" data-review="${c.id}" data-status="Approved">Approve</button><button data-review="${c.id}" data-status="Rejected">Reject</button></div>
  </div>`).join('') : '<div class="empty">No changes awaiting review.</div>';
  document.querySelectorAll('[data-review]').forEach(btn => btn.onclick = async () => {
    await api(`/api/changes/${btn.dataset.review}/review`, {method:'POST', body:JSON.stringify({review_status:btn.dataset.status})});
    await loadAdminChanges(); await loadChanges(); const stats = await api('/api/stats'); renderStats(stats);
  });
}

// Apple/PWA behavior
(function setupAppleExperience() {
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  if (standalone) document.body.classList.add('standalone');

  const installDialog = $('installDialog');
  const openInstallHelp = () => {
    if (installDialog && typeof installDialog.showModal === 'function') installDialog.showModal();
  };
  if ($('installButton')) $('installButton').onclick = openInstallHelp;
  if ($('aboutInstallButton')) $('aboutInstallButton').onclick = openInstallHelp;
  if ($('installDialogClose')) $('installDialogClose').onclick = () => installDialog.close();
  if (installDialog) installDialog.addEventListener('click', e => { if (e.target === installDialog) installDialog.close(); });

  if ($('installHelpText') && !isIOS) {
    $('installHelpText').innerHTML = 'On iPhone or iPad, open this site in Safari, tap <strong>Share</strong>, then choose <strong>Add to Home Screen</strong>. On Mac, you can keep using it directly in Safari.';
  }

  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js').catch(() => {}));
  }

  function showNetworkState() {
    let banner = document.querySelector('.network-banner');
    if (navigator.onLine) {
      if (banner) banner.remove();
      return;
    }
    if (!banner) {
      banner = document.createElement('div');
      banner.className = 'network-banner';
      banner.textContent = 'Offline — live standards data is unavailable';
      document.body.appendChild(banner);
    }
  }
  window.addEventListener('online', showNetworkState);
  window.addEventListener('offline', showNetworkState);
  showNetworkState();
})();
