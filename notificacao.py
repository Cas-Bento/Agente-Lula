"""Notificações: e-mail semanal (SMTP) e Issues do GitHub (abre em falha, fecha na recuperação).

Uso: python notificacao.py [--email] [--issues]   (sem flags = ambos)
Nenhuma falha aqui interrompe a rotina: erros são impressos e o código sai com 0.
"""
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from datetime import date
from email.message import EmailMessage

from coletor import carregar
from analista import DIR_REL

ROTULO_FALHA = "monitor-coleta"
ROTULO_QUAR = "monitor-quarentena"
ROTULO_INTEG = "monitor-integridade"


def url_dashboard():
    if os.environ.get("PAGES_URL"):
        return os.environ["PAGES_URL"].rstrip("/") + "/dashboard.html"
    repo = os.environ.get("GITHUB_REPOSITORY", "usuario/repositorio")
    dono, nome = repo.split("/", 1)
    return f"https://{dono}.github.io/{nome}/dashboard.html"


# ------------------------------------------------------------------------------ e-mail
def enviar_email(hoje=None):
    hoje = hoje or date.today()
    req = ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_DESTINO")
    faltam = [k for k in req if not os.environ.get(k)]
    if faltam:
        print(f"AVISO e-mail não enviado: secrets ausentes {faltam}")
        return False
    saude = carregar("saude.json", {})
    rel = os.path.join(DIR_REL, f"{hoje.isoformat()}.md")
    corpo = open(rel, encoding="utf-8").read() if os.path.exists(rel) else "Relatório não gerado nesta execução."
    st = saude.get("status_geral", "n/d")
    msg = EmailMessage()
    msg["Subject"] = f"[Monitor BR] Coleta {hoje.strftime('%d/%m/%Y')} | status {st}"
    msg["From"] = os.environ.get("EMAIL_REMETENTE", os.environ["SMTP_USER"])
    msg["To"] = os.environ["EMAIL_DESTINO"]
    msg.set_content(f"Dashboard: {url_dashboard()}\n\n{corpo}")
    porta = int(os.environ.get("SMTP_PORT") or "587")
    try:
        if porta == 465:
            with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], porta, timeout=30) as s:
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(os.environ["SMTP_HOST"], porta, timeout=30) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                s.send_message(msg)
        print("E-mail enviado")
        return True
    except Exception as e:
        print(f"AVISO falha no envio de e-mail: {type(e).__name__}: {e}")
        return False


# ------------------------------------------------------------------------------ GitHub Issues
def gh(metodo, caminho, corpo=None):
    token, repo = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{caminho}", method=metodo,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "monitor-br"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def planejar_issues(saude, dados, abertas):
    """Função pura (testável): devolve lista de ações [('abrir'|'comentar'|'fechar', ...)]."""
    acoes = []
    por_titulo = {i["title"]: i for i in abertas}
    hoje = (dados.get("coletas") or [{}])[-1].get("data")
    for id_, s in (saude.get("indicadores") or {}).items():
        titulo = f"[coleta] Falha no indicador {id_}"
        aberta = por_titulo.get(titulo)
        if s.get("status") in ("vermelho", "amarelo") and s.get("ultimo_erro") and s.get("falhas_consecutivas", 0) >= 1:
            critico = s["falhas_consecutivas"] >= 2
            corpo = (f"**Fonte:** {s.get('fonte')}\n\n**Falhas consecutivas:** {s['falhas_consecutivas']}"
                     f"{' (CRÍTICO)' if critico else ''}\n\n**Erro:**\n```\n{s['ultimo_erro']}\n```\n\n"
                     f"**Sugestão:** {s.get('sugestao', '')}\n\nÚltimo valor válido mantido: ref {s.get('ultima_ref')}. "
                     f"Contingência: manual.csv (ver README). Esta Issue fecha sozinha quando a coleta voltar a funcionar.")
            rotulos = [ROTULO_FALHA] + (["critico"] if critico else [])
            acoes.append(("comentar", aberta["number"], corpo, rotulos) if aberta else ("abrir", titulo, corpo, rotulos))
        elif aberta and s.get("status") in ("verde", "cinza", "amarelo") and not s.get("ultimo_erro"):
            acoes.append(("fechar", aberta["number"], f"Coleta normalizada em {hoje}. Fechamento automático."))
    for q in dados.get("quarentena", []):
        if q.get("coleta") == hoje:
            titulo = f"[quarentena] {q['id']} {q['ref']}"
            if titulo not in por_titulo:
                acoes.append(("abrir", titulo,
                              f"Valor **{q['valor']}** rejeitado na validação de sanidade.\n\nMotivo: {q['motivo']}\n\n"
                              f"URL: {q.get('url')}\n\nSe o valor estiver correto na fonte oficial, libere com:\n"
                              f"`python coletor.py --liberar {q['id']} {q['ref']} --motivo \"conferido na fonte\"`",
                              [ROTULO_QUAR]))
    for a in saude.get("integridade") or []:
        titulo = "[integridade] Linha de base alterada"
        if titulo not in por_titulo and not any(x[0] == "abrir" and x[1] == titulo for x in acoes):
            acoes.append(("abrir", titulo, "\n".join(f"- {x}" for x in saude["integridade"]) +
                          "\n\nRestaurar data/dados.json a partir do histórico do Git ou da Release de backup.",
                          [ROTULO_INTEG, "critico"]))
    return acoes


def sincronizar_issues():
    if not (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY")):
        print("AVISO Issues não sincronizadas: GITHUB_TOKEN/GITHUB_REPOSITORY ausentes")
        return
    saude, dados = carregar("saude.json", {}), carregar("dados.json", {})
    abertas = []
    for rot in (ROTULO_FALHA, ROTULO_QUAR, ROTULO_INTEG):
        abertas += gh("GET", f"/issues?state=open&labels={rot}&per_page=100") or []
    for acao in planejar_issues(saude, dados, abertas):
        try:
            if acao[0] == "abrir":
                gh("POST", "/issues", {"title": acao[1], "body": acao[2], "labels": acao[3]})
            elif acao[0] == "comentar":
                gh("POST", f"/issues/{acao[1]}/comments", {"body": acao[2]})
                gh("POST", f"/issues/{acao[1]}/labels", {"labels": acao[3]})
            elif acao[0] == "fechar":
                gh("POST", f"/issues/{acao[1]}/comments", {"body": acao[2]})
                gh("PATCH", f"/issues/{acao[1]}", {"state": "closed"})
            print(f"Issue: {acao[0]} {acao[1]}")
        except urllib.error.HTTPError as e:
            print(f"AVISO falha na Issue {acao[1]}: HTTP {e.code}")


if __name__ == "__main__":
    flags = set(sys.argv[1:]) or {"--email", "--issues"}
    try:
        if "--issues" in flags:
            sincronizar_issues()
    except Exception as e:
        print(f"AVISO falha geral em Issues: {type(e).__name__}: {e}")
    if "--email" in flags:
        enviar_email()
