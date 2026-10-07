"""Fixture comum: aponta config.CATALOG_DB pra um arquivo sqlite temporário
e roda catalog.init_db() nele antes de cada teste, pra nenhum teste tocar no
catalog.db real de produção (que tem canais/tracks reais)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import config
from pipeline import catalog


@pytest.fixture
def temp_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CATALOG_DB", tmp_path / "test_catalog.db")
    catalog.init_db()
    return catalog
