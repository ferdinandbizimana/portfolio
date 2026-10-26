"""Spot-check variance follow-up (Ferdinand, 26 October 2026).

Every variance found in a spot check, in the picking register (items missing at
picking) or in a physical inventory document becomes a case assigned to the
person responsible for its storage bin. The person receives an e-mail with a
secure link, corrects the stock and closes the case through the link with the
reason and the responsible unit. Open cases are amber, corrected ones green,
cases open for more than `variance_overdue_days` days red. A list of open cases
goes to each person every working morning. Every e-mail is copied (BCC) to
`variance_bcc`.

The bin list (storage bin -> responsible person) is uploaded as a file: names are
matched whatever the order of the words and with small spelling differences;
names that are warehouse units (RECEIVING, PICKING) are not people and their
bins are left out. The e-mails are listed below the bins (name, e-mail).
"""

import difflib
import re
import secrets
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import BinOwner, VarianceCase, VarianceStaff

SPOT_CHECK, PICKING, PHYSICAL_INVENTORY = "spot_check", "picking", "physical_inventory"
SOURCES = {
    SPOT_CHECK: "Spot check",
    PICKING: "Missing at picking",
    PHYSICAL_INVENTORY: "Physical inventory",
}
DATASET_SOURCE = {
    "spot_check": SPOT_CHECK,
    "picking_register": PICKING,
    "ewm_physical_inventory": PHYSICAL_INVENTORY,
}
UNITS = ["Receiving", "Picking", "Putaway / bin moves", "System (EWM–ERP)"]  # noqa: RUF001
OPEN, CORRECTED = "open", "corrected"
NAME_SIMILARITY = 0.85


def bin_code(value: object) -> str:
    return _text(value).upper().replace(" ", "")


def _text(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):  # type: ignore[call-overload]
        return ""
    text = str(value).strip()
    return text[:-2] if re.fullmatch(r"\d+\.0", text) else text  # 1000001.0 read as a number


def person_key(name: str) -> str:
    """Words of a name in alphabetical order: "IRAFASHA CEDRICK" = "Cedrick Irafasha"."""
    return " ".join(sorted(re.sub(r"[^A-Z ]", " ", name.upper()).split()))


def same_person(a: str, b: str) -> bool:
    ka, kb = person_key(a), person_key(b)
    return bool(ka) and (
        ka == kb or difflib.SequenceMatcher(None, ka, kb).ratio() >= NAME_SIMILARITY
    )


def unit_names(settings: Settings) -> set[str]:
    return {person_key(n) for n in settings.variance_unit_names.split(",") if n.strip()}


# --- Bin list -------------------------------------------------------------------------------


@dataclass
class BinImport:
    staff: list[str] = field(default_factory=list)
    bins: int = 0
    unit_bins: int = 0
    emails: int = 0
    without_email: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def import_bin_list(db: Session, frame: pd.DataFrame, settings: Settings) -> BinImport:
    """Replace the bin owners with the uploaded list (dataset bin_owners)."""
    result = BinImport()
    units = unit_names(settings)
    contacts: dict[str, str] = {}
    bins: list[tuple[str, str, str, str]] = []  # bin, name, type, section
    for person, bin_cell, kind, section in zip(
        frame["RESPONSIBLE PERSON"].map(_text),
        frame["Storage Bin"].map(_text),
        frame["Storage Type"].map(_text),
        frame["Storage Section"].map(_text),
        strict=True,
    ):
        if "@" in bin_cell:  # the e-mail block below the bins: name, e-mail
            contacts[person] = bin_cell
        elif bin_cell.strip().lower() in ("email", "e-mail", "mail"):
            continue  # the heading of that block
        elif "@" in person:
            result.warnings.append("A row has e-mail addresses but no name; it was left out.")
        elif person and bin_cell:
            if person_key(person) in units:
                result.unit_bins += 1
            else:
                bins.append((bin_code(bin_cell), person, kind, section))

    # One person per group of names that differ only in order or spelling; the
    # spelling used most often is kept.
    groups: list[Counter[str]] = []
    for name, _ in Counter(b[1] for b in bins).most_common():
        group = next((g for g in groups if same_person(g.most_common(1)[0][0], name)), None)
        if group is None:
            groups.append(Counter())
            group = groups[-1]
        group[name] += sum(1 for b in bins if b[1] == name)
    existing = db.scalars(select(VarianceStaff)).all()
    staff_of: dict[str, VarianceStaff] = {}
    for group in groups:
        name = group.most_common(1)[0][0].title()
        member = next((s for s in existing if same_person(s.name, name)), None)
        if member is None:
            member = VarianceStaff(name=name, email="", active=True)
            db.add(member)
        member.active = True
        email = next((e for c, e in contacts.items() if same_person(c, name)), "")
        if email:
            member.email = email.lower()
            result.emails += 1
        elif not member.email:
            result.without_email.append(name)
        for spelling in group:
            staff_of[spelling] = member
        result.staff.append(name)
    db.flush()
    db.execute(delete(BinOwner))
    seen: set[str] = set()
    for code, name, kind, section in bins:
        if code in seen:
            result.warnings.append(f"Bin {code} is listed twice; the first owner is kept.")
            continue
        seen.add(code)
        db.add(
            BinOwner(
                storage_bin=code,
                staff_id=staff_of[name].id,
                storage_type=kind[:20],
                storage_section=section[:20],
            )
        )
    result.bins = len(seen)
    return result


# --- Variance cases -------------------------------------------------------------------------


@dataclass
class CaseImport:
    created: int = 0
    duplicates: int = 0
    unassigned: int = 0
    no_variance: int = 0
    warnings: list[str] = field(default_factory=list)
    new_cases: list[int] = field(default_factory=list)


def _number(value: object) -> float | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):  # type: ignore[call-overload]
        return None
    return float(value)  # type: ignore[arg-type]


def _day(value: object) -> date | None:
    if value is None or pd.isna(value):  # type: ignore[call-overload]
        return None
    return pd.Timestamp(value).date()  # type: ignore[arg-type]


def case_lines(source: str, frame: pd.DataFrame, file_sha: str) -> list[dict[str, Any]]:
    """The lines of an uploaded file that are variances, as case fields."""
    lines: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        if source == SPOT_CHECK:
            system, counted = (
                _number(row.get("Avail. Qty in AUoM")),
                _number(row.get("Counted Quantities")),
            )
            difference = _number(row.get("Variance"))
            if difference is None and system is not None and counted is not None:
                difference = counted - system
            line: dict[str, Any] = {
                "storage_bin": bin_code(row["Storage Bin"]),
                "product": _text(row["Product"]),
                "description": _text(row.get("Product Description")),
                "batch": _text(row.get("Batch")),
                "system_qty": system,
                "counted_qty": counted,
                "difference_qty": difference,
                "found_on": None,
                "reported_by": "",
                "reference": _text(row.get("Stock Reference Doc.")),
            }
            # A spot check file is one check: the same line in another file is a new case.
            key_extra = file_sha
        elif source == PICKING:
            missing = _number(row["Quantity"])
            line = {
                "storage_bin": bin_code(row["BIN LOCATION"]),
                "product": _text(row["PRODUCT CODE"]),
                "description": _text(row.get("PRODUCT DESCRIPTION")),
                "batch": _text(row.get("BATCH")),
                "system_qty": None,
                "counted_qty": None,
                "difference_qty": -abs(missing) if missing else None,
                "found_on": _day(row.get("Date reported")),
                "reported_by": _text(row.get("REPORTER/PICKING STAFF")),
                "reference": "",
            }
            # The register grows over time: a line already imported is the same case.
            key_extra = ""
        else:
            line = {
                "storage_bin": bin_code(row["Storage Bin"]),
                "product": _text(row.get("Product")),
                "description": _text(row.get("Product Description")),
                "batch": _text(row.get("Batch")),
                "system_qty": _number(row["Book Quantity"]),
                "counted_qty": _number(row["Counted Quantity"]),
                "difference_qty": _number(row["Difference Quantity"]),
                "found_on": _day(row.get("Count Date")),
                "reported_by": _text(row.get("Counter")),
                "reference": f"{_text(row['Phys. Inventory Doc.'])}/{_text(row.get('Item'))}",
            }
            key_extra = ""
        if not line["storage_bin"]:
            continue
        line["dedup_key"] = "|".join(
            str(part)
            for part in (
                source,
                line["storage_bin"],
                line["product"],
                line["batch"],
                line["reference"],
                line["found_on"] or "",
                line["difference_qty"],
                key_extra,
            )
        )[:300]
        lines.append(line)
    return lines


def import_cases(
    db: Session, source: str, frame: pd.DataFrame, data_file_id: int | None, file_sha: str
) -> CaseImport:
    result = CaseImport()
    owners = {b.storage_bin: b.staff_id for b in db.scalars(select(BinOwner))}
    known = set(db.scalars(select(VarianceCase.dedup_key)))
    for line in case_lines(source, frame, file_sha):
        difference = line["difference_qty"]
        if difference is None or abs(difference) < 1e-9:
            result.no_variance += 1
            continue
        if line["dedup_key"] in known:
            result.duplicates += 1
            continue
        known.add(line["dedup_key"])
        staff_id = owners.get(line["storage_bin"])
        if staff_id is None:
            result.unassigned += 1
        case = VarianceCase(
            source=source,
            data_file_id=data_file_id,
            staff_id=staff_id,
            status=OPEN,
            token=secrets.token_urlsafe(32),
            **line,
        )
        db.add(case)
        db.flush()
        result.new_cases.append(case.id)
        result.created += 1
    return result


def is_overdue(case: VarianceCase, today: date, settings: Settings) -> bool:
    if case.status != OPEN:
        return False
    started = case.created_at.date() if case.created_at else today
    return (today - started).days > settings.variance_overdue_days


def colour(case: VarianceCase, today: date, settings: Settings) -> str:
    if case.status == CORRECTED:
        return "green"
    return "red" if is_overdue(case, today, settings) else "amber"


class CaseClosed(Exception):
    pass


def correct(
    case: VarianceCase, reason: str, unit: str, action: str, by: str, now: datetime
) -> None:
    if case.status == CORRECTED:
        raise CaseClosed("This variance was already marked as corrected.")
    if unit not in UNITS:
        raise ValueError(f"Unknown responsible unit {unit!r}.")
    case.status = CORRECTED
    case.reason = reason.strip()
    case.responsible_unit = unit
    case.action_taken = action.strip()
    case.corrected_by = by.strip()
    case.corrected_at = now


# --- E-mail ---------------------------------------------------------------------------------


def link(settings: Settings, case: VarianceCase) -> str:
    return f"{settings.site_url.rstrip('/')}/variance/{case.token}"


def _line(settings: Settings, case: VarianceCase, today: date) -> str:
    late = "  [OVERDUE]" if is_overdue(case, today, settings) else ""
    what = f"{case.product} {case.description}".strip() or "(no product)"
    batch = f", batch {case.batch}" if case.batch else ""
    return (
        f"- Bin {case.storage_bin}: {what}{batch}, difference {case.difference_qty:g} "
        f"({SOURCES.get(case.source, case.source)}){late}\n  {link(settings, case)}"
    )


def message(
    settings: Settings, person: VarianceStaff, subject: str, intro: str, lines: list[str]
) -> EmailMessage:
    mail = EmailMessage()
    mail["From"] = formataddr(("RMS stock variances", settings.mail_from))
    mail["To"] = person.email
    if settings.variance_bcc:
        mail["Bcc"] = settings.variance_bcc
    mail["Subject"] = subject
    mail["Message-ID"] = make_msgid(domain=settings.mail_from.rsplit("@", 1)[-1] or "localhost")
    body = [
        f"Dear {person.name},",
        "",
        intro,
        "",
        *lines,
        "",
        "Open each link to record that the variance is corrected, with its reason and the "
        "responsible unit.",
        f"A variance still open after {settings.variance_overdue_days} days is shown in red.",
        "",
    ]
    mail.set_content("\n".join(body))
    return mail


def assignment_messages(
    db: Session, settings: Settings, case_ids: list[int], today: date
) -> list[EmailMessage]:
    """One e-mail per person for newly assigned cases."""
    cases = db.scalars(select(VarianceCase).where(VarianceCase.id.in_(case_ids))).all()
    by_person: dict[int, list[VarianceCase]] = {}
    for case in cases:
        if case.staff_id is not None:
            by_person.setdefault(case.staff_id, []).append(case)
    out = []
    for staff_id, items in sorted(by_person.items()):
        person = db.get(VarianceStaff, staff_id)
        if person is None or not person.active or not person.email:
            continue
        items.sort(key=lambda c: (c.storage_bin, c.id))
        out.append(
            message(
                settings,
                person,
                f"Stock variances to correct: {len(items)} new in your bins",
                f"{len(items)} new stock variances were found in your storage bins:",
                [_line(settings, c, today) for c in items],
            )
        )
    return out


def digest_due(settings: Settings, local_now: datetime) -> bool:
    """Working days (Monday to Friday) from the reminder time."""
    hours, minutes = (int(p) for p in settings.variance_reminder_time.split(":"))
    reminder = local_now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    return local_now.weekday() < 5 and local_now >= reminder


def digest_messages(
    db: Session, settings: Settings, today: date
) -> list[tuple[VarianceStaff, EmailMessage]]:
    """The morning list of open cases, for each person not yet sent one today."""
    out = []
    for person in db.scalars(select(VarianceStaff).order_by(VarianceStaff.id)):
        if not person.active or not person.email or person.last_digest_on == today:
            continue
        cases = db.scalars(
            select(VarianceCase)
            .where(VarianceCase.staff_id == person.id, VarianceCase.status == OPEN)
            .order_by(VarianceCase.created_at, VarianceCase.id)
        ).all()
        if not cases:
            continue
        overdue = sum(1 for c in cases if is_overdue(c, today, settings))
        intro = f"You have {len(cases)} open stock variances" + (
            f", {overdue} of them overdue (red):" if overdue else ":"
        )
        out.append(
            (
                person,
                message(
                    settings,
                    person,
                    f"Open stock variances: {len(cases)}"
                    + (f" ({overdue} overdue)" if overdue else ""),
                    intro,
                    [_line(settings, c, today) for c in cases],
                ),
            )
        )
    return out


def summary(db: Session, settings: Settings, today: date) -> list[dict[str, Any]]:
    """Open, overdue and corrected cases per person (unassigned last)."""
    rows: dict[int | None, dict[str, Any]] = {}
    names = {s.id: s.name for s in db.scalars(select(VarianceStaff))}
    for case in db.scalars(select(VarianceCase)):
        row = rows.setdefault(
            case.staff_id,
            {
                "staff_id": case.staff_id,
                "name": names.get(case.staff_id or -1, "Not assigned"),
                "open": 0,
                "overdue": 0,
                "corrected": 0,
            },
        )
        if case.status == CORRECTED:
            row["corrected"] += 1
        else:
            row["open"] += 1
            row["overdue"] += int(is_overdue(case, today, settings))
    return sorted(rows.values(), key=lambda r: (r["staff_id"] is None, r["name"]))


def days_open(case: VarianceCase, today: date) -> int:
    started = case.created_at.date() if case.created_at else today
    end = case.corrected_at.date() if case.corrected_at else today
    return max((end - started).days, 0)


def working_day(day: date) -> date:
    """The day itself, or the next Monday for a weekend day."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day
