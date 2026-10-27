"""Banco Central, Sistema Gerenciador de Séries Temporais (SGS)."""
from datetime import timedelta

import config
from coletores.util import LayoutErro, data_br, http_json, num


def url_coleta(codigo, primeira, hoje):
    base = config.SGS.format(codigo=codigo)
    if primeira:
        ini = (hoje - timedelta(days=365 * config.HISTORICO_INICIAL_ANOS)).strftime("%d/%m/%Y")
        return f"{base}?formato=json&dataInicial={ini}&dataFinal={hoje.strftime('%d/%m/%Y')}"
    # a API limita "ultimos" a poucas dezenas de pontos; 20 cobre uma semana de série diária
    return f"{base}/ultimos/20?formato=json"


def parse(payload, url):
    if not isinstance(payload, list):
        raise LayoutErro("SGS: resposta não é uma lista")
    obs = []
    for item in payload:
        if not isinstance(item, dict) or "data" not in item or "valor" not in item:
            raise LayoutErro(f"SGS: item fora do formato {{data, valor}}: {item!r}")
        v = num(item["valor"])
        if v is None:
            continue  # valor ausente na fonte: não completar
        obs.append({"ref": data_br(item["data"]), "valor": v, "url": url})
    # a API devolve algumas séries em ordem decrescente: normalizar
    return sorted(obs, key=lambda o: o["ref"])


def coletar(ind, primeira, hoje):
    url = url_coleta(ind["params"]["codigo"], primeira, hoje)
    return parse(http_json(url), url)
