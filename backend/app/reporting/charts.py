"""Charts as images (for Word), in the RMS brand colours.

PowerPoint gets native, editable charts (slides.py); Word cannot hold those, so
the same ChartBlock is drawn here as a PNG.
"""

import io
from functools import cache

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

from app.reporting import brand
from app.reporting.documents import ChartBlock, ValueFormat

MAX_CATEGORIES = 15


def short_number(value: float, value_format: ValueFormat = "number") -> str:
    """1,234,567 -> "1.23M"; shares as percentages."""
    if value_format == "percent":
        return f"{value * 100:.1f}%"
    size = abs(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if size >= limit:
            return f"{value / limit:.3g}{suffix}"
    return f"{value:,.0f}" if size >= 10 or value == int(value) else f"{value:.1f}"


@cache
def _font() -> str:
    """Open Sans when the machine has it, else matplotlib's own font (no warnings)."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    return brand.BODY_FONT if brand.BODY_FONT in names else "DejaVu Sans"


def _hex(colour: str) -> str:
    return f"#{colour}"


def chart_png(chart: ChartBlock, width: float = 6.5, height: float = 3.2) -> bytes:
    categories = [str(c) for c in chart.categories[:MAX_CATEGORIES]]
    series = {
        name: [float(v) for v in values[:MAX_CATEGORIES]] for name, values in chart.series.items()
    }
    plt.rcParams.update(
        {
            "font.family": _font(),
            "font.size": 8,
            "axes.edgecolor": _hex(brand.LINE),
            "axes.labelcolor": _hex(brand.INK),
            "xtick.color": _hex(brand.MUTED),
            "ytick.color": _hex(brand.MUTED),
        }
    )
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    colours = [_hex(c) for c in brand.SERIES]
    fmt = FuncFormatter(lambda v, _pos: short_number(v, chart.value_format))
    n = max(len(series), 1)
    positions = list(range(len(categories)))
    if chart.kind == "pie":
        first = next(iter(series.values()), [])
        ax.pie(first, labels=categories, colors=colours[: len(first)], textprops={"fontsize": 7})
        ax.axis("equal")
    elif chart.kind == "line":
        for k, (name, values) in enumerate(series.items()):
            ax.plot(categories, values, marker="o", color=colours[k % len(colours)], label=name)
            if chart.labels:
                for x, y in zip(categories, values, strict=False):
                    ax.annotate(
                        short_number(y, chart.value_format),
                        (x, y),
                        textcoords="offset points",
                        xytext=(0, 5),
                        ha="center",
                        fontsize=6,
                    )
        ax.yaxis.set_major_formatter(fmt)
    elif chart.kind == "bar":  # horizontal, largest on top
        ys = positions[::-1]
        bar = 0.8 / n
        for k, (name, values) in enumerate(series.items()):
            offset = [y + (n - 1 - k) * bar - 0.4 + bar / 2 for y in ys]
            bars = ax.barh(offset, values, height=bar, color=colours[k % len(colours)], label=name)
            if chart.labels:
                ax.bar_label(
                    bars,
                    labels=[short_number(v, chart.value_format) for v in values],
                    fontsize=6,
                    padding=2,
                )
        ax.set_yticks(ys, categories)
        ax.xaxis.set_major_formatter(fmt)
    else:  # column or stacked
        width_each = 0.8 if chart.kind == "stacked" else 0.8 / n
        bottoms = [0.0] * len(categories)
        for k, (name, values) in enumerate(series.items()):
            if chart.kind == "stacked":
                xs = [float(p) for p in positions]
            else:
                xs = [p - 0.4 + width_each * (k + 0.5) for p in positions]
            bars = ax.bar(
                xs,
                values,
                width=width_each,
                bottom=bottoms if chart.kind == "stacked" else None,
                color=colours[k % len(colours)],
                label=name,
            )
            if chart.kind == "stacked":
                bottoms = [b + v for b, v in zip(bottoms, values, strict=True)]
            elif chart.labels:
                ax.bar_label(
                    bars,
                    labels=[short_number(v, chart.value_format) for v in values],
                    fontsize=6,
                    padding=2,
                )
        ax.set_xticks(
            positions,
            categories,
            rotation=30 if len(categories) > 6 else 0,
            ha="right" if len(categories) > 6 else "center",
        )
        ax.yaxis.set_major_formatter(fmt)
    if chart.kind != "pie":
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x" if chart.kind == "bar" else "y", color=_hex(brand.LINE), linewidth=0.6)
        ax.set_axisbelow(True)
        if len(series) > 1:
            ax.legend(
                frameon=False,
                fontsize=7,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.18),
                ncol=min(len(series), 4),
            )
    ax.set_title(chart.title, loc="left", fontsize=9, fontweight="bold", color=_hex(brand.BLUE))
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", metadata={"Software": None})
    plt.close(fig)
    return buffer.getvalue()
