"""Local finance policy for Aravali Traders. Not a multi-tenant SaaS config."""

from __future__ import annotations

POLICY = {
    "company": "Aravali Traders",
    "site": "Okhla Phase II",
    "currency": "INR",
    "operating_account": "aravali-operating",
    "opening_rupees": 1_000_000,
    "dual_approval_rupees": 100_000,
    "max_variance_rupees": 0,
    "require_three_way_match": True,
    "block_vendor_status": ["hold", "blocked"],
    "roles": {
        "clerk.meera": {"name": "Meera Iyer", "role": "clerk", "can_review": True, "can_release": True},
        "finance.arjun": {
            "name": "Arjun Kapoor",
            "role": "finance",
            "can_review": True,
            "can_approve": True,
            "can_release": True,
        },
        "auditor.neha": {
            "name": "Neha Sethi",
            "role": "auditor",
            "can_review": True,
            "can_approve": False,
            "can_release": False,
        },
    },
    "libraries": {
        "promptgate": "9f74eb567a71cf360ebc6d1ec079f77e88f871f3",
        "truthgraph": "2ac10fbd8d50a444da9151bd23d45711d63f627f",
        "agentic-data-analyst": "8fc22fa6e821507e8cc96d31d98f220c9f491054",
        "agenteval": "5a8e1cfcfbab41dda282d4db21813fae09dba196",
        "karmasakshi": "local-package",
    },
}


def dual_required(rupees: int) -> bool:
    return rupees >= int(POLICY["dual_approval_rupees"])
