const queue = document.querySelector("#queue");
const dossier = document.querySelector("#dossier");
const gates = document.querySelector("#gates");
const balance = document.querySelector("#balance");
const answer = document.querySelector("#answer");
const question = document.querySelector("#question");
const timeline = document.querySelector("#timeline");
const actorSelect = document.querySelector("#actor");
const ops = document.querySelector("#ops");
const auditFeed = document.querySelector("#audit-feed");

let selected = null;
let current = null;
let filter = "all";
let invoicesCache = [];
let roles = {};

function rupees(value) {
  return "₹" + Number(value).toLocaleString("en-IN");
}

function tag(kind) {
  return `<span class="tag ${kind}">${kind}</span>`;
}

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(await response.text());
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  return response.text();
}

async function boot() {
  const dash = await api("/api/dashboard");
  roles = dash.roles || {};
  actorSelect.innerHTML = Object.entries(roles)
    .map(([id, row]) => `<option value="${id}">${row.name} · ${row.role}</option>`)
    .join("");
  actorSelect.value = dash.actor;
  balance.textContent = rupees(dash.balance_rupees);
  renderOps(dash);
  await loadInvoices();
  await loadAudit();
}

async function loadInvoices() {
  const body = await api("/api/invoices");
  balance.textContent = rupees(body.balance_rupees);
  invoicesCache = body.invoices;
  queue.innerHTML = "";
  for (const invoice of invoicesCache) {
    if (filter !== "all" && invoice.stage !== filter) continue;
    const button = document.createElement("button");
    button.className = "invoice" + (invoice.invoice_id === selected ? " active" : "");
    button.type = "button";
    button.innerHTML = `<strong>${invoice.invoice_id}</strong> ${tag(invoice.kind)} ${tag(invoice.stage)}
      <small>${invoice.vendor} · ${rupees(invoice.invoice_rupees)} · ${invoice.priority}</small>`;
    button.addEventListener("click", () => openInvoice(invoice.invoice_id));
    queue.appendChild(button);
  }
}

function renderDossier(invoice, review) {
  const match = review?.match;
  const lines = review?.lines || [];
  dossier.innerHTML = `
    <h2>Selected bill</h2>
    <div class="card">
      <p><strong>${invoice.invoice_id}</strong> ${tag(invoice.kind)} ${tag(invoice.stage || "unread")}</p>
      <p>${invoice.vendor} · ${invoice.vendor_status || review?.vendor?.status || ""}
        <br>PO ${invoice.po_id} · GRN ${invoice.grn_id}
        <br>Due in ${invoice.due_days} days · priority ${invoice.priority}
        ${invoice.dual_required || review?.needs_dual ? " · dual approval" : ""}</p>
      <div class="match-grid">
        <div><span class="muted">Invoice</span><strong>${rupees(invoice.invoice_rupees)}</strong></div>
        <div><span class="muted">Purchase order</span><strong>${rupees(invoice.po_rupees)}</strong></div>
        <div><span class="muted">Goods receipt</span><strong>${rupees(invoice.grn_rupees)}</strong></div>
      </div>
      ${match ? `<p class="${match.matched ? "ok" : "error"}">Three-way match score ${match.score}. ${match.reasons[0] || ""}</p>` : ""}
      <div class="note"><strong>Vendor note.</strong> ${invoice.note || review?.invoice?.note || ""}</div>
      ${lines.length ? `<table><tr><th>SKU</th><th>Ordered</th><th>Received</th><th>Invoice</th><th>PO</th><th>GRN</th></tr>
        ${lines.map((line) => `<tr>
          <td>${line.sku}</td><td>${line.qty_ordered}</td><td>${line.qty_received}</td>
          <td>${rupees(line.invoice_rupees)}</td><td>${rupees(line.po_rupees)}</td><td>${rupees(line.grn_rupees)}</td>
        </tr>`).join("")}</table>` : ""}
    </div>
  `;
}

function renderTimeline(events) {
  if (!events?.length) {
    timeline.innerHTML = `<p class="muted">No events yet.</p>`;
    return;
  }
  timeline.innerHTML = events
    .slice(0, 12)
    .map((event) => {
      const label = event.kind || event.detail?.kind || "event";
      const when = (event.at || "").replace("T", " ").slice(0, 19);
      return `<div class="timeline-item"><strong>${event.source || "desk"} · ${label}</strong><span>${when} · ${event.actor || "—"}</span></div>`;
    })
    .join("");
}

function renderGates(review) {
  const truth = review.truthgraph;
  const prompt = review.promptgate;
  const hostile = review.promptgate_on_injected_amount;
  const naive = review.promptgate_on_invoice_amount;
  const settled = review.stage === "settled";
  const awaiting = review.stage === "awaiting_finance";
  const klass = review.releasable || settled || awaiting ? "ok" : "error";
  const role = roles[actorSelect.value]?.role;

  let actions = "";
  if (settled) {
    actions = "";
  } else if (awaiting && role === "finance") {
    actions = `<button class="approve" id="approve" type="button">Finance approve & seal</button>`;
  } else if (awaiting) {
    actions = `<p class="muted">Waiting on finance. Switch actor to Arjun Kapoor.</p>`;
  } else if (review.releasable) {
    const label = review.needs_dual ? "Confirm for finance" : "Release after I say yes";
    actions = `<button class="release" id="release" type="button">${label}</button>`;
  } else {
    actions = `<button class="release" type="button" disabled>Release blocked</button>`;
  }

  gates.innerHTML = `
    <h2>Control plane</h2>
    <p class="decision ${klass}">${review.summary}</p>
    <article>
      <h2>PromptGate</h2>
      <p class="${prompt.passed ? "ok" : "error"}">PO sentence ${prompt.passed ? "passed" : "failed"}.</p>
      <p>${prompt.output}</p>
      ${naive && naive.output !== prompt.output ? `<p class="${naive.passed ? "ok" : "error"}">Invoice-amount sentence ${naive.passed ? "passed" : "failed"}: ${naive.output}</p>` : ""}
      ${hostile ? `<p class="error">Injected sentence failed: ${hostile.output}</p>` : ""}
    </article>
    <article>
      <h2>TruthGraph</h2>
      <p class="${truth.decision === "ALLOW" ? "ok" : "error"}">${truth.decision} · ${truth.verdict} · ${truth.confidence}</p>
      <p class="muted">${(truth.reasons || []).slice(0, 2).join(" ")}</p>
    </article>
    <article>
      <h2>Match + ledger</h2>
      <p>Score ${review.match.score}. Already paid: ${rupees(review.already_paid_rupees)}. Vendor ${review.vendor.status}.</p>
    </article>
    ${review.receipt ? `<article><h2>KarmaSakshi passport</h2>
      <p class="ok">Verified ${rupees(review.receipt.rupees)} to ${review.receipt.beneficiary}.</p>
      <p class="muted">Grant ${review.receipt.grant_id} · by ${review.receipt.authorized_by || "—"}</p>
      <pre class="passport">${(review.receipt.passport_markdown || "").slice(0, 1200)}</pre>
    </article>` : ""}
    ${actions}
  `;
  const releaseBtn = document.querySelector("#release");
  if (releaseBtn) releaseBtn.addEventListener("click", () => release(review.invoice_id));
  const approveBtn = document.querySelector("#approve");
  if (approveBtn) approveBtn.addEventListener("click", () => approve(review.invoice_id));
  renderTimeline(review.timeline);
}

async function openInvoice(invoiceId) {
  selected = invoiceId;
  const list = await api("/api/invoices");
  current = list.invoices.find((item) => item.invoice_id === invoiceId);
  gates.innerHTML = `<h2>Control plane</h2><p class="muted">Running gates…</p>`;
  await loadInvoices();
  const review = await api(`/api/invoices/${invoiceId}/review`, { method: "POST" });
  // note is on full invoice from dossier if needed
  const dossierData = await api(`/api/invoices/${invoiceId}/dossier`);
  current = { ...current, note: dossierData.invoice.note, due_days: dossierData.invoice.due_days };
  renderDossier(current, review);
  renderGates(review);
  await loadOps();
  await loadAudit();
}

async function release(invoiceId) {
  const button = document.querySelector("#release");
  if (button) {
    button.disabled = true;
    button.textContent = "Working…";
  }
  const body = await api(`/api/invoices/${invoiceId}/release`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
  if (body.pending) {
    renderGates(body.review);
    await loadInvoices();
    await loadOps();
    return;
  }
  if (!body.ok) {
    gates.insertAdjacentHTML("beforeend", `<p class="error">${body.error}${body.detail ? ": " + body.detail : ""}</p>`);
    if (button) button.disabled = false;
    return;
  }
  await openInvoice(invoiceId);
}

async function approve(invoiceId) {
  const button = document.querySelector("#approve");
  if (button) {
    button.disabled = true;
    button.textContent = "Sealing…";
  }
  const body = await api(`/api/invoices/${invoiceId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved: true }),
  });
  if (!body.ok) {
    gates.insertAdjacentHTML("beforeend", `<p class="error">${body.error || "approve failed"}</p>`);
    return;
  }
  await openInvoice(invoiceId);
}

async function runQuestion(text) {
  answer.innerHTML = `<p class="muted">Running SELECT guard…</p>`;
  const body = await api("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: text }),
  });
  if (!body.success) {
    answer.innerHTML = `<div class="answer error"><strong>Refused.</strong> ${body.error || "No answer."}${body.sql ? `<p><code>${body.sql}</code></p>` : ""}</div>`;
    return;
  }
  const rows = body.rows || [];
  const head = rows[0] ? Object.keys(rows[0]) : [];
  const table = rows.length
    ? `<table><tr>${head.map((key) => `<th>${key}</th>`).join("")}</tr>${rows
        .map((row) => `<tr>${head.map((key) => `<td>${row[key]}</td>`).join("")}</tr>`)
        .join("")}</table>`
    : "<p>No rows.</p>";
  answer.innerHTML = `<div class="answer"><p class="muted">${body.route} · ${body.guard}</p><code>${body.sql}</code>${table}</div>`;
}

function renderOps(dash) {
  const stages = dash.by_stage || {};
  ops.innerHTML = `
    <div class="ops-card"><h3>Cash</h3><div class="big">${rupees(dash.balance_rupees)}</div><p class="muted">Opening ${rupees(dash.opening_rupees)}</p></div>
    <div class="ops-card"><h3>Open exposure</h3><div class="big">${rupees(dash.open_exposure_rupees)}</div><p class="muted">Unread + ready + finance queue</p></div>
    <div class="ops-card"><h3>Blocked</h3><div class="big">${dash.blocked_count}</div><p class="muted">Duplicate, mismatch, hold, partial</p></div>
    <div class="ops-card"><h3>Finance queue</h3><div class="big">${(dash.awaiting_finance || []).length}</div><p class="muted">Dual approval ≥ ${rupees(dash.dual_approval_rupees)}</p></div>
    <div class="ops-card"><h3>Pipeline</h3><p>${Object.entries(stages).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}</p></div>
    <div class="ops-card"><h3>Libraries</h3><p class="muted">${Object.keys(dash.libraries || {}).join(" · ")}</p><p>Failure memory ${dash.failure_memory?.enabled ? "on" : "off"}</p></div>
  `;
}

async function loadOps() {
  renderOps(await api("/api/dashboard"));
}

async function loadAudit() {
  const body = await api("/api/audit");
  auditFeed.innerHTML = (body.events || [])
    .slice(0, 40)
    .map((event) => {
      const label = event.kind || "event";
      const when = (event.at || "").replace("T", " ").slice(0, 19);
      return `<div class="timeline-item"><strong>${event.source || "desk"} · ${label}</strong><span>${when} · ${event.actor || "—"} · ${event.invoice_id || ""}</span></div>`;
    })
    .join("") || `<p class="muted">No audit events.</p>`;
}

document.querySelector("#ask").addEventListener("click", () => {
  if (question.value.trim()) runQuestion(question.value.trim());
});
for (const button of document.querySelectorAll("[data-q]")) {
  button.addEventListener("click", () => runQuestion(button.dataset.q));
}
for (const chip of document.querySelectorAll(".chip")) {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((node) => node.classList.remove("active"));
    chip.classList.add("active");
    filter = chip.dataset.filter;
    loadInvoices();
  });
}
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", async () => {
    document.querySelectorAll(".tab").forEach((node) => node.classList.remove("active"));
    document.querySelectorAll(".view").forEach((node) => node.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#view-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "ops") await loadOps();
    if (tab.dataset.tab === "audit") await loadAudit();
  });
}
actorSelect.addEventListener("change", async () => {
  await api("/api/actor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor: actorSelect.value }),
  });
  if (selected) await openInvoice(selected);
  await loadOps();
});
document.querySelector("#reset").addEventListener("click", async () => {
  await api("/api/demo/reset", { method: "POST" });
  selected = null;
  dossier.innerHTML = `<p class="muted">Demo reset. Pick an invoice.</p>`;
  gates.innerHTML = `<h2>Control plane</h2><p class="muted">PromptGate · TruthGraph · Match · KarmaSakshi · AgentEval</p>`;
  timeline.innerHTML = `<p class="muted">No events yet.</p>`;
  await boot();
});

boot().catch((err) => {
  queue.innerHTML = `<p class="error">Desk failed to load: ${err.message}</p>`;
});
