"""Relatório semanal. As seções numéricas (tabela, pendências, saúde) são geradas por código;
a IA escreve apenas o resumo, os destaques e os balanços periódicos, a partir de um recorte do
dados.json e do saude.json. Se a IA falhar, o relatório sai sem a parte interpretativa."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date

import config
from coletor import RAIZ, carregar
from resumo import resumir

API = "https://api.anthropic.com/v1/messages"
MODELO = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-5-5"
DIR_REL = os.environ.get("MONITOR_RELATORIOS", os.path.join(RAIZ, "relatorios"))

SISTEMA = """Você é um analista econômico apartidário. Regras obrigatórias:
1. Use exclusivamente os dados do JSON fornecido. Não use conhecimento externo sobre valores, eventos ou datas.
2. Não calcule novas variações: use os campos var_anterior e var_baseline já calculados (unidade em unidade_var: "pp" = pontos percentuais, "pct" = variação percentual).
3. Se um dado estiver ausente, escreva "Dado não disponível nesta coleta".
4. Linguagem neutra, sem adjetivos valorativos, sem viés partidário. Não atribua causalidade ao governo ou a qualquer agente; quando citar possíveis fatores, rotule como hipótese.
5. Diferencie fato (o que o dado mostra) de interpretação (rotulada como "Interpretação:").
6. "melhor" indica a direção desejável do indicador; "direcao" já classifica melhora/piora frente à linha de base.
7. Não use travessões. Português do Brasil.
Responda SOMENTE com um objeto JSON com as chaves:
"resumo" (texto de até 5 linhas), "destaques" (markdown com subtítulos "Positivos" e "Negativos", baseados só nas variações), "balanco" (markdown ou null; preencha apenas se tipo_balanco não for null)."""


def tipo_balanco(hoje):
    if hoje.day > 7:
        return None
    return "trimestral" if hoje.month in (1, 4, 7, 10) else "mensal"


def montar_payload(dados, saude, hoje):
    r = resumir(dados, saude)
    inds = []
    for id_, reg in dados["indicadores"].items():
        x = r[id_]
        inds.append({
            "id": id_, "nome": reg["nome"], "un": reg["un"], "eixo": reg["eixo"], "melhor": reg["melhor"],
            "fonte": reg["fonte"], "ativo": reg.get("ativo"),
            "baseline": x["baseline"] and {k: x["baseline"][k] for k in ("ref", "valor")},
            "atual": x["atual"] and {k: x["atual"][k] for k in ("ref", "valor")},
            "anterior": x["anterior"] and {k: x["anterior"][k] for k in ("ref", "valor")},
            "var_anterior": x["var_anterior"], "var_baseline": x["var_baseline"],
            "unidade_var": x["unidade_var"], "direcao": x["direcao"],
            "atualizado_na_semana": x["atualizado_na_semana"], "atrasado": x["atrasado"],
            "ultimos": [{"ref": p["ref"], "valor": p["valor"]} for p in reg["serie"][-13:]],
        })
    return {
        "data_coleta": hoje.isoformat(), "baseline_data": dados["baseline_data"],
        "tipo_balanco": tipo_balanco(hoje), "indicadores": inds,
        "saude": {"status_geral": saude.get("status_geral"), "fontes": saude.get("fontes"),
                  "integridade": saude.get("integridade")},
    }


def chamar_ia(payload, chave, _urlopen=urllib.request.urlopen):
    corpo = json.dumps({
        "model": MODELO, "max_tokens": 2500, "temperature": 0, "system": SISTEMA,
        "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    }).encode()
    ultimo = None
    for i in range(3):
        try:
            req = urllib.request.Request(API, data=corpo, method="POST", headers={
                "x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            with _urlopen(req, timeout=120) as resp:
                r = json.loads(resp.read())
            texto = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
            m = re.search(r"\{.*\}", texto, re.S)
            if not m:
                raise ValueError("resposta da IA sem JSON")
            return json.loads(m.group(0)), r.get("usage", {})
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 529):
                break
        except Exception as e:
            ultimo = f"{type(e).__name__}: {e}"
        time.sleep(5 * (2 ** i))
    raise RuntimeError(ultimo)


# ------------------------------------------------------------------ controle de rastreabilidade
_NUM = re.compile(r"(?<![\w/-])[-+]?\d{1,3}(?:\.\d{3})*(?:,\d+)?(?![\w/])|(?<![\w/-])[-+]?\d+(?:[.,]\d+)?(?![\w/])")


def _normalizar(t):
    t = t.lstrip("+")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def numeros_nao_rastreaveis(texto, payload):
    """Lista números citados pela IA que não aparecem (em nenhum arredondamento) no payload."""
    conhecidos = set()

    def coletar(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            for c in range(0, 5):
                conhecidos.add(round(float(o), c))
                conhecidos.add(round(abs(float(o)), c))
        elif isinstance(o, dict):
            for v in o.values():
                coletar(v)
        elif isinstance(o, list):
            for v in o:
                coletar(v)
    coletar(payload)
    suspeitos = []
    for m in _NUM.finditer(texto or ""):
        v = _normalizar(m.group(0))
        if v is None or (v.is_integer() and (abs(v) <= 31 or 1900 <= v <= 2100)):
            continue  # dias, meses, contagens pequenas e anos
        casas = len(m.group(0).split(",")[-1]) if "," in m.group(0) else (
            len(m.group(0).split(".")[-1]) if "." in m.group(0) and not re.search(r"\.\d{3}", m.group(0)) else 0)
        if round(v, casas) not in conhecidos and round(abs(v), casas) not in conhecidos:
            suspeitos.append(m.group(0))
    return suspeitos


# ------------------------------------------------------------------ seções determinísticas
def fmt(v, casas=2):
    if v is None:
        return "Dado não disponível nesta coleta"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_valor(v, un):
    if v is None:
        return "Dado não disponível nesta coleta"
    casas = 3 if un == "índice" and abs(v) < 10 else (0 if un == "vagas" else (4 if un == "R$" and abs(v) < 20 else 2))
    return fmt(v, casas)


def fmt_var(v, tipo):
    if v is None:
        return "n/d"
    return ("+" if v > 0 else "") + fmt(v) + (" p.p." if tipo == "pp" else "%")


def data_br(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else (iso or "")


def secoes_fixas(dados, saude):
    r = resumir(dados, saude)
    linhas = ["| Indicador | Valor | Ref. | vs. anterior | vs. linha de base | Fonte |",
              "|---|---|---|---|---|---|"]
    pend = []
    for id_, reg in dados["indicadores"].items():
        x = r[id_]
        if x["atualizado_na_semana"] and x["atual"]:
            linhas.append(f"| {reg['nome']} | {fmt_valor(x['atual']['valor'], reg['un'])} {reg['un']} | "
                          f"{data_br(x['atual']['ref'])} | {fmt_var(x['var_anterior'], x['unidade_var'])} | "
                          f"{fmt_var(x['var_baseline'], x['unidade_var'])} | [{reg['fonte']}]({x['atual']['url']}) |")
        else:
            ult = data_br(x["atual"]["ref"]) if x["atual"] else "sem dado"
            extra = " (coletor desativado: VALIDAR)" if not reg.get("ativo") else ""
            selo = " **dado atrasado**" if x["atrasado"] else ""
            pend.append(f"- {reg['nome']}: última ref. {ult}{selo}{extra}. Calendário típico: {reg['calendario']}.")
    tabela = "\n".join(linhas) if len(linhas) > 2 else "Nenhum indicador recebeu dado novo nesta semana."
    alertas = []
    for a in saude.get("integridade") or []:
        alertas.append(f"- {a}")
    for id_, s in (saude.get("indicadores") or {}).items():
        if s["status"] in ("vermelho", "amarelo"):
            motivo = s.get("ultimo_erro") or ("dado atrasado" if s.get("atrasado") else "sem dados na série")
            alertas.append(f"- {'CRÍTICO' if s['status'] == 'vermelho' else 'Atenção'} {id_}: {motivo} "
                           f"(falhas seguidas: {s.get('falhas_consecutivas', 0)})")
    novas_q = [q for q in dados.get("quarentena", []) if q["coleta"] == dados["coletas"][-1]["data"]]
    for q in novas_q:
        alertas.append(f"- Quarentena {q['id']} {data_br(q['ref'])} = {q['valor']}: {q['motivo']}")
    return tabela, "\n".join(pend) or "Todos os indicadores foram atualizados.", "\n".join(alertas) or "Sem alertas."


def gerar(hoje=None):
    hoje = hoje or date.today()
    dados, saude = carregar("dados.json", None), carregar("saude.json", {})
    if not dados:
        raise SystemExit("dados.json inexistente: rode o coletor antes")
    tabela, pend, alertas = secoes_fixas(dados, saude)
    payload = montar_payload(dados, saude, hoje)
    ia, aviso, uso = None, None, {}
    chave = os.environ.get("ANTHROPIC_API_KEY")
    if not chave:
        aviso = "ANTHROPIC_API_KEY ausente: relatório sem análise interpretativa."
    else:
        try:
            ia, uso = chamar_ia(payload, chave)
        except Exception as e:
            aviso = f"Falha na API de IA ({e}): relatório sem análise interpretativa."
    sem_novos = dados["coletas"][-1].get("novos", 0) == 0
    partes = [f"# Relatório semanal | {data_br(hoje.isoformat())}",
              f"Linha de base: {data_br(dados['baseline_data'])} | Status do sistema: {saude.get('status_geral', 'n/d')}"]
    if sem_novos:
        partes.append("> Nenhum dado novo publicado pelas fontes desde a coleta anterior.")
    partes += ["## Resumo executivo", (ia or {}).get("resumo") or "Dado não disponível nesta coleta.",
               "## Indicadores atualizados na semana", tabela,
               "## Destaques positivos e negativos", (ia or {}).get("destaques") or "Dado não disponível nesta coleta."]
    if payload["tipo_balanco"] and ia and ia.get("balanco"):
        titulo = "Balanço trimestral frente à linha de base" if payload["tipo_balanco"] == "trimestral" else "Balanço do mês"
        partes += [f"## {titulo}", ia["balanco"]]
    partes += ["## Indicadores sem atualização e próxima divulgação prevista", pend,
               "## Alertas de saúde do sistema", alertas, "---"]
    rodape = [f"Valores e variações calculados por código a partir do dados.json. "
              f"Texto interpretativo: {'IA (' + MODELO + ')' if ia else 'não gerado'}."]
    if aviso:
        rodape.append(f"Aviso: {aviso}")
    if ia:
        sus = numeros_nao_rastreaveis(" ".join(str(v) for v in ia.values() if v), payload)
        rodape.append("Controle de rastreabilidade: " + (
            f"números citados pela IA sem correspondência nos dados: {', '.join(sus)}. Revisar." if sus
            else "todos os números citados pela IA constam nos dados."))
        if uso:
            rodape.append(f"Tokens: entrada {uso.get('input_tokens')}, saída {uso.get('output_tokens')}.")
    partes.append(" ".join(rodape))
    os.makedirs(DIR_REL, exist_ok=True)
    caminho = os.path.join(DIR_REL, f"{hoje.isoformat()}.md")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n\n".join(partes) + "\n")
    print(f"Relatório: {caminho}" + (f" | {aviso}" if aviso else ""))
    return caminho


if __name__ == "__main__":
    import sys
    gerar(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)
