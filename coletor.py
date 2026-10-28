"""Orquestrador: coleta -> validação -> deduplicação -> trava da linha de base -> gravação -> saúde.

Uso:
  python coletor.py                       # execução normal (semanal)
  python coletor.py --hoje 2026-11-02     # simula a data de execução
  python coletor.py --liberar ID REF      # move um valor da quarentena para a série (auditado)
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

import config
from coletores import REGISTRO
from coletores.util import ColetaErro, Desativado, num
from validacao import validar

RAIZ = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("MONITOR_DATA", os.path.join(RAIZ, "data"))
MANUAL_CSV = os.environ.get("MONITOR_MANUAL", os.path.join(RAIZ, "manual.csv"))
CAMPOS_META = ("nome", "un", "eixo", "melhor", "fonte", "url", "periodicidade", "calendario")


# ----------------------------------------------------------------------------- persistência
def caminho(nome):
    return os.path.join(DATA_DIR, nome)


def carregar(nome, padrao):
    try:
        with open(caminho(nome), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return padrao


def salvar(nome, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = caminho(nome) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, caminho(nome))  # gravação atômica: nunca deixa arquivo pela metade


def novo_estado():
    return {"baseline_data": config.BASELINE_DATA, "coletas": [], "indicadores": {},
            "quarentena": [], "revisoes": [], "baseline_selos": {}}


def sincronizar_catalogo(dados):
    """Atualiza metadados a partir do config.py. Nunca toca em baseline nem série."""
    for ind in config.INDICADORES:
        reg = dados["indicadores"].setdefault(ind["id"], {"baseline": None, "serie": []})
        for c in CAMPOS_META:
            reg[c] = ind[c]
        reg["ativo"] = ind["ativo"]
        reg["validar"] = ind.get("validar")
    for k in ("quarentena", "revisoes"):
        dados.setdefault(k, [])
    dados.setdefault("baseline_selos", {})
    # Indicador retirado do config.py: sai do painel, mas a série, a linha de base e o selo
    # vão para "descontinuados" (nada é apagado; trilha de auditoria preservada).
    dados.setdefault("descontinuados", {})
    for id_ in [k for k in dados["indicadores"] if k not in config.CATALOGO]:
        dados["descontinuados"][id_] = {"registro": dados["indicadores"].pop(id_),
                                        "selo": dados["baseline_selos"].pop(id_, None)}


# ----------------------------------------------------------------------------- linha de base
def selo(baseline):
    return hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest()


def verificar_baselines(dados):
    """Detecta alteração manual da linha de base (o selo é gravado no momento da trava)."""
    problemas = []
    for id_, reg in dados["indicadores"].items():
        s = dados["baseline_selos"].get(id_)
        b = reg.get("baseline")
        if s and (b is None or selo(b) != s):
            problemas.append(f"CRÍTICO {id_}: linha de base alterada ou removida fora do sistema")
        if b is not None and not s:
            problemas.append(f"CRÍTICO {id_}: linha de base sem selo de integridade")
    return problemas


def travar_baselines(dados, coleta_iso):
    """Trava a linha de base de quem ainda não tem: último ponto com ref <= BASELINE_DATA.
    Uma vez gravada, a linha de base nunca é alterada por este código."""
    travados = []
    for id_, reg in dados["indicadores"].items():
        if reg.get("baseline") is not None:
            continue
        cand = [p for p in reg["serie"] if p["ref"] <= dados["baseline_data"]]
        if cand:
            p = max(cand, key=lambda x: x["ref"])
            reg["baseline"] = {"ref": p["ref"], "valor": p["valor"], "coleta": coleta_iso,
                               "fonte": p.get("fonte"), "url": p.get("url")}
            dados["baseline_selos"][id_] = selo(reg["baseline"])
            travados.append(id_)
    return travados


# ----------------------------------------------------------------------------- integração
def anterior_a(serie, ref):
    ant = [p for p in serie if p["ref"] < ref]
    return max(ant, key=lambda p: p["ref"]) if ant else None


def integrar(dados, id_, observacoes, coleta_iso, hoje_iso, origem="api"):
    """Integra observações de um indicador. Retorna (novos, log). Regras:
    - mesma ref e mesmo valor: ignora (sem duplicidade)
    - mesma ref e valor diferente: NÃO sobrescreve; registra em 'revisoes' para auditoria
    - ref nova: valida; se reprovada vai para quarentena, nunca para a série"""
    ind = config.CATALOGO[id_]
    reg = dados["indicadores"][id_]
    existentes = {p["ref"]: p for p in reg["serie"]}
    novos, log = 0, []
    for o in sorted(observacoes, key=lambda x: x["ref"]):
        if o["ref"] > hoje_iso:
            continue  # séries como a do salário mínimo trazem meses futuros já programados
        if o["ref"] in existentes:
            atual = existentes[o["ref"]]
            if atual["valor"] != o["valor"]:
                chave = (id_, o["ref"], o["valor"])
                if not any((r["id"], r["ref"], r["valor_novo"]) == chave for r in dados["revisoes"]):
                    dados["revisoes"].append({"id": id_, "ref": o["ref"], "valor_original": atual["valor"],
                                              "valor_novo": o["valor"], "coleta": coleta_iso, "url": o["url"]})
                    log.append(f"REVISÃO {id_} {o['ref']}: fonte publicou {o['valor']} (série mantém {atual['valor']})")
            continue
        motivo = validar(ind, o, anterior_a(reg["serie"], o["ref"]), hoje_iso)
        if motivo:
            chave = (id_, o["ref"], o["valor"])
            if not any((q["id"], q["ref"], q["valor"]) == chave for q in dados["quarentena"]):
                dados["quarentena"].append({"id": id_, "ref": o["ref"], "valor": o["valor"], "motivo": motivo,
                                            "coleta": coleta_iso, "url": o.get("url"), "origem": origem})
                log.append(f"QUARENTENA {id_} {o['ref']} = {o['valor']}: {motivo}")
            continue
        ponto = {"ref": o["ref"], "valor": o["valor"], "coleta": coleta_iso, "fonte": ind["fonte"],
                 "url": o["url"]}
        if o.get("alvo"):
            ponto["alvo"] = o["alvo"]
        if origem != "api":
            ponto["origem"] = origem
        reg["serie"].append(ponto)
        existentes[o["ref"]] = ponto
        novos += 1
    reg["serie"].sort(key=lambda p: p["ref"])
    return novos, log


def calcular_derivados(dados):
    """sm_cestas = salário mínimo do mês (BCB SGS 1619) / cesta básica SP do mesmo mês (DIEESE).
    Só calcula quando os dois dados oficiais existem para o mesmo mês. Sem estimativa."""
    sm = {p["ref"]: p for p in dados["indicadores"]["salario_min"]["serie"]}
    obs = []
    for c in dados["indicadores"]["cesta_sp"]["serie"]:
        s = sm.get(c["ref"])
        if s and c["valor"] > 0:
            obs.append({"ref": c["ref"], "valor": s["valor"] / c["valor"], "url": c["url"]})
    return obs


def ler_manual(path):
    if not os.path.exists(path):
        return []
    linhas = []
    with open(path, encoding="utf-8") as f:
        leitor = csv.DictReader(l for l in f if l.strip() and not l.lstrip().startswith("#"))
        for r in leitor:
            v = num(r.get("valor"))
            if r.get("id") in config.CATALOGO and r.get("ref") and v is not None:
                linhas.append({"id": r["id"].strip(), "ref": r["ref"].strip(), "valor": v,
                               "url": (r.get("url") or "").strip()})
    return linhas


# ----------------------------------------------------------------------------- saúde
SUGESTOES = {
    "rede": "Instabilidade ou bloqueio na fonte. Se persistir, testar a URL manualmente e verificar mudança de endpoint.",
    "layout": "O formato da resposta mudou. Revisar o parser do coletor; enquanto isso, usar manual.csv.",
    "desativado": "Coletor desativado ou não configurado (VALIDAR). Ver README.",
    "codigo": "Erro interno do coletor. Ver log e testes.",
}


def atualizar_saude(saude, resultados, dados, hoje, coleta_iso):
    saude.setdefault("indicadores", {})
    for id_, res in resultados.items():
        ind = config.CATALOGO[id_]
        s = saude["indicadores"].setdefault(id_, {"falhas_consecutivas": 0, "ultima_coleta_ok": None,
                                                   "ultimo_dado_novo": None})
        s["fonte"], s["ativo"] = ind["fonte"], ind["ativo"]
        if res["status"] == "ok":
            s["falhas_consecutivas"], s["ultimo_erro"], s["ultima_coleta_ok"] = 0, None, coleta_iso
            if res["novos"]:
                s["ultimo_dado_novo"] = coleta_iso
        elif res["status"] == "erro":
            s["falhas_consecutivas"] = s.get("falhas_consecutivas", 0) + 1
            s["ultimo_erro"] = res["erro"]
            s["sugestao"] = SUGESTOES.get(res.get("tipo"), SUGESTOES["codigo"])
        else:
            s["falhas_consecutivas"], s["ultimo_erro"] = 0, res.get("erro")
            s["sugestao"] = SUGESTOES["desativado"]
        serie = dados["indicadores"][id_]["serie"]
        s["ultima_ref"] = serie[-1]["ref"] if serie else None
        lim = ind.get("atraso_max_dias")
        s["atrasado"] = bool(lim and serie and (hoje - date.fromisoformat(serie[-1]["ref"])).days > lim)
        if res["status"] == "inativo":
            s["status"] = "cinza"
        elif s["falhas_consecutivas"] >= config.FALHAS_ALERTA_CRITICO:
            s["status"] = "vermelho"
        elif s["falhas_consecutivas"] or s["atrasado"] or not serie:
            s["status"] = "amarelo"
        else:
            s["status"] = "verde"
    ordem = {"vermelho": 3, "amarelo": 2, "verde": 1, "cinza": 0}
    fontes = {}
    for s in saude["indicadores"].values():
        f = s["fonte"]
        if ordem[s["status"]] >= ordem.get(fontes.get(f, "cinza"), 0):
            fontes[f] = s["status"]
    saude["fontes"] = fontes
    integridade = verificar_baselines(dados)
    saude["integridade"] = integridade
    pior = max([ordem[s] for s in fontes.values()] + [0])
    saude["status_geral"] = "vermelho" if integridade else {3: "vermelho", 2: "amarelo"}.get(pior, "verde")
    saude["atualizado"] = coleta_iso
    return saude


# ----------------------------------------------------------------------------- rotação
def particionar(dados, hoje):
    """Se dados.json passar do limite, move logs de coleta e quarentena de anos anteriores para
    data/arquivo/AAAA.json. Linha de base, selos e séries nunca saem do arquivo principal."""
    tamanho = len(json.dumps(dados, ensure_ascii=False).encode())
    if tamanho <= config.LIMITE_DADOS_BYTES:
        return None
    ano_atual = str(hoje.year)
    movidos = {}
    for chave in ("coletas", "quarentena"):
        campo = "data" if chave == "coletas" else "coleta"
        ficam = []
        for item in dados[chave]:
            ano = str(item[campo])[:4]
            (ficam if ano >= ano_atual else movidos.setdefault(ano, {}).setdefault(chave, [])).append(item)
        dados[chave] = ficam
    os.makedirs(caminho("arquivo"), exist_ok=True)
    for ano, blocos in movidos.items():
        nome = os.path.join("arquivo", f"{ano}.json")
        arq = carregar(nome, {"ano": ano, "coletas": [], "quarentena": []})
        for k, v in blocos.items():
            arq[k].extend(v)
        salvar(nome, arq)
    return sorted(movidos)


# ----------------------------------------------------------------------------- execução
def executar(hoje=None, coletar_fn=None, agora=None):
    hoje = hoje or date.today()
    agora = agora or datetime.now(timezone.utc)
    coleta_iso = hoje.isoformat()
    hoje_iso = hoje.isoformat()
    dados = carregar("dados.json", None) or novo_estado()
    saude = carregar("saude.json", {})
    sincronizar_catalogo(dados)
    log = [f"INÍCIO coleta {agora.isoformat(timespec='seconds')}"]
    log += verificar_baselines(dados)
    resultados, total_novos = {}, 0

    for ind in config.INDICADORES:
        id_ = ind["id"]
        if ind["coletor"] == "derivado":
            continue
        if not ind["ativo"]:
            resultados[id_] = {"status": "inativo", "novos": 0, "erro": ind.get("validar") or "inativo"}
            log.append(f"INATIVO {id_}: {ind.get('validar') or 'desativado'}")
            continue
        fn = coletar_fn or REGISTRO[ind["coletor"]]
        try:
            obs = fn(ind, not dados["indicadores"][id_]["serie"], hoje)
            novos, l = integrar(dados, id_, obs, coleta_iso, hoje_iso)
            log += l
            total_novos += novos
            resultados[id_] = {"status": "ok", "novos": novos}
            ult = dados["indicadores"][id_]["serie"]
            log.append(f"OK {id_}: {novos} novo(s); última ref {ult[-1]['ref'] if ult else '-'}")
        except Desativado as e:
            resultados[id_] = {"status": "inativo", "novos": 0, "erro": str(e)}
            log.append(f"INATIVO {id_}: {e}")
        except ColetaErro as e:
            resultados[id_] = {"status": "erro", "novos": 0, "erro": str(e), "tipo": e.tipo}
            log.append(f"ERRO {id_}: {e}")
        except Exception as e:  # defeito de código: isola o indicador e segue com os demais
            resultados[id_] = {"status": "erro", "novos": 0, "erro": f"{type(e).__name__}: {e}", "tipo": "codigo"}
            log.append(f"ERRO {id_}: falha interna {type(e).__name__}: {e}")

    # contingência manual: só para indicadores cujo coletor falhou ou está inativo nesta execução
    permitidos = {k for k, r in resultados.items() if r["status"] != "ok"}
    for linha in ler_manual(MANUAL_CSV):
        if linha["id"] not in permitidos:
            continue
        novos, l = integrar(dados, linha["id"], [linha], coleta_iso, hoje_iso, origem="manual")
        log += l
        if novos:
            total_novos += novos
            resultados[linha["id"]]["novos"] = resultados[linha["id"]].get("novos", 0) + novos
            log.append(f"MANUAL {linha['id']} {linha['ref']} = {linha['valor']} (contingência)")

    # indicadores calculados
    try:
        novos, l = integrar(dados, "sm_cestas", calcular_derivados(dados), coleta_iso, hoje_iso, origem="calculado")
        log += l
        total_novos += novos
        resultados["sm_cestas"] = {"status": "ok" if dados["indicadores"]["sm_cestas"]["serie"] else "inativo",
                                   "novos": novos, "erro": "aguardando cesta_sp"}
        log.append(f"OK sm_cestas: {novos} novo(s) calculado(s)")
    except Exception as e:
        resultados["sm_cestas"] = {"status": "erro", "novos": 0, "erro": str(e), "tipo": "codigo"}
        log.append(f"ERRO sm_cestas: {e}")

    for id_ in travar_baselines(dados, coleta_iso):
        b = dados["indicadores"][id_]["baseline"]
        log.append(f"LINHA DE BASE travada {id_}: {b['valor']} (ref {b['ref']})")

    if total_novos == 0:
        log.append("SEM DADOS NOVOS nesta semana")
    dados["coletas"].append({"data": coleta_iso, "inicio": agora.isoformat(timespec="seconds"),
                             "novos": total_novos, "log": log})
    arquivados = particionar(dados, hoje)
    if arquivados:
        dados["coletas"][-1]["log"].append(f"ROTAÇÃO: logs dos anos {arquivados} movidos para data/arquivo/")
    atualizar_saude(saude, resultados, dados, hoje, coleta_iso)
    saude["ultima_execucao"] = {"data": coleta_iso, "resultados": resultados}
    salvar("dados.json", dados)
    salvar("saude.json", saude)
    return dados, saude


def liberar(id_, ref, motivo):
    dados = carregar("dados.json", None)
    q = [x for x in dados["quarentena"] if x["id"] == id_ and x["ref"] == ref]
    if not q:
        sys.exit(f"Nada em quarentena para {id_} {ref}")
    item = q[-1]
    reg = dados["indicadores"][id_]
    if any(p["ref"] == ref for p in reg["serie"]):
        sys.exit("A série já tem essa referência")
    reg["serie"].append({"ref": ref, "valor": item["valor"], "coleta": item["coleta"],
                         "fonte": config.CATALOGO[id_]["fonte"], "url": item.get("url"),
                         "origem": f"liberado da quarentena em {date.today()}: {motivo}"})
    reg["serie"].sort(key=lambda p: p["ref"])
    dados["quarentena"].remove(item)
    dados["coletas"].append({"data": date.today().isoformat(), "novos": 1,
                             "log": [f"LIBERAÇÃO MANUAL {id_} {ref} = {item['valor']}: {motivo}"]})
    travar_baselines(dados, date.today().isoformat())
    salvar("dados.json", dados)
    print(f"Liberado {id_} {ref}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje")
    ap.add_argument("--liberar", nargs=2, metavar=("ID", "REF"))
    ap.add_argument("--motivo", default="conferido na fonte oficial")
    a = ap.parse_args()
    if a.liberar:
        liberar(a.liberar[0], a.liberar[1], a.motivo)
    else:
        d, s = executar(date.fromisoformat(a.hoje) if a.hoje else None)
        print("\n".join(d["coletas"][-1]["log"]))
        print(f"Status geral: {s['status_geral']}")
