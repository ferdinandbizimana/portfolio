"""The contract every analysis follows.

An analysis is a pure, deterministic function: named input DataFrames plus
parameters in, an AnalysisResult out. It never reads files, the database, the
network or the clock. The engine (app/jobs/analysis.py) loads and validates
the inputs, calls `compute`, stores the result and asks the analysis for its
reports.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

import pandas as pd
from pydantic import BaseModel

from app.analyses.dashboard import CheckOut, Dashboard, Kpi
from app.reporting.documents import ReportFile, Templates


@dataclass(frozen=True)
class InputSpec:
    key: str  # name the analysis uses for this input
    dataset: str  # dataset key (app/datasets)
    label: str  # shown in the form, e.g. "Stock balance at period end"
    required: bool = True
    # Take every sheet of the chosen file that is recognised as the dataset (for
    # workbooks with one sheet per programme); a "Sheet" column says which.
    all_sheets: bool = False


@dataclass
class Check:
    """A self-check: expected and actual must agree within the tolerance."""

    key: str
    label: str
    expected: float
    actual: float
    tolerance: float = 0.5
    description: str = ""

    @property
    def passed(self) -> bool:
        return abs(self.actual - self.expected) <= self.tolerance

    def out(self) -> CheckOut:
        return CheckOut(
            key=self.key,
            label=self.label,
            expected=round(float(self.expected), 6),
            actual=round(float(self.actual), 6),
            tolerance=self.tolerance,
            passed=self.passed,
            description=self.description,
        )


@dataclass
class AnalysisResult:
    tables: dict[str, pd.DataFrame]
    metrics: list[Kpi]
    checks: list[Check]
    dashboard: Dashboard
    # Free-form values the report builders need (already computed, deterministic).
    extras: dict[str, object] = field(default_factory=dict)


class Analysis(ABC):
    key: ClassVar[str]
    title: ClassVar[str]
    version: ClassVar[str]
    description: ClassVar[str]
    inputs: ClassVar[tuple[InputSpec, ...]]
    Parameters: ClassVar[type[BaseModel]]
    demo: ClassVar[bool] = False

    @abstractmethod
    def compute(self, data: dict[str, pd.DataFrame], params: BaseModel) -> AnalysisResult:
        """Pure calculation. Same inputs and parameters must give the same result."""

    @abstractmethod
    def reports(
        self, result: AnalysisResult, params: BaseModel, templates: Templates
    ) -> list[ReportFile]:
        """Excel, Word and PowerPoint files for this result."""
