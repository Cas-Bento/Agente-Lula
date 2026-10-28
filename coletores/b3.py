"""B3, estatísticas diárias do Ibovespa (fonte primária: a B3 calcula e publica o índice).

Endpoint usado pela página pública "Estatísticas de Índices" da B3 (conferido em 28/10/2026):
  https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/<base64>
com <base64> = {"index":"IBOV","language":"pt-br","year":"AAAA"}.
Resposta: {"results": [{"day": 1..31, "rateValue1".."rateValue12": "176.608,23" ou null}]},
em que rateValueM é o fechamento do dia "day" no mês M.

Ponto de atenção: não é uma API documentada; a B3 pode mudar o formato sem aviso. Nesse caso
o coletor falha com LayoutErro, abre Issue e o manual.csv serve de contingência.
"""
import base64
import json
from datetime import date

from coletores.util import LayoutErro, http_json, num

BASE = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/"


def url_ano(indice, ano):
    p = json.dumps({"index": indice, "language": "pt-br", "year": str(ano)}, separators=(",", ":"))
    return BASE + base64.b64encode(p.encode()).decode()


def parse(payload, ano, url):
    res = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(res, list):
        raise LayoutErro("B3: resposta sem 'results'")
    obs = []
    for item in res:
        if not isinstance(item, dict) or "day" not in item:
            raise LayoutErro(f"B3: item fora do formato: {item!r}")
        for mes in range(1, 13):
            v = num(item.get(f"rateValue{mes}"))
            if v is None:
                continue
            try:
                d = date(ano, mes, int(item["day"]))
            except ValueError as e:
                raise LayoutErro(f"B3: data inválida {ano}-{mes}-{item['day']}") from e
            obs.append({"ref": d.isoformat(), "valor": v, "url": url})
    return sorted(obs, key=lambda o: o["ref"])


def coletar(ind, primeira, hoje, _json=http_json):
    indice = ind["params"].get("indice", "IBOV")
    anos = [hoje.year - 2, hoje.year - 1, hoje.year] if primeira else (
        [hoje.year - 1, hoje.year] if hoje.month == 1 else [hoje.year])
    obs = []
    for a in anos:
        u = url_ano(indice, a)
        obs += parse(_json(u), a, u)
    if not obs:
        raise LayoutErro("B3: nenhum fechamento na resposta")
    hoje_iso = hoje.isoformat()
    return [o for o in obs if o["ref"] <= hoje_iso]
