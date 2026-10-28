"""Demo data: every analysis runs on the fake files and every self-check passes."""

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import cli
from app.db.models import AnalysisRun, DataFile, Project, VarianceCase
from app.db.session import get_engine, get_sessionmaker
from app.demo.data import all_files
from app.demo.seed import RUNS, seed
from app.storage import LocalStorage


@pytest.fixture(autouse=True)
def _uses_test_database_and_storage(
    engine: Engine, storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    monkeypatch.setattr("app.db.session.get_engine", lambda: engine)
    monkeypatch.setattr("app.storage.get_storage", lambda: storage)


def test_files_are_fake_and_the_same_every_time() -> None:
    first, second = all_files(), all_files()
    assert list(first) == list(second)
    for name, sheets in first.items():
        assert name.startswith("DEMO_")
        for sheet, frame in sheets.items():
            assert frame.equals(second[name][sheet]), (name, sheet)
            assert len(frame) > 0, (name, sheet)


def test_seed_runs_every_analysis_with_all_checks_passed(
    db: Session, storage: LocalStorage
) -> None:
    report = seed(db, storage)
    assert report.content.startswith("sample profile")
    assert all(line.endswith("ready") for line in report.files), report.files
    assert len(report.runs) == len(RUNS)
    for label, status, message in report.runs:
        assert status == "succeeded", (label, message)
        assert "failed" not in message, (label, message)
    assert db.scalar(select(func.count()).select_from(Project)) == 3
    assert (db.scalar(select(func.count()).select_from(VarianceCase)) or 0) > 0
    assert any(note.startswith("Expiry follow-up") for note in report.follow_ups)

    # A second seed keeps the content and the files, and only adds runs.
    again = seed(db, storage, runs=False)
    assert again.content.startswith("kept")
    assert db.scalar(select(func.count()).select_from(DataFile)) == len(all_files())
    assert db.scalar(select(func.count()).select_from(AnalysisRun)) == len(RUNS)


def test_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert cli.main(["seed-demo"]) == 1
    finally:
        get_settings.cache_clear()
