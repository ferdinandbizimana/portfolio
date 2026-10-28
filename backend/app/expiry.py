"""Monthly expiry follow-up (Ferdinand, 26 October 2026).

Each expiry monitoring run can have a review: one justification line per
expired material, filled in by the sales pharmacist through a secure link (a
root cause from the list; "Other" needs the reason in words), and one line per
material expiring within 6 months, where the pharmacist records the measure taken
to avoid the expiry (Ferdinand, 28 October 2026). On the last day of
each month the latest run is e-mailed to the pharmacist, copied to the managers:
expired stock and what expires within 3 and 3 to 6 months, value per plant, with
the batches attached as Excel and the link to justify the expired items.
"""

import calendar
import secrets
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AnalysisRun, ExpiryJustification, ExpiryReview
from app.reporting.documents import TableBlock, ValueFormat
from app.reporting.excel import build_workbook
from app.reporting.guard import BannedWordingError, check_report
from app.reporting.interactive import (
    ChartSpec,
    DashSection,
    DetailSpec,
    Filter,
    InteractiveDashboard,
    KpiTile,
    Measure,
    TableSpec,
    build_html,
)
from app.storage import LocalStorage

ANALYSIS_KEY = "expiry_monitoring"
COMMERCIAL, PROGRAMME = "Commercial (RMS-OWN)", "Programme (RMS-PRG)"
OTHER_CAUSE = "Other (give the reason)"
# Root causes named in Ferdinand's expiry justifications report (2025 - 2026).
ROOT_CAUSES = [
    "Project termination and patient drop-outs",
    "Post-epidemic residual stock",
    "Demand stagnation and low facility consumption",
    "Forecast inaccuracies and supplier minimum order quantities",
    "Quality recalls and late supplier deliveries",
    "Short remaining shelf life on receipt",
    "Cost-absorption barrier (free to paid)",
    "Clinical protocol and guideline revisions",
    "Donated stock and warehouse saturation",
    "Laboratory analyser breakdown and ERP delays",
    OTHER_CAUSE,
]
WITHIN_3, THREE_TO_6 = "Within 3 months", "3 to 6 months"
EXPIRED, PROJECTED = "expired", "projected"
OTHER_MEASURE = "Other (describe the measure)"
# Measures to avoid an expiry: the actions named in the monthly e-mail
# (redistribution, donation, sale); the list is open for Ferdinand to adjust.
MEASURES = [
    "Redistribute to facilities that use it",
    "Transfer to another branch",
    "Inform customers and promote the product",
    "Donation (agreed with Sales)",
    "Return or exchange with the supplier",
    "Issue first (FEFO priority)",
    OTHER_MEASURE,
]


class JustificationError(ValueError):
    pass


def table(storage: LocalStorage, run_id: int, name: str) -> pd.DataFrame:
    key = f"runs/{run_id}/tables/{name}.parquet"
    if not storage.exists(key):
        return pd.DataFrame()
    frame: pd.DataFrame = pq.read_table(storage.path(key)).to_pandas()
    return frame


def latest_run(db: Session) -> AnalysisRun | None:
    return db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.analysis_key == ANALYSIS_KEY, AnalysisRun.status == "succeeded")
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    ).first()


def expired_items(expired: pd.DataFrame) -> list[dict[str, Any]]:
    """One line per expired material (all plants together), largest value first."""
    if expired.empty:
        return []
    items = []
    for material, part in expired.groupby("Material", sort=True):
        owners = sorted(set(part["Owner"]))
        items.append(
            {
                "material": str(material),
                "description": str(part["Description"].max() or ""),
                "owner": owners[0] if len(owners) == 1 else ", ".join(owners),
                "plants": ", ".join(sorted(set(part["Plant"].astype(str))))[:500],
                "value": float(part["Value"].sum()),
            }
        )
    return sorted(items, key=lambda i: (-i["value"], i["material"]))


def projected_items(batches: pd.DataFrame) -> list[dict[str, Any]]:
    """One line per material expiring within 6 months (all plants together), with
    its earliest band, the soonest first and then the largest value."""
    if batches.empty:
        return []
    soon = batches[batches["Expiry Band"].isin([WITHIN_3, THREE_TO_6])]
    items = []
    for material, part in soon.groupby("Material", sort=True):
        owners = sorted(set(part["Owner"]))
        bands = set(part["Expiry Band"])
        items.append(
            {
                "material": str(material),
                "description": str(part["Description"].max() or ""),
                "owner": owners[0] if len(owners) == 1 else ", ".join(owners),
                "plants": ", ".join(sorted(set(part["Plant"].astype(str))))[:500],
                "value": float(part["Value"].sum()),
                "band": WITHIN_3 if WITHIN_3 in bands else THREE_TO_6,
            }
        )
    return sorted(items, key=lambda i: (i["band"] != WITHIN_3, -i["value"], i["material"]))


def ensure_review(db: Session, storage: LocalStorage, run: AnalysisRun) -> ExpiryReview:
    """The review of a run, created with one justification line per expired material
    and one measure line per material expiring within 6 months."""
    review = db.scalars(select(ExpiryReview).where(ExpiryReview.run_id == run.id)).first()
    if review is None:
        review = ExpiryReview(
            run_id=run.id,
            closing_date=date.fromisoformat(str(run.parameters["closing_date"])),
            token=secrets.token_urlsafe(32),
            mailed_month="",
        )
        db.add(review)
        db.flush()
        for item in expired_items(table(storage, run.id, "expired")):
            db.add(ExpiryJustification(review_id=review.id, kind=EXPIRED, **item))
    has_projected = db.scalars(
        select(ExpiryJustification.id).where(
            ExpiryJustification.review_id == review.id, ExpiryJustification.kind == PROJECTED
        )
    ).first()
    if has_projected is None:  # also for reviews prepared before measures were recorded
        for item in projected_items(table(storage, run.id, "closing_batches")):
            db.add(ExpiryJustification(review_id=review.id, kind=PROJECTED, **item))
    db.flush()
    return review


def justify(
    item: ExpiryJustification, root_cause: str, reason: str, by: str, now: datetime
) -> None:
    """Record why an item expired, or (projected items) the measure taken to avoid it."""
    root_cause, reason = root_cause.strip(), reason.strip()
    if item.kind == PROJECTED:
        if root_cause not in MEASURES:
            raise JustificationError("Choose a measure from the list.")
        if root_cause == OTHER_MEASURE and len(reason) < 3:
            raise JustificationError('Describe the measure when it is "Other".')
    elif root_cause not in ROOT_CAUSES:
        raise JustificationError("Choose a root cause from the list.")
    elif root_cause == OTHER_CAUSE and len(reason) < 3:
        raise JustificationError('Give the reason when the root cause is "Other".')
    item.root_cause = root_cause
    item.reason = reason
    item.justified_by = by.strip()[:200]
    item.justified_at = now


def link(settings: Settings, review: ExpiryReview) -> str:
    return f"{settings.site_url.rstrip('/')}/expiry/{review.token}"


def mail_due(settings: Settings, local_now: datetime) -> bool:
    """The last day of the month, from the e-mail time."""
    last_day = calendar.monthrange(local_now.year, local_now.month)[1]
    hours, minutes = (int(p) for p in settings.expiry_mail_time.split(":"))
    send_at = local_now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    return local_now.day == last_day and local_now >= send_at


def outlook(storage: LocalStorage, run_id: int) -> pd.DataFrame:
    """Expired, within 3 months and 3 to 6 months, value per plant (plants with any)."""
    plants = table(storage, run_id, "by_plant")
    if plants.empty:
        return plants
    columns = ["Plant", "Plant Name", "Expired Value", "Within 3 Months", "3 to 6 Months"]
    plants = plants[columns]
    keep = plants[["Expired Value", "Within 3 Months", "3 to 6 Months"]].abs().sum(axis=1) > 0
    return plants[keep].reset_index(drop=True)


def attachment(storage: LocalStorage, run_id: int, closing: date) -> bytes:
    """Excel: value per plant, then the expired batches and those expiring within 6 months."""
    batches = table(storage, run_id, "closing_batches")
    expired = table(storage, run_id, "expired")
    columns = [
        "Plant",
        "Plant Name",
        "Material",
        "Description",
        "Batch",
        "WBS",
        "Owner",
        "Expiry Date",
        "Quantity",
        "Value",
    ]
    formats: dict[str, ValueFormat] = {"Value": "money", "Quantity": "number"}
    money: dict[str, ValueFormat] = dict.fromkeys(
        ("Expired Value", "Within 3 Months", "3 to 6 Months"), "money"
    )

    def part(band: str) -> pd.DataFrame:
        if batches.empty:
            return pd.DataFrame(columns=columns)
        return batches.loc[batches["Expiry Band"] == band, columns].reset_index(drop=True)

    return build_workbook(
        "Expiry follow-up",
        f"Stock at {closing:%d %B %Y}",
        [],
        [
            TableBlock("Value per plant", outlook(storage, run_id), money, total_row=True),
            TableBlock(
                "Expired batches",
                expired[columns] if not expired.empty else part("Expired"),
                formats,
            ),
            TableBlock(WITHIN_3, part(WITHIN_3), formats),
            TableBlock(THREE_TO_6, part(THREE_TO_6), formats),
        ],
        [],
    )


def _rwf(value: float) -> str:
    return f"RWF {value:,.0f}"


def monthly_message(
    settings: Settings, storage: LocalStorage, review: ExpiryReview, month: str
) -> EmailMessage:
    plants = outlook(storage, review.run_id)
    totals = (
        plants[["Expired Value", "Within 3 Months", "3 to 6 Months"]].sum()
        if not plants.empty
        else pd.Series({"Expired Value": 0.0, "Within 3 Months": 0.0, "3 to 6 Months": 0.0})
    )
    mail = EmailMessage()
    mail["From"] = formataddr(("RMS expiry follow-up", settings.mail_from))
    mail["To"] = settings.expiry_mail_to
    if settings.expiry_mail_cc:
        mail["Cc"] = settings.expiry_mail_cc
    if settings.expiry_mail_bcc:
        mail["Bcc"] = settings.expiry_mail_bcc
    mail["Subject"] = (
        f"Expiry follow-up {month}: expired {_rwf(totals['Expired Value'])}, "
        f"within 3 months {_rwf(totals['Within 3 Months'])}"
    )
    mail["Message-ID"] = make_msgid(domain=settings.mail_from.rsplit("@", 1)[-1] or "localhost")
    lines = [
        f"- {p}{' ' + n if n else ''}: expired {_rwf(e)}, within 3 months {_rwf(w)}, "
        f"3 to 6 months {_rwf(s)}"
        for p, n, e, w, s in plants.itertuples(index=False)
    ]
    body = [
        "Dear colleague,",
        "",
        f"Stock expiry position at {review.closing_date:%d %B %Y} (ZSTOCKREPORT), value per plant:",
        "",
        *(lines or ["- No expired stock and nothing expiring within six months."]),
        "",
        f"Total: expired {_rwf(totals['Expired Value'])}, within 3 months "
        f"{_rwf(totals['Within 3 Months'])}, 3 to 6 months {_rwf(totals['3 to 6 Months'])}.",
        "",
        "The batches are in the attached workbook. Through the link below, please record "
        "the measure you are taking for each item expiring within six months "
        "(redistribution, transfer, donation, sale) and justify each expired item, "
        "choosing its root cause:",
        link(settings, review),
        "",
    ]
    content = attachment(storage, review.run_id, review.closing_date)
    try:
        check_report("xlsx", content)
    except BannedWordingError:
        content = b""
        body.append("The workbook could not be attached; open the link to see the batches.")
    mail.set_content("\n".join(body))
    if content:
        mail.add_attachment(
            content,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"Expiry_follow_up_{review.closing_date:%Y-%m-%d}.xlsx",
        )
    return mail


def intervention_frame(items: list[ExpiryJustification]) -> pd.DataFrame:
    """The measures recorded for the items expiring within 6 months."""
    return pd.DataFrame(
        [
            {
                "Material": i.material,
                "Description": i.description,
                "Stock owner": i.owner,
                "Plants": i.plants,
                "Expires": i.band,
                "Value (RWF)": i.value,
                "Measure": i.root_cause or "No measure recorded yet",
                "Details": i.reason,
                "Recorded by": i.justified_by,
                "Recorded on": i.justified_at.strftime("%Y-%m-%d") if i.justified_at else "",
            }
            for i in items
            if i.kind == PROJECTED
        ],
        columns=[
            "Material",
            "Description",
            "Stock owner",
            "Plants",
            "Expires",
            "Value (RWF)",
            "Measure",
            "Details",
            "Recorded by",
            "Recorded on",
        ],
    )


def justification_frame(items: list[ExpiryJustification]) -> pd.DataFrame:
    items = [i for i in items if i.kind != PROJECTED]
    return pd.DataFrame(
        [
            {
                "Material": i.material,
                "Description": i.description,
                "Stock owner": i.owner,
                "Plants": i.plants,
                "Expired value (RWF)": i.value,
                "Root cause": i.root_cause or "Not justified yet",
                "Reason": i.reason,
                "Justified by": i.justified_by,
                "Justified on": i.justified_at.strftime("%Y-%m-%d") if i.justified_at else "",
            }
            for i in items
        ],
        columns=[
            "Material",
            "Description",
            "Stock owner",
            "Plants",
            "Expired value (RWF)",
            "Root cause",
            "Reason",
            "Justified by",
            "Justified on",
        ],
    )


def justification_workbook(review: ExpiryReview, items: list[ExpiryJustification]) -> bytes:
    frame = justification_frame(items)
    return build_workbook(
        "Expiry justifications",
        f"Expired stock at {review.closing_date:%d %B %Y}",
        [],
        [
            TableBlock("Justifications", frame, {"Expired value (RWF)": "money"}, total_row=True),
            TableBlock(
                "Measures to avoid expiry",
                intervention_frame(items),
                {"Value (RWF)": "money"},
                total_row=True,
            ),
        ],
        [],
    )


def justification_dashboard(review: ExpiryReview, items: list[ExpiryJustification]) -> bytes:
    """The "Expiry justifications" board view: commercial and programme loss,
    root causes, and the top 20 items of each with their justification."""
    frame = justification_frame(items)
    items = [i for i in items if i.kind != PROJECTED]
    facts = pd.DataFrame(
        {
            "Stock owner": frame["Stock owner"],
            "Root cause": frame["Root cause"],
            "Item": [
                f"{d} [{m}]" if d else m
                for d, m in zip(frame["Description"], frame["Material"], strict=True)
            ],
            "Reason": frame["Reason"].replace("", "—"),
            "Justified": ["Yes" if i.root_cause else "No" for i in items],
            "Value": frame["Expired value (RWF)"].astype(float),
        }
    )
    measures = (
        Measure("skus", "SKUs", count=True),
        Measure("value", "Expired value (RWF)", "rwf", sum="Value"),
        Measure(
            "commercial",
            "Commercial loss (RWF)",
            "rwf",
            sum="Value",
            where=("Stock owner", (COMMERCIAL,)),
        ),
        Measure(
            "programme",
            "CP and programme loss (RWF)",
            "rwf",
            sum="Value",
            where=("Stock owner", (PROGRAMME,)),
        ),
        Measure(
            "commercial_n", "Commercial SKUs", count=True, where=("Stock owner", (COMMERCIAL,))
        ),
        Measure("programme_n", "Programme SKUs", count=True, where=("Stock owner", (PROGRAMME,))),
        Measure("justified", "Justified SKUs", count=True, where=("Justified", ("Yes",))),
        Measure("justified_pct", "Justified", "pct", ratio=("justified", "skus")),
    )
    top = ("Item", "Reason")
    dashboard = InteractiveDashboard(
        title=f"Expiry justifications: {review.closing_date:%d %B %Y}",
        subtitle="Expired stock by root cause, commercial and programme",
        intro=(
            "Every expired item with the root cause and the reason given by the sales "
            "pharmacist. Commercial stock (RMS-OWN) is lost sales revenue; programme stock "
            "(RMS-PRG) is lost donor commodities."
        ),
        facts={"items": facts},
        measures={"items": measures},
        filters=(
            Filter("Stock owner", "Stock owner", "Commercial and programme"),
            Filter("Root cause", "Root cause", "All root causes"),
            Filter("Justified", "Justified", "All items"),
        ),
        kpis=(
            KpiTile("Total expired value", "value", "items", "{skus} SKUs", "red"),
            KpiTile("Commercial loss", "commercial", "items", "{commercial_n} SKUs", "amber"),
            KpiTile("CP and programme loss", "programme", "items", "{programme_n} SKUs", "amber"),
            KpiTile("Items justified", "justified_pct", "items", "{justified} of {skus}", "green"),
        ),
        sections=(
            DashSection(
                "A · Root causes",
                blocks=(
                    ChartSpec(
                        "Expired value by root cause",
                        "items",
                        "Root cause",
                        ("value",),
                        kind="hbar",
                        sort="desc",
                        sort_by="value",
                    ),
                    TableSpec(
                        "By root cause",
                        "items",
                        ("Root cause",),
                        ("skus", "commercial", "programme", "value"),
                        sort_by="value",
                    ),
                ),
            ),
            DashSection(
                "B · Top 20 commercial and programme items",
                blocks=(
                    TableSpec(
                        "Commercial products: top 20",
                        "items",
                        top,
                        ("commercial",),
                        sort_by="commercial",
                        limit=20,
                        hide_zero=True,
                    ),
                    TableSpec(
                        "CP and programme products: top 20",
                        "items",
                        top,
                        ("programme",),
                        sort_by="programme",
                        limit=20,
                        hide_zero=True,
                    ),
                ),
            ),
            DashSection(
                "C · All items",
                blocks=(
                    DetailSpec(
                        "Expired items",
                        "items",
                        (
                            ("Item", "Item", "text"),
                            ("Stock owner", "Owner", "text"),
                            ("Value", "Value (RWF)", "rwf"),
                            ("Root cause", "Root cause", "text"),
                            ("Reason", "Reason", "text"),
                        ),
                        sort_by="Value",
                    ),
                ),
            ),
        ),
        footer="Rwanda Medical Supply · Expiry justifications.",
    )
    return build_html(dashboard)
