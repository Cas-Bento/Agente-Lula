"""Banco Central, Boletim Focus via API Olinda (ExpectativasMercadoAnuais).

Regra: mediana, baseCalculo = 0, para o ano seguinte ao da coleta. Em 1º de janeiro o ano-alvo
muda (ex.: 2027 -> 2028). Cada ponto grava o campo "alvo" para que essa troca fique explícita.
"""
from urllib.parse import quote

import config
from coletores.util import LayoutErro, http_json, num


def url_coleta(indicador, alvo, primeira):
    top = 60 if primeira else 10
    filtro = (f"Indicador eq '{indicador}' and DataReferencia eq '{alvo}' and baseCalculo eq 0")
    q = (f"$top={top}&$filter={quote(filtro)}&$orderby={quote('Data desc')}&$format=json"
         f"&$select=Indicador,Data,DataReferencia,Mediana,baseCalculo")
    return f"{config.OLINDA_FOCUS}?{q}"


def parse(payload, url, alvo):
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
        raise LayoutErro("Focus: resposta sem a lista 'value'")
    obs = {}
    for it in payload["value"]:
        if not {"Data", "Mediana", "DataReferencia"} <= set(it):
            raise LayoutErro(f"Focus: item fora do formato: {it!r}")
        if str(it["DataReferencia"]) != str(alvo):
            raise LayoutErro(f"Focus: ano de referência inesperado {it['DataReferencia']}")
        v = num(it["Mediana"])
        if v is None:
            continue
        ref = str(it["Data"])[:10]
        obs[ref] = {"ref": ref, "valor": v, "url": url, "alvo": str(alvo)}
    return sorted(obs.values(), key=lambda o: o["ref"])


def coletar(ind, primeira, hoje):
    alvo = hoje.year + 1
    url = url_coleta(ind["params"]["indicador"], alvo, primeira)
    obs = parse(http_json(url), url, alvo)
    if not obs:
        raise LayoutErro(f"Focus: nenhuma mediana para {ind['params']['indicador']} {alvo}")
    return obs
