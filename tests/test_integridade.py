import json
from datetime import date

import coletor
from coletores.util import ColetaErro, LayoutErro
from tests.conftest import fonte_falsa

U = "https://api.bcb.gov.br/x"


def ob(ref, valor, url=U):
    return {"ref": ref, "valor": valor, "url": url}


def rodar(respostas, hoje):
    return coletor.executar(hoje=date.fromisoformat(hoje), coletar_fn=fonte_falsa(respostas))


def test_baseline_trava_e_nunca_e_sobrescrita(ambiente):
    d, _ = rodar({"selic": [ob("2026-10-20", 14.25), ob("2026-10-26", 14.25), ob("2026-10-27", 14.0)]}, "2026-10-27")
    b = d["indicadores"]["selic"]["baseline"]
    assert b["ref"] == "2026-10-26" and b["valor"] == 14.25
    d, _ = rodar({"selic": [ob("2026-11-03", 13.75)]}, "2026-11-03")
    assert d["indicadores"]["selic"]["baseline"] == b


def test_baseline_alterada_manual_e_detectada(ambiente):
    rodar({"selic": [ob("2026-10-26", 14.25)]}, "2026-10-27")
    p = ambiente / "data" / "dados.json"
    dados = json.loads(p.read_text())
    dados["indicadores"]["selic"]["baseline"]["valor"] = 10.0
    p.write_text(json.dumps(dados))
    d, s = rodar({}, "2026-11-03")
    assert s["status_geral"] == "vermelho" and any("selic" in x for x in s["integridade"])
    assert d["indicadores"]["selic"]["baseline"]["valor"] == 10.0  # sistema não "corrige" sozinho


def test_sem_duplicidade_e_revisao_nao_sobrescreve(ambiente):
    rodar({"ipca_m": [ob("2026-09-01", 0.44)]}, "2026-10-27")
    d, _ = rodar({"ipca_m": [ob("2026-09-01", 0.44)]}, "2026-11-03")
    assert len(d["indicadores"]["ipca_m"]["serie"]) == 1
    d, _ = rodar({"ipca_m": [ob("2026-09-01", 0.48)]}, "2026-11-10")
    assert d["indicadores"]["ipca_m"]["serie"][0]["valor"] == 0.44
    assert len(d["revisoes"]) == 1
    d, _ = rodar({"ipca_m": [ob("2026-09-01", 0.48)]}, "2026-11-17")
    assert len(d["revisoes"]) == 1


def test_ref_futura_descartada(ambiente):
    d, _ = rodar({"salario_min": [ob("2026-10-01", 1621.0), ob("2026-12-01", 1621.0)]}, "2026-10-27")
    assert [p["ref"] for p in d["indicadores"]["salario_min"]["serie"]] == ["2026-10-01"]


def test_quarentena_faixa_e_variacao(ambiente):
    d, s = rodar({"desocup": [ob("2026-08-01", 5.3), ob("2026-09-01", 60.0)],
                  "dolar": [ob("2026-10-23", 5.40), ob("2026-10-26", 9.0)]}, "2026-10-27")
    assert [p["valor"] for p in d["indicadores"]["desocup"]["serie"]] == [5.3]
    assert [p["valor"] for p in d["indicadores"]["dolar"]["serie"]] == [5.40]
    assert {q["id"] for q in d["quarentena"]} == {"desocup", "dolar"}
    d, _ = rodar({"desocup": [ob("2026-09-01", 60.0)]}, "2026-11-03")
    assert len([q for q in d["quarentena"] if q["id"] == "desocup"]) == 1


def test_falha_de_uma_fonte_nao_interrompe(ambiente):
    d, s = rodar({"dolar": ColetaErro("HTTP 503"), "euro": RuntimeError("bug"),
                  "selic": [ob("2026-10-26", 14.25)]}, "2026-10-27")
    assert d["indicadores"]["selic"]["serie"]
    assert s["indicadores"]["dolar"]["falhas_consecutivas"] == 1
    assert s["indicadores"]["euro"]["status"] == "amarelo"
    d, s = rodar({"dolar": LayoutErro("mudou"), "selic": [ob("2026-11-03", 14.25)]}, "2026-11-03")
    assert s["indicadores"]["dolar"]["status"] == "vermelho"
    d, s = rodar({"dolar": [ob("2026-11-07", 5.4)]}, "2026-11-10")
    assert s["indicadores"]["dolar"]["falhas_consecutivas"] == 0


def test_manual_so_quando_coletor_falha(ambiente):
    (ambiente / "manual.csv").write_text(
        "# comentário\nid,ref,valor,url\n"
        "dolar,2026-10-26,5.40,https://www.bcb.gov.br/x\n"
        "selic,2026-10-26,99,https://www.bcb.gov.br/x\n"
        "cesta_sp,2026-09-01,\"850,12\",https://www.dieese.org.br/x\n"
        "ipca_m,2026-09-01,0.5,https://noticias.exemplo.com/x\n", encoding="utf-8")
    d, _ = rodar({"dolar": ColetaErro("fora do ar"), "selic": [ob("2026-10-26", 14.25)],
                  "ipca_m": ColetaErro("x")}, "2026-10-27")
    assert d["indicadores"]["dolar"]["serie"][0]["origem"] == "manual"
    assert d["indicadores"]["selic"]["serie"][0]["valor"] == 14.25
    assert d["indicadores"]["cesta_sp"]["serie"][0]["valor"] == 850.12  # coletor inativo
    assert not d["indicadores"]["ipca_m"]["serie"]  # URL não oficial -> quarentena
    assert any(q["id"] == "ipca_m" for q in d["quarentena"])


def test_derivado_sm_cestas(ambiente):
    (ambiente / "manual.csv").write_text(
        "id,ref,valor,url\ncesta_sp,2026-09-01,810.5,https://www.dieese.org.br/x\n", encoding="utf-8")
    d, _ = rodar({"salario_min": [ob("2026-09-01", 1621.0)]}, "2026-10-27")
    p = d["indicadores"]["sm_cestas"]["serie"][0]
    assert p["valor"] == 1621.0 / 810.5 and p["ref"] == "2026-09-01"


def test_sem_dados_novos_registra_coleta(ambiente):
    rodar({"selic": [ob("2026-10-26", 14.25)]}, "2026-10-27")
    d, _ = rodar({"selic": [ob("2026-10-26", 14.25)]}, "2026-11-03")
    assert len(d["coletas"]) == 2 and d["coletas"][-1]["novos"] == 0
    assert any("SEM DADOS NOVOS" in l for l in d["coletas"][-1]["log"])


def test_dado_atrasado(ambiente):
    _, s = rodar({"ipca_m": [ob("2026-06-01", 0.3)]}, "2026-10-27")
    assert s["indicadores"]["ipca_m"]["atrasado"] and s["indicadores"]["ipca_m"]["status"] == "amarelo"


def test_particionamento_preserva_baseline(ambiente, monkeypatch):
    rodar({"selic": [ob("2026-10-26", 14.25)]}, "2026-10-27")
    monkeypatch.setattr(coletor.config, "LIMITE_DADOS_BYTES", 10)
    d, s = rodar({}, "2027-01-04")
    assert d["indicadores"]["selic"]["baseline"]["valor"] == 14.25 and not s["integridade"]
    assert all(c["data"].startswith("2027") for c in d["coletas"])
    assert (ambiente / "data" / "arquivo" / "2026.json").exists()
