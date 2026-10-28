"""Fill a test installation with fake data: portfolio content, data files and runs.

    python -m app.cli seed-demo

For testing only. It refuses to run in production. Each part is skipped when
it is already there (portfolio content, the DEMO_ files), so running it twice
adds nothing new except the runs. Every file name starts with DEMO_ and every
material, plant, customer and figure is invented (see app/demo/data.py).
"""

import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analyses.registry import get_analysis
from app.content.service import get_profile
from app.datasets import ALL_SHEETS
from app.db.models import AnalysisRun, DataFile, ExperienceEntry, Project, SkillGroup
from app.demo import content
from app.demo.data import all_files
from app.ingest.parse import detect_format
from app.jobs.analysis import run_analysis
from app.jobs.ingest import parse_data_file
from app.runs import resolve_inputs
from app.storage import LocalStorage

logger = logging.getLogger(__name__)
MAX_BYTES = 200 * 2**20

# Analysis, run label, {input: file}, parameters. Inputs not listed are left empty.
RUNS: list[tuple[str, str, dict[str, str], dict[str, Any]]] = [
    (
        "closing_stock_wbs",
        "Closing stock by WBS, June 2026 (demo)",
        {
            "gl_lines": "DEMO_GL_stock_lines_Jun2026.csv",
            "scrapping": "DEMO_MB51_FY2025-26.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
            "counted": "DEMO_Closing_vs_counted_Jun2026.csv",
        },
        {"period_end": "2026-06-30"},
    ),
    (
        "rbc_accountability",
        "Programme stock Q4 FY2025/26 (demo)",
        {
            "previous_report": "DEMO_Previous_quarter_report_Mar2026.csv",
            "gl_lines": "DEMO_GL_stock_lines_Jun2026.csv",
            "scrapping": "DEMO_MB51_FY2025-26.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
            "item_categories": "DEMO_Item_categories.csv",
        },
        {"opening_date": "2026-03-31", "closing_date": "2026-06-30"},
    ),
    (
        "stock_count_reconciliation",
        "Year-end count, June 2026 (demo)",
        {
            "lines": "DEMO_Closing_vs_counted_Jun2026.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
        },
        {"count_date": "2026-06-30"},
    ),
    (
        "count_variance",
        "Variance investigation, June 2026 count (demo)",
        {
            "variance_lines": "DEMO_Count_variance_lines_Jun2026.csv",
            "closing": "DEMO_Final_closing_by_WBS_Jun2026.csv",
            "programmes": "DEMO_Previous_quarter_report_Mar2026.csv",
        },
        {"count_date": "2026-06-30"},
    ),
    (
        "stock_sufficiency_amc",
        "Stock sufficiency, June 2026 (demo)",
        {
            "weekly": "DEMO_Weekly_stock_monitoring_Jun2026.xlsx",
            "stock": "DEMO_ZSTOCKREPORT_30Jun2026.csv",
            "master": "DEMO_Material_master_MARA.csv",
            "closing": "DEMO_Final_closing_by_WBS_Jun2026.csv",
        },
        {"report_date": "2026-06-30"},
    ),
    (
        "expiry_risk",
        "Expiry risk, June 2026 (demo)",
        {
            "stock": "DEMO_ZSTOCKREPORT_30Jun2026.csv",
            "weekly": "DEMO_Weekly_stock_monitoring_Jun2026.xlsx",
            "master": "DEMO_Material_master_MARA.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
        },
        {"report_date": "2026-06-30"},
    ),
    (
        "expiry_monitoring",
        "Expiry monitoring Q4 FY2025/26 (demo)",
        {
            "opening": "DEMO_ZSTOCKREPORT_31Mar2026.csv",
            "closing": "DEMO_ZSTOCKREPORT_30Jun2026.csv",
            "movements": "DEMO_MB51_FY2025-26.csv",
            "donations": "DEMO_Donations_Apr-Jun2026.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
        },
        {"opening_date": "2026-03-31", "closing_date": "2026-06-30"},
    ),
    (
        "order_fill_rate",
        "Order fill rate Q4 FY2025/26 (demo)",
        {
            "orders": "DEMO_VA05_sales_orders_Q4.csv",
            "deliveries": "DEMO_Outbound_deliveries_Q4.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
            "movements": "DEMO_MB51_FY2025-26.csv",
        },
        {"period_start": "2026-04-01", "period_end": "2026-06-30"},
    ),
    (
        "po_follow_up",
        "Purchase orders January-June 2026 (demo)",
        {
            "orders": "DEMO_ME2M_purchase_orders_H1.csv",
            "deliveries": "DEMO_Inbound_deliveries_H1.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
        },
        {"period_start": "2026-01-01", "period_end": "2026-06-30", "report_date": "2026-06-30"},
    ),
    (
        "stock_in_transit",
        "Stock in transit, 30 June 2026 (demo)",
        {
            "in_transit": "DEMO_MB5T_stock_in_transit_Jun2026.csv",
            "movements": "DEMO_MB51_FY2025-26.csv",
            "plants": "DEMO_OX10_plants_and_customers.csv",
        },
        {"report_date": "2026-06-30"},
    ),
    (
        "warehouse_activity",
        "Warehouse activity Q4 FY2025/26 (demo)",
        {
            "tasks": "DEMO_EWM_warehouse_tasks_Q4.csv",
            "deliveries": "DEMO_Outbound_deliveries_Q4.csv",
        },
        {"report_date": "2026-06-30"},
    ),
    (
        "picker_accuracy",
        "Picker accuracy, June 2026 (demo)",
        {
            "daily": "DEMO_Picking_register_Jun2026.xlsx",
            "orders": "DEMO_Picking_register_Jun2026.xlsx",
        },
        {},
    ),
    (
        "spot_check_accuracy",
        "Spot check 17 September 2026 (demo)",
        {
            "spot_check": "DEMO_Spot_check_17Sep2026.csv",
            "previous": "DEMO_Spot_check_10Sep2026.csv",
            "bins": "DEMO_Storage_bins_responsible.csv",
        },
        {"check_date": "2026-09-17", "previous_label": "10 September"},
    ),
    (
        "demo_stock_summary",
        "Stock value by plant (demo)",
        {"stock": "DEMO_Stock_balance.csv"},
        {"period_end": "2026-06-30"},
    ),
]


@dataclass
class SeedReport:
    content: str = ""
    files: list[str] = field(default_factory=list)
    runs: list[tuple[str, str, str]] = field(default_factory=list)  # label, status, message
    follow_ups: list[str] = field(default_factory=list)


def _bytes(name: str, sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    if name.endswith(".xlsx"):
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for sheet, frame in sheets.items():
                frame.to_excel(writer, sheet_name=sheet[:31], index=False)
    else:
        [frame] = sheets.values()
        buffer.write(frame.to_csv(index=False).encode("utf-8"))
    return buffer.getvalue()


def seed_content(db: Session) -> str:
    """Sample profile, experience, skills and projects, when the portfolio is empty."""
    has_content = (
        db.scalar(select(func.count()).select_from(ExperienceEntry))
        or db.scalar(select(func.count()).select_from(SkillGroup))
        or db.scalar(select(func.count()).select_from(Project))
    )
    if has_content:
        return "kept (the portfolio already has content)"
    profile = get_profile(db)
    for key, value in content.PROFILE.items():
        setattr(profile, key, value)
    for order, entry in enumerate(content.EXPERIENCE):
        db.add(ExperienceEntry(**entry, sort_order=order))
    for order, group in enumerate(content.SKILLS):
        db.add(SkillGroup(**group, sort_order=order))
    for order, project in enumerate(content.PROJECTS):
        db.add(Project(**project, sort_order=order))
    db.commit()
    return "sample profile, experience, skills and projects added"


def seed_files(db: Session, storage: LocalStorage) -> dict[str, DataFile]:
    """The DEMO_ files, stored and read like uploads. Files already there are reused."""
    found: dict[str, DataFile] = {}
    for name, sheets in all_files().items():
        existing = db.scalar(
            select(DataFile)
            .where(DataFile.filename == name, DataFile.status == "ready")
            .order_by(DataFile.id.desc())
        )
        if existing is not None:
            found[name] = existing
            continue
        payload = _bytes(name, sheets)
        if detect_format(payload[:4096]) is None:
            raise RuntimeError(f"{name} is not an Excel or CSV file.")
        key, size, sha256 = storage.save(io.BytesIO(payload), MAX_BYTES, "data")
        data_file = DataFile(
            filename=name,
            size_bytes=size,
            sha256=sha256,
            storage_key=key,
            status="received",
            message="Waiting to be read",
            sheets=[],
            source="demo",
        )
        db.add(data_file)
        db.commit()
        parse_data_file(data_file.id)
        db.refresh(data_file)
        found[name] = data_file
    return found


def _sheet(data_file: DataFile, dataset: str) -> str | None:
    for sheet in data_file.sheets:
        if any(m["dataset"] == dataset for m in sheet.get("matches", [])):
            return str(sheet["name"])
    return None


def seed_runs(
    db: Session,
    files: dict[str, DataFile],
    execute: Callable[[int], None] = run_analysis,
) -> list[tuple[str, str, str]]:
    results = []
    for key, label, chosen, parameters in RUNS:
        analysis = get_analysis(key)
        if analysis is None:
            continue
        datasets = {spec.key: spec for spec in analysis.inputs}
        choices: dict[str, tuple[int, str]] = {}
        for input_key, filename in chosen.items():
            data_file, spec = files.get(filename), datasets.get(input_key)
            if data_file is None or spec is None or data_file.status != "ready":
                continue
            sheet = ALL_SHEETS if spec.all_sheets else _sheet(data_file, spec.dataset)
            if sheet is not None:
                choices[input_key] = (data_file.id, sheet)
        inputs, errors = resolve_inputs(db, analysis, choices)
        if errors:
            results.append((label, "not started", " ".join(errors)))
            continue
        params = analysis.Parameters.model_validate(parameters)
        run = AnalysisRun(
            analysis_key=key,
            analysis_version=analysis.version,
            label=label,
            parameters=params.model_dump(mode="json"),
            inputs=inputs,
            status="queued",
            message="Waiting for the worker",
        )
        db.add(run)
        db.commit()
        execute(run.id)
        db.refresh(run)
        failed = [c["label"] for c in run.checks if not c.get("passed")]
        message = (
            run.message
            if run.status != "succeeded"
            else (
                f"{len(run.checks) - len(failed)} of {len(run.checks)} checks passed"
                + (f"; failed: {', '.join(failed)}" if failed else "")
            )
        )
        results.append((label, run.status, message))
    return results


def seed_follow_ups(db: Session, storage: LocalStorage, files: dict[str, DataFile]) -> list[str]:
    """Stock variances from the spot checks (with the bin list) and the expiry follow-up."""
    from app import expiry, variances
    from app.core.config import get_settings
    from app.db.models import VarianceCase
    from app.jobs.variances import read_dataset

    notes: list[str] = []
    if db.scalar(select(func.count()).select_from(VarianceCase)):
        notes.append("Stock variances: kept (cases already there)")
    else:
        _, bins, _ = read_dataset(
            storage, files["DEMO_Storage_bins_responsible.csv"], ["bin_owners"]
        )
        imported = variances.import_bin_list(db, bins, get_settings())
        created = 0
        for name in ("DEMO_Spot_check_10Sep2026.csv", "DEMO_Spot_check_17Sep2026.csv"):
            data_file = files[name]
            _, frame, _ = read_dataset(storage, data_file, ["spot_check"])
            result = variances.import_cases(
                db,
                variances.SPOT_CHECK,
                frame,
                data_file.id,
                data_file.sha256,
                data_file.filename,
            )
            created += result.created
        db.commit()
        notes.append(f"Stock variances: {imported.bins} bins, {created} variance cases")
    run = db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.analysis_key == "expiry_monitoring", AnalysisRun.status == "succeeded")
        .order_by(AnalysisRun.id.desc())
    )
    if run is not None:
        review = expiry.ensure_review(db, storage, run)
        db.commit()
        notes.append(f"Expiry follow-up: prepared for run {run.id} (review {review.id})")
    return notes


def seed(db: Session, storage: LocalStorage, runs: bool = True) -> SeedReport:
    report = SeedReport()
    report.content = seed_content(db)
    files = seed_files(db, storage)
    report.files = [
        f"{name}: {f.status}" + (f" ({f.message})" if f.status != "ready" else "")
        for name, f in files.items()
    ]
    if runs:
        report.runs = seed_runs(db, files)
        report.follow_ups = seed_follow_ups(db, storage, files)
    return report
