"""Utilitários compartilhados pelos coletores: HTTP com retentativa, parsing de números e datas."""
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime

import config


class ColetaErro(Exception):
    """Falha de coleta (rede, HTTP, resposta vazia)."""
    tipo = "rede"


class LayoutErro(ColetaErro):
    """A resposta chegou, mas o formato não é o esperado. Nunca gravar nada nesse caso."""
    tipo = "layout"


class Desativado(ColetaErro):
    tipo = "desativado"


def http_get(url, tentativas=None, timeout=None, _sleep=time.sleep):
    tentativas = tentativas or config.TENTATIVAS
    timeout = timeout or config.TIMEOUT_S
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": config.USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                corpo = r.read()
                if not corpo:
                    raise ColetaErro(f"resposta vazia de {url}")
                return corpo
        except urllib.error.HTTPError as e:
            ultimo = ColetaErro(f"HTTP {e.code} em {url}")
            if e.code in (400, 401, 403, 404):  # erro do cliente: repetir não resolve
                break
        except (urllib.error.URLError, TimeoutError, OSError, ColetaErro) as e:
            ultimo = ColetaErro(f"{type(e).__name__}: {e} em {url}")
        if i < tentativas - 1:
            _sleep(config.BACKOFF_BASE_S * (2 ** i))
    raise ultimo


def http_json(url, **kw):
    corpo = http_get(url, **kw)
    try:
        return json.loads(corpo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise LayoutErro(f"JSON inválido em {url}: {e}") from e


def num(txt):
    """Converte número em formato brasileiro ou internacional. Retorna None se não for número.
    Não arredonda: preserva o valor como publicado."""
    if txt is None:
        return None
    if isinstance(txt, (int, float)):
        v = float(txt)
        return v if math.isfinite(v) else None
    s = str(txt).strip().replace("R$", "").replace("\xa0", "").replace(" ", "")
    if s in ("", "-", "...", "..", "X", "x", "NA", "null"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def data_br(txt):
    """dd/mm/aaaa -> AAAA-MM-DD"""
    try:
        return datetime.strptime(txt.strip(), "%d/%m/%Y").date().isoformat()
    except (ValueError, AttributeError) as e:
        raise LayoutErro(f"data inesperada: {txt!r}") from e


MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
     "setembro", "outubro", "novembro", "dezembro"], start=1)}


def mes_por_extenso(texto):
    """Procura 'outubro de 2026' / 'outubro/2026' num texto e devolve AAAA-MM-01."""
    m = re.search(r"(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|"
                  r"outubro|novembro|dezembro)\s*(?:de|/)\s*(\d{4})", texto, re.I)
    if not m:
        return None
    nome = m.group(1).lower().replace("marco", "março")
    return f"{int(m.group(2)):04d}-{MESES[nome]:02d}-01"


def periodo_sidra(codigo, tipo):
    """Converte o código de período do SIDRA para ref ISO.
    mensal '202608' -> 2026-08-01 | trimestral '202602' -> 2026-06-01 | anual '2025' -> 2025-12-01"""
    c = str(codigo).strip()
    if tipo == "anual":
        if not re.fullmatch(r"\d{4}", c):
            raise LayoutErro(f"período anual inesperado: {c}")
        return f"{c}-12-01"
    if not re.fullmatch(r"\d{6}", c):
        raise LayoutErro(f"período inesperado: {c}")
    ano, n = int(c[:4]), int(c[4:])
    if tipo == "mensal":
        if not 1 <= n <= 12:
            raise LayoutErro(f"mês inválido: {c}")
        return f"{ano:04d}-{n:02d}-01"
    if tipo == "trimestral":
        if not 1 <= n <= 4:
            raise LayoutErro(f"trimestre inválido: {c}")
        return f"{ano:04d}-{n * 3:02d}-01"
    raise LayoutErro(f"tipo de período desconhecido: {tipo}")


def hoje():
    return date.today()
