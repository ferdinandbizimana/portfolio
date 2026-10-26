"""Database models. Alembic migrations in alembic/versions must match these."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    """A login session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class AuditEvent(Base):
    """An important action: logins, uploads, runs, publishing and so on."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)


class StoredFile(Base):
    """A file kept in storage (photo, CV, images). Only `public` files are served to visitors."""

    __tablename__ = "stored_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    """The portfolio owner's profile. There is exactly one row (id = 1)."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    summary_md: Mapped[str] = mapped_column(Text, default="")
    about_md: Mapped[str] = mapped_column(Text, default="")
    linkedin_url: Mapped[str] = mapped_column(String(300), default="")
    github_url: Mapped[str] = mapped_column(String(300), default="")
    photo_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    cv_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExperienceEntry(Base):
    __tablename__ = "experience_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(200))
    organisation: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(120), default="")
    start_month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    end_month: Mapped[str | None] = mapped_column(String(7))  # None = current role
    description_md: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class SkillGroup(Base):
    __tablename__ = "skill_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    items: Mapped[list[str]] = mapped_column(JsonDict, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Project(Base):
    """A project or case study. Only published projects are visible to visitors."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JsonDict, default=list)
    cover_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UploadSession(Base):
    """A chunked upload in progress. Chunks are kept in storage until completed."""

    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    chunk_size: Mapped[int] = mapped_column(Integer)
    received_chunks: Mapped[list[int]] = mapped_column(JsonDict, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataFile(Base):
    """An uploaded data file (Excel or CSV export). Never public."""

    __tablename__ = "data_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    # received -> parsing -> ready | failed
    status: Mapped[str] = mapped_column(String(16), default="received")
    message: Mapped[str] = mapped_column(Text, default="")
    # [{name, header_row, columns, row_count, parquet_path, matches: [{dataset, title}]}]
    sheets: Mapped[list[dict[str, Any]]] = mapped_column(JsonDict, default=list)
    source: Mapped[str] = mapped_column(String(32), default="upload")
    # Shared folder only: path inside the folder, and its size and modification
    # time when it was picked up (to notice a changed file without re-reading it).
    source_path: Mapped[str | None] = mapped_column(String(1024), index=True)
    source_mtime_ns: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRun(Base):
    """One execution of an analysis on chosen input files."""

    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_key: Mapped[str] = mapped_column(String(64), index=True)
    analysis_version: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(200), default="")
    parameters: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    # {input_key: {data_file_id, sheet, sha256, filename}}
    inputs: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    # queued -> running -> succeeded | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    errors: Mapped[list[str]] = mapped_column(JsonDict, default=list)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JsonDict, default=list)
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(JsonDict, default=list)
    dashboard: Mapped[dict[str, Any] | None] = mapped_column(JsonDict)
    # [{key, title, kind, filename, storage_key, size_bytes}]
    reports: Mapped[list[dict[str, Any]]] = mapped_column(JsonDict, default=list)
    result_hash: Mapped[str] = mapped_column(String(64), default="")
    job_id: Mapped[str] = mapped_column(String(64), default="")
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportTemplate(Base):
    """An organisation template (Word or PowerPoint) used for generated reports."""

    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # docx | pptx
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Publication(Base):
    """A frozen copy of a run's dashboard, shown to visitors.

    Visitors only ever see `snapshot`; nothing here points them to uploads or
    run data. `visibility`: private (only you), secret (anyone with the link),
    public (listed on the dashboards page).
    """

    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), index=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    secret_token: Mapped[str] = mapped_column(String(64), unique=True)
    visibility: Mapped[str] = mapped_column(String(8), default="private", index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    detail_level: Mapped[str] = mapped_column(String(8), default="summary")
    include_checks: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JsonDict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Schedule(Base):
    """Runs an analysis automatically on the newest files from the shared folder."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    analysis_key: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # daily: at `run_time` on `weekdays`; new_files: as soon as new input files arrive
    trigger: Mapped[str] = mapped_column(String(16), default="daily")
    run_time: Mapped[str] = mapped_column(String(5), default="06:00")  # HH:MM, settings.timezone
    weekdays: Mapped[list[int]] = mapped_column(JsonDict, default=lambda: [0, 1, 2, 3, 4, 5, 6])
    # {input_key: {pattern: "MB5B*.xlsx", sheet: ""}}; empty sheet = the recognised one
    inputs: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    # Parameter values; a date may be a rule such as "previous_month_end" (see scheduling.py)
    parameters: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    only_when_changed: Mapped[bool] = mapped_column(Boolean, default=True)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_on: Mapped[date | None] = mapped_column(Date)
    last_signature: Mapped[str] = mapped_column(String(64), default="")
    last_message: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VarianceStaff(Base):
    """A warehouse staff member responsible for storage bins (spot-check follow-up)."""

    __tablename__ = "variance_staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_digest_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BinOwner(Base):
    """Who corrects the variances found in a storage bin."""

    __tablename__ = "bin_owners"

    storage_bin: Mapped[str] = mapped_column(String(40), primary_key=True)
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("variance_staff.id", ondelete="SET NULL"), index=True
    )
    storage_type: Mapped[str] = mapped_column(String(20), default="")
    storage_section: Mapped[str] = mapped_column(String(20), default="")


class VarianceCase(Base):
    """A stock variance to verify and correct (spot check, missed at picking, inventory).

    The responsible person closes it through a secure link (a random token, like a
    publication's secret link). The link is repeated in the daily list, so the token
    itself is kept; the database is never public.
    """

    __tablename__ = "variance_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # spot_check | picking | physical_inventory
    source: Mapped[str] = mapped_column(String(24), index=True)
    # The same line imported twice is one case.
    dedup_key: Mapped[str] = mapped_column(String(300), unique=True)
    data_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_files.id", ondelete="SET NULL")
    )
    reference: Mapped[str] = mapped_column(String(100), default="")  # e.g. PI document / item
    storage_bin: Mapped[str] = mapped_column(String(40), index=True)
    product: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(String(255), default="")
    batch: Mapped[str] = mapped_column(String(40), default="")
    system_qty: Mapped[float | None] = mapped_column()
    counted_qty: Mapped[float | None] = mapped_column()
    difference_qty: Mapped[float] = mapped_column(default=0.0)
    found_on: Mapped[date | None] = mapped_column(Date)
    reported_by: Mapped[str] = mapped_column(String(200), default="")
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("variance_staff.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | corrected
    reason: Mapped[str] = mapped_column(Text, default="")
    responsible_unit: Mapped[str] = mapped_column(String(40), default="")
    action_taken: Mapped[str] = mapped_column(Text, default="")
    corrected_by: Mapped[str] = mapped_column(String(200), default="")
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
