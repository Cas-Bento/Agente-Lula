"""Gera site/dashboard.html (arquivo único) a partir do template.html com os dados embutidos."""
import glob
import json
import os
import shutil

from coletor import DATA_DIR, RAIZ, carregar
from resumo import resumir

SITE = os.environ.get("MONITOR_SITE", os.path.join(RAIZ, "site"))
DIR_REL = os.environ.get("MONITOR_RELATORIOS", os.path.join(RAIZ, "relatorios"))
MARCADOR = "/*__DADOS__*/null"


def montar(dados, saude, relatorios):
    return {
        "baseline_data": dados["baseline_data"],
        "ultima_coleta": dados["coletas"][-1]["data"] if dados["coletas"] else None,
        "total_coletas": len(dados["coletas"]),
        "indicadores": dados["indicadores"],
        "resumo": resumir(dados, saude),
        "saude": saude,
        "quarentena": dados.get("quarentena", []),
        "relatorios": relatorios,
    }


def ler_relatorios():
    arquivos = sorted(glob.glob(os.path.join(DIR_REL, "*.md")), reverse=True)
    out = []
    for a in arquivos:
        with open(a, encoding="utf-8") as f:
            out.append({"data": os.path.basename(a)[:10], "md": f.read()})
    return out


def gerar():
    dados = carregar("dados.json", None)
    if not dados:
        raise SystemExit("dados.json inexistente: rode o coletor antes")
    saude = carregar("saude.json", {})
    with open(os.path.join(RAIZ, "template.html"), encoding="utf-8") as f:
        tpl = f.read()
    if MARCADOR not in tpl:
        raise SystemExit("template.html sem o marcador de dados")
    blob = json.dumps(montar(dados, saude, ler_relatorios()), ensure_ascii=False)
    blob = blob.replace("</", "<\\/")  # impede que um texto feche a tag <script>
    html = tpl.replace(MARCADOR, blob)
    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    for nome in ("dashboard.html", "index.html"):
        with open(os.path.join(SITE, nome), "w", encoding="utf-8") as f:
            f.write(html)
    for nome in ("dados.json", "saude.json"):  # cópia pública para download e auditoria
        shutil.copy(os.path.join(DATA_DIR, nome), os.path.join(SITE, "data", nome))
    print(f"Dashboard: {os.path.join(SITE, 'dashboard.html')} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    gerar()
