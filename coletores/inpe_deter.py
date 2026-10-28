"""INPE, DETER Amazônia (TerraBrasilis/GeoServer, WFS público).

Camada deter-amz:deter_amz (conferida em 28/10/2026): campos classname, view_date, areamunkm,
publish_month, entre outros; histórico desde ago/2016.

Indicador gravado: área mensal de avisos de desmatamento na Amazônia Legal, em km², somando
as classes DESMATAMENTO_CR (corte raso), DESMATAMENTO_VEG (com vegetação) e MINERACAO, pela
data de observação (view_date). Degradação, cicatriz de queimada e corte seletivo ficam de fora.

Regras:
- um pedido por mês (evita o limite de feições por resposta do servidor);
- o mês só é gravado 15 dias após terminar, porque avisos atrasados ainda entram nesse prazo;
- DETER é um sistema de alerta, não a taxa oficial anual (PRODES). Ver README.
"""
import csv
import io
from datetime import date, timedelta
from urllib.parse import quote

from coletores.util import LayoutErro, http_get

BASE = "https://terrabrasilis.dpi.inpe.br/geoserver/deter-amz/ows"
CLASSES = ("DESMATAMENTO_CR", "DESMATAMENTO_VEG", "MINERACAO")
CARENCIA_DIAS = 15


def url_mes(ini, fim):
    cql = (f"view_date >= '{ini.isoformat()}' AND view_date < '{fim.isoformat()}' AND "
           f"classname IN ({','.join(repr(c) for c in CLASSES)})")
    return (f"{BASE}?service=WFS&version=2.0.0&request=GetFeature&typeName=deter-amz:deter_amz"
            f"&outputFormat=csv&propertyName=classname,view_date,areamunkm&CQL_FILTER={quote(cql)}")


def somar_csv(texto):
    if "ExceptionReport" in texto[:500]:
        raise LayoutErro(f"DETER: servidor devolveu exceção: {texto[:300]}")
    leitor = csv.DictReader(io.StringIO(texto))
    if not leitor.fieldnames or "areamunkm" not in leitor.fieldnames or "classname" not in leitor.fieldnames:
        raise LayoutErro(f"DETER: colunas inesperadas {leitor.fieldnames}")
    total = 0.0
    for l in leitor:
        if l["classname"] not in CLASSES:
            raise LayoutErro(f"DETER: classe fora do filtro: {l['classname']}")
        total += float(l["areamunkm"] or 0)
    return total


def _proximo(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def meses_fechados(hoje, n):
    """Últimos n meses cujo fim ocorreu há pelo menos CARENCIA_DIAS dias."""
    m = date(hoje.year, hoje.month, 1)
    saida = []
    while len(saida) < n:
        m = date(m.year - (m.month == 1), (m.month - 2) % 12 + 1, 1)
        if _proximo(m) + timedelta(days=CARENCIA_DIAS) <= hoje:
            saida.append(m)
    return sorted(saida)


def coletar(ind, primeira, hoje, _get=http_get):
    obs = []
    for ini in meses_fechados(hoje, 24 if primeira else 3):
        url = url_mes(ini, _proximo(ini))
        texto = _get(url, timeout=90).decode("utf-8-sig", errors="replace")
        obs.append({"ref": ini.isoformat(), "valor": round(somar_csv(texto), 4), "url": url})
    return obs
