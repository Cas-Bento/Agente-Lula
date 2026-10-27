import pytest

from coletores import bcb_focus, bcb_sgs, dieese, ibge_sidra, tesouro
from coletores.util import LayoutErro, num, periodo_sidra

# Respostas reais (formato) obtidas das APIs oficiais em 27/10/2026
SIDRA_6381 = [
    {"NC": "Nível Territorial (Código)", "NN": "Nível Territorial", "MC": "Unidade de Medida (Código)",
     "MN": "Unidade de Medida", "V": "Valor", "D1C": "Brasil (Código)", "D1N": "Brasil",
     "D2C": "Variável (Código)", "D2N": "Variável", "D3C": "Trimestre Móvel (Código)", "D3N": "Trimestre Móvel"},
    {"NC": "1", "NN": "Brasil", "MC": "2", "MN": "%", "V": "5.3", "D1C": "1", "D1N": "Brasil",
     "D2C": "4099", "D2N": "Taxa de desocupação", "D3C": "202608", "D3N": "jun-jul-ago 2026"},
    {"NC": "1", "NN": "Brasil", "MC": "2", "MN": "%", "V": "...", "D1C": "1", "D1N": "Brasil",
     "D2C": "4099", "D2N": "Taxa de desocupação", "D3C": "202609", "D3N": "jul-ago-set 2026"},
]


def test_num_formatos():
    assert num("1.234,56") == 1234.56
    assert num("5.4321") == 5.4321
    assert num("...") is None and num("-") is None and num("") is None
    assert num("nan") is None


def test_periodo_sidra():
    assert periodo_sidra("202608", "mensal") == "2026-08-01"
    assert periodo_sidra("202602", "trimestral") == "2026-06-01"
    assert periodo_sidra("2025", "anual") == "2025-12-01"
    with pytest.raises(LayoutErro):
        periodo_sidra("202613", "mensal")


def test_sgs_ordena_e_ignora_vazio():
    payload = [{"data": "01/08/2026", "valor": "0.62"}, {"data": "01/07/2026", "valor": "0.67"},
               {"data": "01/06/2026", "valor": ""}]
    obs = bcb_sgs.parse(payload, "https://api.bcb.gov.br/x")
    assert [o["ref"] for o in obs] == ["2026-07-01", "2026-08-01"]
    assert obs[1]["valor"] == 0.62


def test_sgs_layout_errado():
    with pytest.raises(LayoutErro):
        bcb_sgs.parse([{"date": "01/08/2026", "value": "1"}], "u")
    with pytest.raises(LayoutErro):
        bcb_sgs.parse({"erro": "x"}, "u")


def test_sidra_real_e_valor_ausente():
    obs = ibge_sidra.parse(SIDRA_6381, "https://apisidra.ibge.gov.br/x", "mensal", "4099")
    assert obs == [{"ref": "2026-08-01", "valor": 5.3, "url": "https://apisidra.ibge.gov.br/x"}]


def test_sidra_variavel_inesperada():
    with pytest.raises(LayoutErro):
        ibge_sidra.parse(SIDRA_6381, "u", "mensal", "4097")


def test_sidra_url_insere_periodo_antes_da_classificacao():
    u = ibge_sidra.url_coleta("t/5932/n1/all/v/6561/c11255/90707", False)
    assert u.endswith("t/5932/n1/all/v/6561/p/last%206/c11255/90707")


def test_focus():
    payload = {"value": [{"Indicador": "IPCA", "Data": "2026-10-23", "DataReferencia": "2027", "Mediana": 4.1},
                         {"Indicador": "IPCA", "Data": "2026-10-16", "DataReferencia": "2027", "Mediana": 4.15}]}
    obs = bcb_focus.parse(payload, "https://olinda.bcb.gov.br/x", 2027)
    assert [o["ref"] for o in obs] == ["2026-10-16", "2026-10-23"] and obs[0]["alvo"] == "2027"
    with pytest.raises(LayoutErro):
        bcb_focus.parse({"value": [{"Data": "2026-10-23", "DataReferencia": "2028", "Mediana": 1}]}, "u", 2027)


def test_dieese_html():
    html = """<h2>Custo da cesta básica, setembro de 2026</h2>
    <table><tr><th>Capital</th><th>Valor da cesta (R$)</th><th>Variação</th></tr>
    <tr><td>Rio de Janeiro</td><td>800,10</td><td>1,0</td></tr>
    <tr><td>São Paulo</td><td>850,12</td><td>0,5</td></tr></table>"""
    assert dieese.parse(html, "https://www.dieese.org.br/x", "São Paulo") == [
        {"ref": "2026-09-01", "valor": 850.12, "url": "https://www.dieese.org.br/x"}]
    with pytest.raises(LayoutErro):
        dieese.parse(html.replace("Valor", "Preço"), "u", "São Paulo")
    with pytest.raises(LayoutErro):
        dieese.parse(html.replace("setembro de 2026", ""), "u", "São Paulo")


def test_tesouro_csv():
    csv_txt = "Mes;Estoque\n01/08/2026;8.100.000.000.000,00\n01/09/2026;8.200.000.000.000,00\n"
    obs = tesouro.parse_csv(csv_txt, "https://www.tesourotransparente.gov.br/x", "Mes", "Estoque", 1e12)
    assert obs[-1] == {"ref": "2026-09-01", "valor": 8.2, "url": "https://www.tesourotransparente.gov.br/x"}
    with pytest.raises(LayoutErro):
        tesouro.parse_csv(csv_txt, "u", "Data", "Estoque", 1)
