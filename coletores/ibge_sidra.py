"""IBGE, API SIDRA (apisidra.ibge.gov.br/values)."""
import config
from coletores.util import LayoutErro, http_json, num, periodo_sidra

ROTULOS_PERIODO = ("Mês", "Trimestre", "Ano")


def url_coleta(path, primeira):
    n = 24 if primeira else 6
    partes = path.strip("/").split("/")
    if "v" not in partes:
        raise LayoutErro(f"SIDRA: path sem variável: {path}")
    i = partes.index("v") + 2
    partes[i:i] = ["p", f"last%20{n}"]
    return config.SIDRA.format(path="/".join(partes))


def variavel(path):
    partes = path.strip("/").split("/")
    return partes[partes.index("v") + 1]


def parse(payload, url, tipo, var_esperada):
    if not isinstance(payload, list) or len(payload) < 1 or not isinstance(payload[0], dict):
        raise LayoutErro("SIDRA: resposta sem cabeçalho")
    cab = payload[0]
    if cab.get("V") != "Valor":
        raise LayoutErro("SIDRA: cabeçalho sem a coluna Valor")
    chave_per = chave_var = None
    for k, rot in cab.items():
        if k.startswith("D") and k.endswith("N"):
            if rot.startswith(ROTULOS_PERIODO):
                chave_per = k[:-1] + "C"
            elif rot == "Variável":
                chave_var = k[:-1] + "C"
    if not chave_per or not chave_var:
        raise LayoutErro(f"SIDRA: dimensões de período/variável não encontradas: {cab}")
    obs = []
    for linha in payload[1:]:
        if str(linha.get(chave_var)) != str(var_esperada):
            raise LayoutErro(f"SIDRA: variável inesperada {linha.get(chave_var)}")
        v = num(linha.get("V"))
        if v is None:
            continue  # '...', '-', 'X': dado não divulgado ou sigiloso. Não completar.
        obs.append({"ref": periodo_sidra(linha[chave_per], tipo), "valor": v, "url": url})
    return sorted(obs, key=lambda o: o["ref"])


def coletar(ind, primeira, hoje):
    path = ind["params"]["path"]
    url = url_coleta(path, primeira)
    return parse(http_json(url), url, ind["params"]["periodo"], variavel(path))
