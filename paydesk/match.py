"""Three-way match between invoice, purchase order, and goods receipt."""

from __future__ import annotations

from paydesk.books import vendor_by_id
from paydesk.policy import POLICY


def three_way(invoice: dict) -> dict:
    vendor = vendor_by_id(invoice["vendor_id"])
    lines = []
    line_pass = True
    for row in invoice.get("lines") or []:
        ok = (
            row["invoice_rupees"] == row["po_rupees"] == row["grn_rupees"]
            and row["qty_ordered"] == row["qty_received"]
        )
        variance = row["invoice_rupees"] - row["grn_rupees"]
        line_pass = line_pass and ok
        lines.append({**row, "matched": ok, "variance_rupees": variance})

    header_ok = invoice["invoice_rupees"] == invoice["po_rupees"] == invoice["grn_rupees"]
    variance = invoice["invoice_rupees"] - min(invoice["po_rupees"], invoice["grn_rupees"])
    vendor_ok = vendor["status"] not in POLICY["block_vendor_status"]
    matched = header_ok and line_pass and vendor_ok and variance <= int(POLICY["max_variance_rupees"])

    reasons = []
    if not header_ok:
        reasons.append(
            f"Header mismatch: invoice ₹{invoice['invoice_rupees']}, "
            f"PO ₹{invoice['po_rupees']}, GRN ₹{invoice['grn_rupees']}."
        )
    if not line_pass:
        reasons.append("One or more lines do not match quantity or amount.")
    if not vendor_ok:
        reasons.append(f"Vendor {vendor['name']} is on status '{vendor['status']}'.")
    if matched:
        reasons.append("Invoice, purchase order, and goods receipt agree.")

    score = 100
    if not header_ok:
        score -= 40
    if not line_pass:
        score -= 30
    if not vendor_ok:
        score -= 30
    score = max(0, score)

    return {
        "matched": matched,
        "score": score,
        "variance_rupees": variance,
        "vendor_status": vendor["status"],
        "vendor_ok": vendor_ok,
        "header_ok": header_ok,
        "lines_ok": line_pass,
        "lines": lines,
        "reasons": reasons,
        "policy": {
            "max_variance_rupees": POLICY["max_variance_rupees"],
            "require_three_way_match": POLICY["require_three_way_match"],
        },
    }
