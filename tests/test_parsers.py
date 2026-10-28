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


def test_dieese_texto():
    texto = ("Pesquisa Nacional da Cesta Básica de Alimentos Brasil - Julho de 2026 "
             "Em São Paulo (R$ 915,01) o custo caiu. Tabela 1 Capital Valor da cesta Variação mensal (%) "
             "Rio de Janeiro 855,37 -1,10 57,00 115h00m\nSão Paulo 915,01 -5,23 61,02 124h11m 8,16 5,67")
    url = "https://www.dieese.org.br/analisecestabasica/2026/202607cestabasica.pdf"
    assert dieese.parse_texto(texto, "2026-07-01", url, "São Paulo") == {"ref": "2026-07-01", "valor": 915.01, "url": url}
    with pytest.raises(LayoutErro):  # mês divergente do endereço
        dieese.parse_texto(texto, "2026-08-01", url, "São Paulo")
    with pytest.raises(LayoutErro):  # tabela sem a linha da cidade
        dieese.parse_texto(texto.replace("São Paulo 915,01 -5,23", "SP"), "2026-07-01", url, "São Paulo")


def test_dieese_pdf_real():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    import io
    w = PdfWriter()
    pg = w.add_blank_page(width=600, height=400)
    fonte = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                              NameObject("/BaseFont"): NameObject("/Helvetica"),
                              NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    pg[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(fonte)})})
    linhas = ["Brasil - Julho de 2026", "Capital Valor da cesta Variacao mensal (%)", "S\xe3o Paulo 915,01 -5,23 61,02 124h11m"]
    ops = "BT /F1 12 Tf 50 350 Td " + " ".join(f"({l}) Tj 0 -20 Td" for l in linhas) + " ET"
    st = DecodedStreamObject(); st.set_data(ops.encode("latin-1"))
    pg[NameObject("/Contents")] = w._add_object(st)
    buf = io.BytesIO(); w.write(buf)
    txt = dieese.texto_pdf(buf.getvalue())
    assert dieese.parse_texto(txt, "2026-07-01", "u", "São Paulo")["valor"] == 915.01


def test_dieese_coletar_404_e_janela():
    from datetime import date
    from coletores.util import ColetaErro
    chamadas = []

    def get(url):
        chamadas.append(url)
        if "202609" in url:
            raise ColetaErro(f"HTTP 404 em {url}")
        return url.encode()

    def texto(conteudo):
        u = conteudo.decode()
        mes = {"06": "Junho", "07": "Julho", "08": "Agosto"}[u[-17:-15]]
        return f"{mes} de 2026 São Paulo 900,00 -1,00 60,00"
    ind = {"params": {"cidade": "São Paulo"}}
    obs = dieese.coletar(ind, False, date(2026, 10, 27), _get=get, _texto=texto)
    assert [o["ref"] for o in obs] == ["2026-06-01", "2026-07-01", "2026-08-01"]
    assert chamadas[0].endswith("2026/202606cestabasica.pdf") and len(chamadas) == 4
    assert dieese.meses_alvo(date(2027, 1, 5), 2) == [date(2026, 11, 1), date(2026, 12, 1)]


def test_tesouro_csv():
    csv_txt = ("Titulo;Vencimento do Titulo;Valor do Estoque;Quantidade do Estoque;Mes do Estoque;Classe da Carteira;Tipo de Divida\n"
               "LTN;01/01/2027;4.000.000.000.000,00;1;ago/2026;Mercado;Interna\n"
               "NTN-B;15/05/2035;4.100.000.000.000,00;1;ago/2026;Mercado;Interna\n"
               "LTN;01/01/2027;999.000.000.000,00;1;ago/2026;Bacen;Interna\n"
               "LTN;01/01/2027;8.200.000.000.000,00;1;set/2026;Mercado;Interna\n")
    url = "https://www.tesourotransparente.gov.br/x"
    obs = tesouro.parse_csv(csv_txt, url)
    assert obs == [{"ref": "2026-08-01", "valor": 8.1, "url": url}, {"ref": "2026-09-01", "valor": 8.2, "url": url}]
    with pytest.raises(LayoutErro):  # sem coluna de classe
        tesouro.parse_csv(csv_txt.replace("Classe da Carteira", "Carteira"), url)
    assert tesouro.ref_mes("Set/26") == "2026-09-01" and tesouro.ref_mes("2026-09") == "2026-09-01"
    assert tesouro.valor("8100000000000.5") == 8100000000000.5
    meta = {"result": {"resources": [{"format": "PDF", "url": "m.pdf", "name": "Metadados"},
                                     {"format": "CSV", "url": "https://x/EstoqueDPF.csv", "name": "Estoque da DPF"}]}}
    assert tesouro.recurso_csv(meta) == "https://x/EstoqueDPF.csv"