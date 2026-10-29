"""Sample portfolio content, for testing the public pages before the real text is written.

Only the name, the field of work and the SAP modules come from Ferdinand; the
rest is placeholder text, marked "(sample)" where it could be read as a fact,
to be replaced in the admin area before going live.
"""

from typing import Any

PROFILE: dict[str, Any] = {
    "full_name": "Ferdinand Bizimana",
    "headline": "Supply chain & inventory analyst · SAP S/4HANA (MM, EWM, SD, FI)",
    "location": "Kigali, Rwanda",
    "summary_md": (
        "I turn SAP exports into decisions: stock accuracy, expiry prevention, order fill "
        "rate and accountability reports that boards and programme partners can rely on."
    ),
    "about_md": (
        "I work in public health supply chain, where every stock line is a medicine that "
        "has to reach a health facility on time and before it expires.\n\n"
        "My daily tools are SAP S/4HANA Materials Management, Extended Warehouse "
        "Management, Sales and Distribution and Finance. I build repeatable analyses on "
        "top of them: period-end stock reconciliation, physical inventory variance "
        "investigation, expiry monitoring, stock sufficiency against consumption and "
        "programme stock accountability.\n\n"
        "*(Sample text: replace it with your own story in Admin > Profile.)*"
    ),
    "linkedin_url": "",
    "github_url": "https://github.com/ferdinandbizimana",
    "availability": "Open to supply chain and SAP analytics roles (sample)",
    # True of this system; replace with your own results in Admin > Profile.
    "highlights": [
        {"value": "13", "label": "supply chain analyses automated, SAP export to board report"},
        {"value": "4", "label": "SAP S/4HANA modules in daily use: MM, EWM, SD, FI"},
        {"value": "100%", "label": "of reports self-checked: every total ties back to SAP"},
    ],
}

EXPERIENCE: list[dict[str, Any]] = [
    {
        "role": "Supply chain and SAP analyst (sample)",
        "organisation": "Public health supply chain (sample)",
        "location": "Kigali, Rwanda",
        "start_month": "2022-07",
        "end_month": None,
        "description_md": (
            "- Period-end stock reconciliation between SAP Finance and the warehouse\n"
            "- Physical inventory variance investigation and follow-up of corrections\n"
            "- Quarterly programme stock accountability reports for partners\n"
            "- Monthly expiry monitoring with justifications from the sales pharmacist"
        ),
    },
    {
        "role": "Inventory and warehouse officer (sample)",
        "organisation": "Medical stores (sample)",
        "location": "Kigali, Rwanda",
        "start_month": "2019-01",
        "end_month": "2022-06",
        "description_md": (
            "- Receiving, putaway and picking in SAP EWM\n"
            "- Weekly spot checks and bin accuracy\n"
            "- Stock transfers between the central warehouse and the branches"
        ),
    },
]

SKILLS: list[dict[str, Any]] = [
    {"name": "SAP S/4HANA", "items": ["MM", "EWM", "SD", "FI", "MB51", "MB5B", "ZSTOCKREPORT"]},
    {
        "name": "Supply chain",
        "items": [
            "Inventory accuracy",
            "Expiry management",
            "Order fill rate",
            "Stock sufficiency (AMC, MOS)",
            "Physical inventory",
        ],
    },
    {"name": "Reporting", "items": ["Excel", "Dashboards", "Board reports"]},
]

PROJECTS: list[dict[str, Any]] = [
    {
        "slug": "programme-stock-accountability",
        "title": "Programme stock accountability",
        "summary": (
            "A quarterly report of programme stock by programme, plant and product: opening, "
            "receipts, goods issues, expired stock scrapped and closing, with self-checks."
        ),
        "body_md": (
            "## The problem\nEvery quarter, partners need to know how the stock they fund "
            "moved: what came in, what went out, what expired and what is left.\n\n"
            "## What I built\nAn analysis that reads the previous report, the G/L stock lines "
            "and MB51, rolls every plant and product forward from opening to closing, and "
            "produces the Excel, Word, PowerPoint and interactive dashboard in one run.\n\n"
            "## Result\nThe report that took days is ready in minutes, and every figure ties "
            "back to SAP through its self-checks.\n\n*(Sample case study: figures omitted.)*"
        ),
        "tags": ["SAP MM", "Reporting", "Programmes"],
        "published": True,
        "featured": True,
    },
    {
        "slug": "expiry-monitoring",
        "title": "Monthly expiry monitoring and follow-up",
        "summary": (
            "Expired and near-expiry stock per plant from two ZSTOCKREPORT snapshots, the value "
            "saved, and a monthly e-mail with a justification link for the sales pharmacist."
        ),
        "body_md": (
            "## The problem\nExpiries are discovered too late, and nobody records why they "
            "happened.\n\n## What I built\nA monthly comparison of stock snapshots: batches "
            "that were due to expire, what was cleared, what expired, and a secure page where "
            "each expired item gets a root cause.\n\n*(Sample case study: figures omitted.)*"
        ),
        "tags": ["Expiry", "ZSTOCKREPORT", "Automation"],
        "published": True,
        "featured": False,
    },
    {
        "slug": "spot-check-accuracy",
        "title": "Weekly spot check accuracy",
        "summary": (
            "Quantity and line accuracy of the weekly bin spot check, with the variances that "
            "comments explain left out and wrong batches or expiry dates flagged."
        ),
        "body_md": (
            "## The problem\nSpot checks were compiled by hand and accuracy was hard to "
            "compare week to week.\n\n## What I built\nAn analysis of the EWM bin list against "
            "the quantity found, by WBS, storage type and responsible person, compared with "
            "the previous week.\n\n*(Sample case study: figures omitted.)*"
        ),
        "tags": ["SAP EWM", "Inventory accuracy"],
        "published": True,
        "featured": False,
    },
]
