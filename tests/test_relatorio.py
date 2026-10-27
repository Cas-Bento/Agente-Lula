import io
import json
from datetime import date

import analista
import dashboard
import notificacao
from tests.test_integridade import ob, rodar
from validacao import validar
import config


def test_validacao_basica():
    ind = config.CATALOGO["dolar"]
    assert validar(ind, ob("2026-10-26", 0.0), None, "2026-10-27")
    assert validar(ind, ob("2026-10-26", float("nan")), None, "2026-10-27")
    assert validar(ind, ob("2026-10-26", 5.4, "https://bcb.gov.br.golpe.com/x"), None, "2026-10-27")
    assert validar(ind, ob("2026-10-26", 5.4), None, "2026-10-27") is None


def test_relatorio_sem_chave_e_dashboard(ambiente):
    rodar({"selic": [ob("2026-10-26", 14.25)], "dolar": [ob("2026-10-26", 5.40)]}, "2026-10-27")
    caminho = analista.gerar(date(2026, 10, 27))
    md = open(caminho, encoding="utf-8").read()
    assert "ANTHROPIC_API_KEY ausente" in md and "Selic meta" in md and "14,25" in md
    dashboard.gerar()
    html = (ambiente / "site" / "dashboard.html").read_text(encoding="utf-8")
    assert "/*__DADOS__*/" not in html and "Nenhum dado é estimado" in html


def test_relatorio_com_ia_simulada(ambiente, monkeypatch):
    rodar({"selic": [ob("2026-10-26", 14.25)]}, "2026-10-27")
    resposta = {"content": [{"type": "text", "text": json.dumps(
        {"resumo": "Selic em 14,25%. Valor de 99,9 inventado.", "destaques": "### Positivos\nNenhum", "balanco": None})}],
        "usage": {"input_tokens": 1000, "output_tokens": 200}}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste")
    real = analista.chamar_ia
    monkeypatch.setattr(analista, "chamar_ia",
                        lambda p, c: real(p, c, _urlopen=lambda req, timeout: Resp(json.dumps(resposta).encode())))
    md = open(analista.gerar(date(2026, 10, 27)), encoding="utf-8").read()
    assert "Selic em 14,25%" in md and "99,9" in md.split("Controle de rastreabilidade")[1]


def test_falha_da_ia_nao_derruba(ambiente, monkeypatch):
    rodar({"selic": [ob("2026-10-26", 14.25)]}, "2026-10-27")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    def quebra(*a):
        raise RuntimeError("HTTP 529")
    monkeypatch.setattr(analista, "chamar_ia", quebra)
    md = open(analista.gerar(date(2026, 10, 27)), encoding="utf-8").read()
    assert "Falha na API de IA" in md and "Selic meta" in md


def test_planejar_issues_abre_e_fecha():
    saude = {"indicadores": {"dolar": {"status": "vermelho", "ultimo_erro": "HTTP 503", "falhas_consecutivas": 2,
                                       "fonte": "BCB", "sugestao": "x", "ultima_ref": "2026-10-26"},
                             "euro": {"status": "verde", "ultimo_erro": None, "falhas_consecutivas": 0}}}
    dados = {"coletas": [{"data": "2026-11-03"}], "quarentena": []}
    abertas = [{"title": "[coleta] Falha no indicador euro", "number": 7}]
    acoes = notificacao.planejar_issues(saude, dados, abertas)
    assert ("fechar", 7) == acoes[1][:2] or any(a[:2] == ("fechar", 7) for a in acoes)
    abrir = [a for a in acoes if a[0] == "abrir"][0]
    assert "critico" in abrir[3]


def test_rastreabilidade():
    payload = {"x": [14.25, 0.4433, -1.2]}
    assert analista.numeros_nao_rastreaveis("Selic de 14,25% e IPCA 0,44 e -1,2 p.p. em 2026", payload) == []
    assert analista.numeros_nao_rastreaveis("cresceu 7,77%", payload) == ["7,77"]
