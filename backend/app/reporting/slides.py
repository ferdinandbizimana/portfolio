"""PowerPoint decks, on an uploaded organisation template or the default layout.

With a template, its slide layouts are used ("Title Slide" for the cover and
"Title and Content" / "Title Only" for the rest, found by name, else by
position) and the template's own example slides are removed.
"""

import io
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches, Pt

from app.reporting.documents import ChartBlock, ReportDocument, TableBlock, format_value

MAX_TABLE_ROWS = 12

_CHART_TYPES = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "pie": XL_CHART_TYPE.PIE,
}


def _layout(prs: Any, name: str, fallback: int) -> Any:
    for layout in prs.slide_layouts:
        if layout.name.lower() == name.lower():
            return layout
    layouts = list(prs.slide_layouts)
    return layouts[min(fallback, len(layouts) - 1)]


def _remove_existing_slides(prs: Any) -> None:
    slide_ids = prs.slides._sldIdLst
    for slide_id in list(slide_ids):
        prs.part.drop_rel(slide_id.rId)
        slide_ids.remove(slide_id)


def _content_box(prs: Any, slide: Any) -> tuple[int, int, int, int]:
    """Area below the title for tables and charts (in EMU)."""
    top = int(Inches(1.5))
    if slide.shapes.title is not None:
        title = slide.shapes.title
        top = int(title.top + title.height + Inches(0.2))
    left = int(Inches(0.6))
    width = int(prs.slide_width - 2 * left)
    height = int(prs.slide_height - top - Inches(0.5))
    return left, top, width, height


def _title_only(prs: Any, title: str) -> Any:
    slide = prs.slides.add_slide(_layout(prs, "Title Only", 5))
    if slide.shapes.title is not None:
        slide.shapes.title.text = title
    return slide


def _table_slide(prs: Any, block: TableBlock) -> None:
    slide = _title_only(prs, block.title)
    frame = block.frame.head(min(block.max_rows or MAX_TABLE_ROWS, MAX_TABLE_ROWS))
    columns = [str(c) for c in frame.columns]
    left, top, width, _ = _content_box(prs, slide)
    rows = len(frame) + 1
    shape = slide.shapes.add_table(rows, len(columns), left, top, width, Inches(0.3) * rows)
    table = shape.table
    for j, name in enumerate(columns):
        table.cell(0, j).text = name
    for i, record in enumerate(frame.itertuples(index=False), start=1):
        for j, value in enumerate(record):
            table.cell(i, j).text = format_value(value, block.formats.get(columns[j], "text"))
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(11)


def _chart_slide(prs: Any, chart: ChartBlock) -> None:
    slide = _title_only(prs, chart.title)
    data = CategoryChartData()  # type: ignore[no-untyped-call]
    data.categories = chart.categories
    for name, values in chart.series.items():
        data.add_series(name, [float(v) for v in values])  # type: ignore[no-untyped-call]
    left, top, width, height = _content_box(prs, slide)
    graphic = slide.shapes.add_chart(_CHART_TYPES[chart.kind], left, top, width, height, data)
    plotted = graphic.chart
    plotted.has_legend = len(chart.series) > 1 or chart.kind == "pie"
    if plotted.has_legend:
        plotted.legend.position = XL_LEGEND_POSITION.BOTTOM
        plotted.legend.include_in_layout = False


def build_pptx(document: ReportDocument, template: Path | None = None) -> bytes:
    prs = Presentation(str(template)) if template else Presentation()
    if template:
        _remove_existing_slides(prs)
    else:
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    cover = prs.slides.add_slide(_layout(prs, "Title Slide", 0))
    if cover.shapes.title is not None:
        cover.shapes.title.text = document.title
    subtitle = next((p for p in cover.placeholders if p.placeholder_format.idx == 1), None)
    if subtitle is not None:
        subtitle.text = f"{document.subtitle}\n{document.date_text}"

    for section in document.sections:
        lines = [*section.paragraphs, *section.bullets]
        if lines:
            slide = prs.slides.add_slide(_layout(prs, "Title and Content", 1))
            if slide.shapes.title is not None:
                slide.shapes.title.text = section.heading
            body = next((p for p in slide.placeholders if p.placeholder_format.idx == 1), None)
            if body is not None:
                frame = body.text_frame
                frame.text = lines[0]
                for line in lines[1:]:
                    frame.add_paragraph().text = line
        for chart in section.charts:
            _chart_slide(prs, chart)
        for block in section.tables:
            _table_slide(prs, block)

    if document.checks:
        passed = sum(c.passed for c in document.checks)
        slide = prs.slides.add_slide(_layout(prs, "Title and Content", 1))
        if slide.shapes.title is not None:
            slide.shapes.title.text = "Report checks"
        body = next((p for p in slide.placeholders if p.placeholder_format.idx == 1), None)
        if body is not None:
            frame = body.text_frame
            frame.text = f"{passed} of {len(document.checks)} checks passed."
            for check in document.checks:
                frame.add_paragraph().text = (
                    f"{'Passed' if check.passed else 'Failed'}: {check.label}"
                )

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
