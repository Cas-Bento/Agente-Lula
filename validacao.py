"""Validação de sanidade de cada observação antes de entrar na série."""
import math
from urllib.parse import urlparse

import config


def dominio_oficial(url):
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in config.DOMINIOS_OFICIAIS)


def validar(ind, obs, anterior, hoje_iso, exigir_dominio=True):
    """Retorna None se a observação é válida, ou o motivo da rejeição.

    ind: entrada do catálogo | obs: {ref, valor, url} | anterior: último ponto válido com ref < obs.ref
    """
    v = obs.get("valor")
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        return f"valor não numérico: {v!r}"
    if not obs.get("ref") or obs["ref"] > hoje_iso:
        return f"data de referência inválida ou futura: {obs.get('ref')}"
    if exigir_dominio and not dominio_oficial(obs.get("url")):
        return f"URL fora dos domínios oficiais: {obs.get('url')}"
    lo, hi = ind["faixa"]
    if not lo <= v <= hi:
        return f"fora da faixa plausível [{lo}, {hi}]"
    if anterior is not None:
        tipo, lim = ind["var_max"]
        a = anterior["valor"]
        if tipo == "abs" and abs(v - a) > lim:
            return f"variação {v - a:+.4g} acima do limite absoluto {lim} vs {anterior['ref']}"
        if tipo == "rel" and a != 0 and abs(v / a - 1) > lim:
            return f"variação {100 * (v / a - 1):+.2f}% acima do limite {100 * lim:.0f}% vs {anterior['ref']}"
    return None
