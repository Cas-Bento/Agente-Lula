import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    import analista
    import coletor
    import dashboard
    monkeypatch.setattr(coletor, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(coletor, "MANUAL_CSV", str(tmp_path / "manual.csv"))
    monkeypatch.setattr(analista, "DIR_REL", str(tmp_path / "relatorios"))
    monkeypatch.setattr(dashboard, "DIR_REL", str(tmp_path / "relatorios"))
    monkeypatch.setattr(dashboard, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(dashboard, "SITE", str(tmp_path / "site"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def fonte_falsa(respostas):
    """respostas: {id: lista de obs | Exception}. Indicadores ausentes retornam lista vazia."""
    def fn(ind, primeira, hoje):
        r = respostas.get(ind["id"], [])
        if isinstance(r, Exception):
            raise r
        return [dict(o) for o in r]
    return fn
