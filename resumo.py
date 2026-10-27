"""Cálculos determinísticos de comparação (usados pelo relatório e pelo dashboard).

A IA recebe estes números prontos: ela não calcula nem corrige valores."""


def tipo_variacao(un):
    return "pp" if "%" in un else "pct"


def variacao(atual, base, un):
    if atual is None or base is None:
        return None
    if tipo_variacao(un) == "pp":
        return atual - base
    if base == 0:
        return None
    return (atual / base - 1) * 100


def direcao(var, melhor):
    if var is None:
        return "sem_base"
    if melhor == "neutro":
        return "neutro"
    if var == 0:
        return "estavel"
    return "melhora" if (var > 0) == (melhor == "alto") else "piora"


def resumir(dados, saude=None):
    saude = saude or {}
    ultima = dados["coletas"][-1]["data"] if dados.get("coletas") else None
    out = {}
    for id_, reg in dados["indicadores"].items():
        serie = reg["serie"]
        atual = serie[-1] if serie else None
        anterior = serie[-2] if len(serie) > 1 else None
        base = reg.get("baseline")
        va = variacao(atual and atual["valor"], anterior and anterior["valor"], reg["un"])
        vb = variacao(atual and atual["valor"], base and base["valor"], reg["un"])
        s = (saude.get("indicadores") or {}).get(id_, {})
        out[id_] = {
            "atual": atual, "anterior": anterior, "baseline": base,
            "var_anterior": va, "var_baseline": vb, "unidade_var": tipo_variacao(reg["un"]),
            "direcao": direcao(vb, reg["melhor"]),
            "atualizado_na_semana": bool(ultima and any(p["coleta"] == ultima for p in serie)),
            "atrasado": bool(s.get("atrasado")), "status": s.get("status"),
        }
    return out
