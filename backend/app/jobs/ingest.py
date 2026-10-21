"""Background job: read an uploaded file into Parquet sheets and recognise its datasets."""

import logging

from app import storage as storage_module
from app.datasets import match_sheet
from app.db.models import DataFile
from app.db.session import session_scope
from app.ingest.parse import ParseError, parse_file

logger = logging.getLogger(__name__)


def parsed_dir_key(data_file: DataFile) -> str:
    return f"{data_file.storage_key}.parsed"


def parse_data_file(data_file_id: int) -> None:
    storage = storage_module.get_storage()
    with session_scope() as db:
        data_file = db.get(DataFile, data_file_id)
        if data_file is None:
            return
        data_file.status = "parsing"
        data_file.message = "Reading the file"
        db.commit()

        def progress(text: str) -> None:
            data_file.message = text
            db.commit()

        try:
            sheets = parse_file(
                storage.path(data_file.storage_key),
                storage.path(parsed_dir_key(data_file)),
                progress,
            )
        except ParseError as error:
            data_file.status = "failed"
            data_file.message = str(error)
            db.commit()
            return
        except Exception:
            logger.exception("Parsing data file %s failed", data_file_id)
            data_file.status = "failed"
            data_file.message = "The file could not be read. It may be damaged."
            db.commit()
            return

        data_file.sheets = [
            {
                **sheet.as_dict(),
                "matches": [
                    {"dataset": m.dataset, "title": m.title}
                    for m in match_sheet(sheet.columns, sheet.name)
                ],
            }
            for sheet in sheets
        ]
        data_file.status = "ready"
        recognised = sum(1 for s in data_file.sheets if s["matches"])
        data_file.message = (
            f"{len(sheets)} sheet(s) read; {recognised} recognised as a known dataset."
        )
        db.commit()
