"""Finds every analysis package under app/analyses.

An analysis package defines `ANALYSIS = MyAnalysis()` in its __init__.py.
Adding a package is enough to make it available; nothing else changes.
"""

import importlib
import pkgutil
from functools import cache

import app.analyses as package
from app.analyses.base import Analysis

_NOT_ANALYSES = {"base", "dashboard", "registry", "common"}


@cache
def all_analyses() -> dict[str, Analysis]:
    found: dict[str, Analysis] = {}
    for module in pkgutil.iter_modules(package.__path__):
        if module.name in _NOT_ANALYSES or not module.ispkg:
            continue
        loaded = importlib.import_module(f"{package.__name__}.{module.name}")
        analysis = getattr(loaded, "ANALYSIS", None)
        if not isinstance(analysis, Analysis):
            raise TypeError(f"app/analyses/{module.name} does not define ANALYSIS.")
        if analysis.key in found:
            raise ValueError(f"Two analyses use the key {analysis.key!r}.")
        found[analysis.key] = analysis
    return dict(sorted(found.items(), key=lambda item: item[1].title))


def get_analysis(key: str) -> Analysis | None:
    return all_analyses().get(key)
