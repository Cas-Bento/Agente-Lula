"""Tesouro Nacional, Tesouro Transparente (CKAN): estoque da Dívida Pública Federal.

Fluxo: package_show(dataset) -> primeiro recurso CSV -> download -> colunas configuradas.
VALIDAR: dataset, col_data, col_valor e divisor em config.py.
"""
import csv
import io
import re
from urllib.parse import quote

from coletores.util import Desativado, LayoutErro, http_get, http_json, num

CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id={}"


def _ref(txt):
    s = txt.strip()
    for pad, fmt in ((r"(\d{2})/(\d{2})/(\d{4})", "{2}-{1}-01"), (r"(\d{4})-(\d{2})", "{0}-{1}-01"),
                     (r"(\d{2})/(\d{4})", "{1}-{0}-01")):
        m = re.fullmatch(pad, s[:10]) or re.match(pad, s)
        if m:
            return fmt.format(*m.groups())
    raise LayoutErro(f"Tesouro: data inesperada {txt!r}")


def parse_csv(texto, url, col_data, col_valor, divisor):
    amostra = texto[:2000]
    dialeto = csv.Sniffer().sniff(amostra, delimiters=";,") if amostra else csv.excel
    leitor = csv.DictReader(io.StringIO(texto), dialect=dialeto)
    if not leitor.fieldnames or col_data not in leitor.fieldnames or col_valor not in leitor.fieldnames:
        raise LayoutErro(f"Tesouro: colunas {col_data}/{col_valor} ausentes: {leitor.fieldnames}")
    obs = {}
    for linha in leitor:
        v = num(linha[col_valor])
        if v is None:
            continue
        ref = _ref(linha[col_data])
        obs[ref] = {"ref": ref, "valor": v / divisor, "url": url}
    if not obs:
        raise LayoutErro("Tesouro: CSV sem valores")
    return sorted(obs.values(), key=lambda o: o["ref"])[-24:]


def coletar(ind, primeira, hoje):
    p = ind["params"]
    if not (p.get("dataset") and p.get("col_data") and p.get("col_valor")):
        raise Desativado("Tesouro: dataset/colunas não configurados (VALIDAR)")
    meta = http_json(CKAN.format(quote(p["dataset"])))
    recursos = (meta.get("result") or {}).get("resources") or []
    csvs = [r for r in recursos if str(r.get("format", "")).upper() == "CSV" and r.get("url")]
    if not csvs:
        raise LayoutErro("Tesouro: dataset sem recurso CSV")
    url = csvs[0]["url"]
    texto = http_get(url).decode("utf-8-sig", errors="replace")
    return parse_csv(texto, url, p["col_data"], p["col_valor"], p.get("divisor", 1))
