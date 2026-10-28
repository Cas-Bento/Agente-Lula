"""Parsers dos indicadores incluídos em 28/10/2026 (amostras reproduzem o layout real conferido)."""
import base64
import json
from datetime import date, datetime

import pytest

import config
from coletores import anp, b3, inpe_deter, tesouro_rtn
from coletores.util import LayoutErro
from validacao import dominio_oficial


# ---------------------------------------------------------------- ANP
LINHAS_ANP = [
    ("AGÊNCIA NACIONAL DO PETRÓLEO, GÁS NATURAL E BIOCOMBUSTÍVEIS - ANP",),
    ("Atualmente, o produto 'óleo diesel' se refere ao óleo diesel B S500 comum.",),
    ("DATA INICIAL", "DATA FINAL", "PRODUTO", "NÚMERO DE POSTOS PESQUISADOS", "UNIDADE DE MEDIDA",
     "PREÇO MÉDIO REVENDA", "DESVIO PADRÃO REVENDA"),
    (46306, 46312, "GASOLINA COMUM", 4526, "R$/l", 6.53, 0.403),
    (46306, 46312, "OLEO DIESEL S10", 3141, "R$/l", 7.34, 0.3),
    (datetime(2026, 10, 18), datetime(2026, 10, 24), "GASOLINA COMUM", 4600, "R$/l", 6.49, 0.4),
    (datetime(2026, 10, 18), datetime(2026, 10, 24), "ETANOL HIDRATADO", 3929, "R$/l", 4.11, 0.4),
    (datetime(2026, 10, 18), datetime(2026, 10, 24), "GLP", 3330, "R$/13kg", 114.98, 12),
]


def test_anp():
    obs = anp.parse_linhas(LINHAS_ANP, "GASOLINA COMUM", anp.URL)
    assert [(o["ref"], o["valor"]) for o in obs] == [("2026-10-17", 6.53), ("2026-10-24", 6.49)]
    assert anp.parse_linhas(LINHAS_ANP, "OLEO DIESEL S10", anp.URL)[0]["valor"] == 7.34
    with pytest.raises(LayoutErro):
        anp.parse_linhas(LINHAS_ANP, "QUEROSENE", anp.URL)
    with pytest.raises(LayoutErro):
        anp.parse_linhas([l for l in LINHAS_ANP if "PRODUTO" not in l], "GASOLINA COMUM", anp.URL)


def test_anp_baixa_uma_vez():
    anp._cache.clear()
    chamadas = []
    orig = anp.linhas_planilha
    anp.linhas_planilha = lambda c: LINHAS_ANP
    try:
        get = lambda u, timeout=None: chamadas.append(u) or b"x"
        anp.coletar({"params": {"produto": "GASOLINA COMUM"}}, False, date(2026, 10, 28), _get=get)
        anp.coletar({"params": {"produto": "ETANOL HIDRATADO"}}, False, date(2026, 10, 28), _get=get)
    finally:
        anp.linhas_planilha = orig
        anp._cache.clear()
    assert len(chamadas) == 1


# ---------------------------------------------------------------- INPE DETER
def test_deter_soma_e_meses():
    csv_txt = ("FID,classname,view_date,areamunkm\r\n"
               "deter_amz.1_curr,DESMATAMENTO_CR,2026-09-01,0.0954\r\n"
               "deter_amz.2_curr,MINERACAO,2026-09-03,4.1624\r\n")
    assert inpe_deter.somar_csv(csv_txt) == pytest.approx(4.2578)
    with pytest.raises(LayoutErro):
        inpe_deter.somar_csv(csv_txt.replace("MINERACAO", "DEGRADACAO"))
    with pytest.raises(LayoutErro):
        inpe_deter.somar_csv('<?xml version="1.0"?><ows:ExceptionReport>erro')
    # em 28/10 setembro já fechou há 28 dias; outubro ainda não entra
    assert inpe_deter.meses_fechados(date(2026, 10, 28), 3) == [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    assert inpe_deter.meses_fechados(date(2026, 10, 10), 1) == [date(2026, 8, 1)]
    u = inpe_deter.url_mes(date(2026, 9, 1), date(2026, 10, 1))
    assert "typeName=deter-amz:deter_amz" in u and "2026-09-01" in u and dominio_oficial(u)


# ---------------------------------------------------------------- B3
def test_b3():
    u = b3.url_ano("IBOV", 2026)
    assert json.loads(base64.b64decode(u.rsplit("/", 1)[1])) == {"index": "IBOV", "language": "pt-br", "year": "2026"}
    payload = {"results": [{"day": 23, "rateValue10": "205.082,56", "rateValue11": None},
                           {"day": 26, "rateValue10": "176.608,23"},
                           {"day": 31, "rateValue10": None}]}
    obs = b3.parse(payload, 2026, u)
    assert [(o["ref"], o["valor"]) for o in obs] == [("2026-10-23", 205082.56), ("2026-10-26", 176608.23)]
    assert dominio_oficial(u)
    with pytest.raises(LayoutErro):
        b3.parse({"x": 1}, 2026, u)
    with pytest.raises(LayoutErro):
        b3.parse({"results": [{"day": 31, "rateValue2": "1,00"}]}, 2026, u)


def test_b3_queda_de_14pct_nao_vai_para_quarentena():
    from validacao import validar
    ind = config.CATALOGO["ibovespa"]
    ant = {"ref": "2026-10-23", "valor": 205082.56}
    assert validar(ind, {"ref": "2026-10-26", "valor": 176608.23, "url": b3.url_ano("IBOV", 2026)}, ant, "2026-10-28") is None


# ---------------------------------------------------------------- Tesouro RTN
def _rtn(n_meses=30, faltando=None):
    meses = [date(2024 + (i // 12), i % 12 + 1, 1) for i in range(n_meses)]
    cab = ("Código", "Discriminação") + tuple(meses)
    valores = tuple(None if (faltando is not None and i == faltando) else 200_000.0 + i * 1000 for i in range(n_meses))
    return [("Tabela 1.1 - Resultado Primário do Governo Central - R$ milhões",), cab,
            (1, "1. RECEITA TOTAL") + valores, (1.1, "1.1 - Receita Administrada pela RFB") + valores]


def test_rtn_acumulado_12m():
    obs = tesouro_rtn.parse_linhas(_rtn(), "Receita Total", "https://www.tesourotransparente.gov.br/x")
    assert obs[0]["ref"] == "2024-12-01" and obs[-1]["ref"] == "2026-06-01" and len(obs) == 19
    assert obs[0]["valor"] == pytest.approx(sum(200_000.0 + i * 1000 for i in range(12)) / 1000)
    # mês faltando: as janelas de 12 meses que o incluem não são calculadas
    com_buraco = tesouro_rtn.parse_linhas(_rtn(faltando=15), "Receita Total", "u")
    assert "2025-04-01" not in [o["ref"] for o in com_buraco] and "2026-04-01" in [o["ref"] for o in com_buraco]
    with pytest.raises(LayoutErro):
        tesouro_rtn.parse_linhas(_rtn(), "Receita Inexistente", "u")
    assert tesouro_rtn.mes_cabecalho("jan/97") == date(1997, 1, 1)
    assert tesouro_rtn.mes_cabecalho(46204) == date(2026, 7, 1)


def test_rtn_layout_real():
    """Reproduz a planilha de jul/2026: meses como número de série, rótulo com nota "1/"."""
    seriais = [45870, 45901, 45931, 45962, 45992, 46023, 46054, 46082, 46113, 46143, 46174, 46204]
    mensal = [219614.37, 216368.82, 268185.67, 218448.44, 312023.27, 322088.83,
              219030.45, 235025.65, 279491.45, 256223.38, 251923.54, 275883.96]
    antes = [(date(2024 + (m > 12), (m - 1) % 12 + 1, 1) - date(1899, 12, 30)).days for m in range(8, 20)]  # ago/24 a jul/25
    linhas = [("Voltar",), ("Tabela 1.1. Resultado Primário do Governo Central - Brasil - Mensal - Resumida",),
              ("R$ Milhões - Valores Correntes ",), (None,),
              ("Discriminação",) + tuple(antes) + tuple(seriais),
              ("1. RECEITA TOTAL 1/",) + (200000.0,) * 12 + tuple(mensal),
              ("1.1 -  Receita Administrada pela RFB",) + (1.0,) * 24]
    obs = tesouro_rtn.parse_linhas(linhas, "Receita Total", "u")
    assert obs[-1]["ref"] == "2026-07-01" and obs[-1]["valor"] == pytest.approx(sum(mensal) / 1000)


def test_catalogo_novos():
    for id_ in ("arrecadacao", "desmat_deter", "ibovespa", "gasolina", "etanol", "diesel"):
        ind = config.CATALOGO[id_]
        assert ind["ativo"] and ind["eixo"] in config.EIXOS


def test_ponta_a_ponta_novos(ambiente):
    """Coleta simulada -> linha de base -> relatório -> dashboard com os novos indicadores."""
    from datetime import date as d
    import analista
    import coletor
    import dashboard
    from tests.conftest import fonte_falsa
    U_ANP, U_B3 = anp.URL, b3.url_ano("IBOV", 2026)
    U_DET = inpe_deter.url_mes(d(2026, 9, 1), d(2026, 10, 1))
    resp = {
        "gasolina": [{"ref": "2026-10-24", "valor": 6.49, "url": U_ANP}, {"ref": "2026-10-17", "valor": 6.53, "url": U_ANP}],
        "ibovespa": [{"ref": "2026-10-23", "valor": 205082.56, "url": U_B3}, {"ref": "2026-10-26", "valor": 176608.23, "url": U_B3}],
        "desmat_deter": [{"ref": "2026-09-01", "valor": 350.19, "url": U_DET}],
        "arrecadacao": [{"ref": "2026-08-01", "valor": 2800.5, "url": "https://www.tesourotransparente.gov.br/x"}],
    }
    dados, saude = coletor.executar(hoje=d(2026, 10, 28), coletar_fn=fonte_falsa(resp))
    ind = dados["indicadores"]
    assert ind["ibovespa"]["baseline"]["valor"] == 176608.23
    assert ind["gasolina"]["baseline"]["ref"] == "2026-10-24"
    assert ind["desmat_deter"]["baseline"]["valor"] == 350.19
    assert not dados["quarentena"]
    analista.gerar(d(2026, 10, 28))
    dashboard.gerar() if hasattr(dashboard, "gerar") else dashboard.main()
    html = (ambiente / "site" / "dashboard.html").read_text(encoding="utf-8")
    assert "Meio ambiente" in html and "ibovespa" in html


def test_sidra_inseguranca_alimentar_formato_real():
    """Resposta real da API SIDRA para a tabela 6665 (conferida em 28/10/2026)."""
    from coletores import ibge_sidra
    path = config.CATALOGO["inseg_grave"]["params"]["path"]
    url = ibge_sidra.url_coleta(path, False)
    assert url.endswith("t/6665/n1/all/v/800/p/last%206/c12404/109102")
    payload = [{"NC": "Nível Territorial (Código)", "MN": "Unidade de Medida", "V": "Valor",
                "D1N": "Brasil", "D2C": "Variável (Código)", "D2N": "Variável", "D3C": "Ano (Código)", "D3N": "Ano",
                "D4C": "Situação (Código)", "D4N": "Situação de segurança alimentar existente no domicílio"},
               {"V": "4.1", "D2C": "800", "D3C": "2023", "D4C": "109102"},
               {"V": "3.2", "D2C": "800", "D3C": "2024", "D4C": "109102"}]
    obs = ibge_sidra.parse(payload, url, "anual", "800")
    assert [(o["ref"], o["valor"]) for o in obs] == [("2023-12-01", 4.1), ("2024-12-01", 3.2)]


def test_ativados_em_28_10():
    for id_ in ("inseg_grave", "pobreza", "ext_pobreza", "caged"):
        assert config.CATALOGO[id_]["ativo"] and not config.CATALOGO[id_]["validar"]
    assert "cds" not in config.CATALOGO
    assert all(i["ativo"] for i in config.INDICADORES)


def test_indicador_retirado_sai_do_painel_sem_perder_historico(ambiente):
    import json
    from datetime import date as d
    import coletor
    from tests.conftest import fonte_falsa
    coletor.executar(hoje=d(2026, 10, 28), coletar_fn=fonte_falsa({}))
    arq = ambiente / "data" / "dados.json"
    dados = json.loads(arq.read_text())
    antigo = {"nome": "Risco-país CDS 5 anos", "baseline": {"ref": "2026-10-26", "valor": 150.0},
              "serie": [{"ref": "2026-10-26", "valor": 150.0}]}
    dados["indicadores"]["cds"] = antigo
    dados["baseline_selos"]["cds"] = coletor.selo(antigo["baseline"])
    arq.write_text(json.dumps(dados))
    dados, saude = coletor.executar(hoje=d(2026, 11, 2), coletar_fn=fonte_falsa({}))
    assert "cds" not in dados["indicadores"] and "cds" not in dados["baseline_selos"]
    assert dados["descontinuados"]["cds"]["registro"]["serie"][0]["valor"] == 150.0
    assert not saude.get("integridade")
