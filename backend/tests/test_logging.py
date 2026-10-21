import json
import logging
import logging.config
import os

import pytest

from tests.conftest import BACKEND_DIR


def test_uvicorn_logs_are_json(capsys: pytest.CaptureFixture[str]) -> None:
    with open(os.path.join(BACKEND_DIR, "logging.json")) as file:
        logging.config.dictConfig(json.load(file))

    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /api/health HTTP/1.1" 200')

    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["logger"] == "uvicorn.access"
    assert record["level"] == "INFO"
    assert "GET /api/health" in record["message"]
