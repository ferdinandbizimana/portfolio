"""Read uploaded Excel or CSV files into one Parquet file per sheet.

Values are kept as text exactly as exported (numbers in their shortest exact
form, dates as ISO 8601). Each analysis then converts the columns it needs to
the types its datasets declare, so parsing never guesses or loses data.
"""

import csv
import datetime as dt
import math
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from itertools import chain
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from python_calamine import CalamineWorkbook

BATCH_ROWS = 50_000
HEADER_SCAN_ROWS = 30
MIN_HEADER_CELLS = 2

Progress = Callable[[str], None]


class ParseError(Exception):
    pass


@dataclass
class SheetInfo:
    name: str
    header_row: int  # 1-based row number of the header in the sheet
    columns: list[str]
    row_count: int
    parquet_path: str  # relative to the output directory

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def cell_text(value: Any) -> str | None:
    """One cell as text: None for empty, numbers without float noise, dates in ISO."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ") if value.time() != dt.time() else value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def detect_format(head: bytes) -> str | None:
    if head.startswith(b"PK\x03\x04"):
        return "xlsx"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    try:
        sample = head.decode("utf-8")
    except UnicodeDecodeError:
        sample = head.decode("latin-1")
    if "\x00" not in sample and any(sep in sample for sep in (",", ";", "\t")):
        return "csv"
    return None


def _find_header(rows: list[list[str | None]]) -> int:
    """Index of the header row among the first rows.

    A candidate starts with text cells (not numbers). Of the candidates, the row
    with the most text labels wins (the earliest on a tie): title and legend lines
    above a table have fewer labels than its header, and in a two-row header the
    column row has more labels than the group row above it.
    """
    best, best_count = -1, 0
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        texts = [c for c in row if c is not None]
        if len(texts) < MIN_HEADER_CELLS or any(_is_number(c) for c in texts[:MIN_HEADER_CELLS]):
            continue
        labels = sum(1 for c in texts if not _is_number(c))
        if labels > best_count:
            best, best_count = index, labels
    if best < 0:
        raise ParseError("No header row found in the first 30 rows.")
    return best


def _is_number(text: str) -> bool:
    try:
        float(text.replace(",", ""))
    except ValueError:
        return False
    return True


def _unique_headers(raw: list[str | None]) -> list[str]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    for position, value in enumerate(raw, start=1):
        name = value or f"Column {position}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        headers.append(name)
    return headers


def _write_sheet(
    name: str, rows: Iterator[list[str | None]], out_dir: Path, file_name: str
) -> SheetInfo | None:
    head: list[list[str | None]] = []
    for row in rows:
        head.append(row)
        if len(head) >= HEADER_SCAN_ROWS:
            break
    if not any(any(c is not None for c in r) for r in head):
        return None  # empty sheet
    header_index = _find_header(head)
    headers = _unique_headers(head[header_index])
    width = len(headers)
    schema = pa.schema([pa.field(h, pa.string()) for h in headers])
    target = out_dir / file_name
    count = 0

    def batches() -> Iterator[list[list[str | None]]]:
        batch: list[list[str | None]] = []
        for row in chain(head[header_index + 1 :], rows):  # stream, never all in memory
            if not any(c is not None for c in row):
                continue  # blank line
            batch.append((row + [None] * width)[:width])
            if len(batch) >= BATCH_ROWS:
                yield batch
                batch = []
        if batch:
            yield batch

    with pq.ParquetWriter(target, schema, compression="zstd") as writer:
        for batch in batches():
            columns = list(zip(*batch, strict=True))
            writer.write_table(
                pa.table({h: pa.array(columns[i], pa.string()) for i, h in enumerate(headers)})
            )
            count += len(batch)
    return SheetInfo(name, header_index + 1, headers, count, file_name)


def _excel_rows(workbook: CalamineWorkbook, sheet: str) -> Iterator[list[str | None]]:
    for row in workbook.get_sheet_by_name(sheet).iter_rows():
        yield [cell_text(value) for value in row]


def _csv_rows(path: Path) -> Iterator[list[str | None]]:
    raw = path.read_bytes()[:65536]
    encoding = "utf-8-sig"
    try:
        raw.decode(encoding)
    except UnicodeDecodeError:
        encoding = "cp1252"
    sample = raw.decode(encoding, errors="replace")
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    with open(path, encoding=encoding, newline="") as handle:
        for row in csv.reader(handle, dialect):
            yield [cell.strip() or None for cell in row]


def parse_file(path: Path, out_dir: Path, progress: Progress | None = None) -> list[SheetInfo]:
    """Convert every non-empty sheet of an Excel or CSV file to Parquet in out_dir."""
    with open(path, "rb") as handle:
        file_format = detect_format(handle.read(4096))
    if file_format is None:
        raise ParseError("This is not an Excel (.xlsx, .xls) or CSV file.")
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets: list[SheetInfo] = []
    if file_format == "csv":
        if progress:
            progress("Reading CSV")
        info = _write_sheet("CSV", _csv_rows(path), out_dir, "sheet-1.parquet")
        if info:
            sheets.append(info)
        return sheets
    try:
        workbook = CalamineWorkbook.from_path(str(path))
    except Exception as error:  # calamine raises several error types
        raise ParseError(f"The workbook cannot be opened: {error}") from None
    skipped: list[str] = []
    for position, name in enumerate(workbook.sheet_names, start=1):
        if progress:
            progress(f"Reading sheet {name!r}")
        try:
            info = _write_sheet(
                name, _excel_rows(workbook, name), out_dir, f"sheet-{position}.parquet"
            )
        except ParseError as error:
            # Workbooks often hold sheets without a table (notes, summaries, charts):
            # those are left out; the file fails only if no sheet has a table.
            skipped.append(f"sheet {name!r}: {error}")
            continue
        if info:
            sheets.append(info)
    if not sheets:
        raise ParseError("; ".join(skipped) if skipped else "The file has no data.")
    return sheets


def read_sheet(path: Path) -> "pa.Table":
    return pq.read_table(path)
