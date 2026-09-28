const queue = document.querySelector("#queue");
const dossier = document.querySelector("#dossier");
const gates = document.querySelector("#gates");
const balance = document.querySelector("#balance");
const answer = document.querySelector("#answer");
const question = document.querySelector("#question");

let selected = null;
let current = null;

function rupees(value) {
  return "₹" + Number(value).toLocaleString("en-IN");
}

function tag(kind) {
  return `<span class="tag ${kind}">${kind}</span>`;
}

async function loadInvoices() {
  const response = await fetch("/api/invoices");
  const body = await response.json();
  balance.textContent = rupees(body.balance_rupees);
  queue.innerHTML = "";
  for (const invoice of body.invoices) {
    const button = document.createElement("button");
    button.className = "invoice" + (invoice.invoice_id === selected ? " active" : "");
    button.type = "button";
    const state = invoice.settled ? "settled" : invoice.decision || "unread";
    button.innerHTML = `<strong>${invoice.invoice_id}</strong> ${tag(invoice.kind)}<small>${invoice.vendor} · ${rupees(invoice.invoice_rupees)} · ${state}</small>`;
    button.addEventListener("click", () => openInvoice(invoice.invoice_id));
    queue.appendChild(button);
  }
}

function renderDossier(invoice) {
  dossier.innerHTML = `
    <h2>Selected bill</h2>
    <p><strong>${invoice.invoice_id}</strong> ${tag(invoice.kind)}</p>
    <p>${invoice.vendor}<br>Purchase order ${invoice.po_id} ${rupees(invoice.po_rupees)}<br>Goods receipt ${invoice.grn_id} ${rupees(invoice.grn_rupees)}<br>Invoice amount ${rupees(invoice.invoice_rupees)}</p>
    <div class="note"><strong>Vendor note.</strong> ${invoice.note}</div>
  `;
}

function renderGates(review) {
  const truth = review.truthgraph;
  const prompt = review.promptgate;
  const hostile = review.promptgate_on_injected_amount;
  const naive = review.promptgate_on_invoice_amount;
  const settled = review.summary === "already settled";
  const klass = review.releasable ? "ok" : settled ? "ok" : "error";
  gates.innerHTML = `
    <h2>Before money moves</h2>
    <p class="decision ${klass}">${review.summary}</p>
    <article>
      <h2>PromptGate</h2>
      <p class="${prompt.passed ? "ok" : "error"}">Purchase-order sentence ${prompt.passed ? "passed" : "failed"}.</p>
      <p>${prompt.output}</p>
      ${naive && naive.output !== prompt.output ? `<p class="${naive.passed ? "ok" : "error"}">Invoice-amount sentence ${naive.passed ? "passed" : "failed"}: ${naive.output}</p>` : ""}
      ${hostile ? `<p class="error">Injected sentence failed: ${hostile.output}</p>` : ""}
    </article>
    <article>
      <h2>TruthGraph</h2>
      <p class="${truth.decision === "ALLOW" ? "ok" : "error"}">${truth.decision} · ${truth.verdict} · confidence ${truth.confidence}</p>
      <p class="muted">${(truth.reasons || []).slice(0, 2).join(" ")}</p>
    </article>
    <article>
      <h2>Ledger</h2>
      <p>${review.receipt ? `Sealed payment on this invoice: ${rupees(review.receipt.rupees)}.` : `Already paid on this invoice: ${rupees(review.already_paid_rupees)}.`}</p>
    </article>
    ${review.receipt ? `<article><h2>KarmaSakshi</h2><p class="ok">Verified. ₹${Number(review.receipt.rupees).toLocaleString("en-IN")} to ${review.receipt.beneficiary}.</p><p class="muted">Manifest ${String(review.receipt.manifest_hash).slice(0, 16)}… · seal ${review.receipt.seal_verified ? "holds" : "failed"}</p></article>` : ""}
    ${settled ? "" : `<button class="release" id="release" type="button" ${review.releasable ? "" : "disabled"}>Release ${review.releasable ? "after I say yes" : "blocked"}</button>`}
  `;
  const button = document.querySelector("#release");
  if (button) button.addEventListener("click", () => release(review.invoice_id));
}

async function openInvoice(invoiceId) {
  selected = invoiceId;
  const list = await fetch("/api/invoices").then((r) => r.json());
  current = list.invoices.find((item) => item.invoice_id === invoiceId);
  renderDossier(current);
  gates.innerHTML = `<h2>Before money moves</h2><p class="muted">Reading the purchase order, the goods receipt, and the sentence…</p>`;
  await loadInvoices();
  const review = await fetch(`/api/invoices/${invoiceId}/review`, { method: "POST" });
  if (!review.ok) {
    gates.innerHTML = `<p class="error">The review did not finish.</p>`;
    return;
  }
  renderGates(await review.json());
}

async function release(invoiceId) {
  const button = document.querySelector("#release");
  button.disabled = true;
  button.textContent = "Sealing…";
  const response = await fetch(`/api/invoices/${invoiceId}/release`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
  const body = await response.json();
  if (!body.ok) {
    gates.insertAdjacentHTML("beforeend", `<p class="error">${body.error}${body.detail ? ": " + body.detail : ""}</p>`);
    button.disabled = false;
    return;
  }
  gates.insertAdjacentHTML(
    "beforeend",
    `<article><h2>KarmaSakshi</h2><p class="ok">Verified. ${rupees(body.rupees)} to ${body.beneficiary}.</p><p class="muted">Manifest ${body.manifest_hash.slice(0, 16)}… · grant ${body.grant_id} · seal ${body.seal_verified ? "holds" : "failed"}</p></article>`
  );
  await loadInvoices();
}

async function runQuestion(text) {
  answer.innerHTML = `<p class="muted">Running the SELECT guard…</p>`;
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: text }),
  });
  const body = await response.json();
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

document.querySelector("#ask").addEventListener("click", () => {
  if (question.value.trim()) runQuestion(question.value.trim());
});
for (const button of document.querySelectorAll("[data-q]")) {
  button.addEventListener("click", () => runQuestion(button.dataset.q));
}

loadInvoices().catch(() => {
  queue.innerHTML = `<p class="error">The desk did not load.</p>`;
});
