"""Tesouro Nacional, Tesouro Transparente (CKAN): estoque da Dívida Pública Federal.

Dataset "Estoque da Dívida Pública Federal" (id 0998f610-bc25-4ce3-b32c-a873447500c2).
Segundo o documento de metadados do Tesouro, o CSV traz uma linha por título/contrato e mês,
com as colunas: Título/Contrato, Vencimento, Valor do Estoque (R$ correntes), Quantidade do
Estoque, Mês do estoque (mmm/aaaa), Classe da carteira (Mercado ou Bacen) e Tipo de dívida
(interna ou externa).

Indicador gravado: soma do Valor do Estoque da classe "Mercado" por mês, em R$ trilhões.
É o conceito de DPF em poder do público usado no Relatório Mensal da Dívida; títulos na
carteira do Banco Central ficam de fora. Os nomes das colunas são localizados por palavra-chave
(sem acento, sem caixa) para tolerar pequenas variações de grafia; se alguma coluna não for
encontrada, LayoutErro e nada é gravado.
"""
import csv
import io
import re
import unicodedata
from urllib.parse import quote

from coletores.util import Desativado, LayoutErro, http_get, http_json

CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id={}"
MESES_ABREV = {m: i for i, m in enumerate(
    ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"], start=1)}


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def ref_mes(txt):
    """'set/2026', 'Set/26', '09/2026', '01/09/2026' ou '2026-09' -> '2026-09-01'."""
    s = _norm(txt)
    m = re.fullmatch(r"([a-z]{3})[a-z]*[/\-\s]+(\d{2,4})", s)
    if m and m.group(1) in MESES_ABREV:
        ano = int(m.group(2))
        ano = (ano + 2000 if ano < 70 else ano + 1900) if ano < 100 else ano
        return f"{ano:04d}-{MESES_ABREV[m.group(1)]:02d}-01"
    for pad, fmt in ((r"\d{2}/(\d{2})/(\d{4})", "{1}-{0}-01"), (r"(\d{2})/(\d{4})", "{1}-{0}-01"),
                     (r"(\d{4})-(\d{2})(?:-\d{2})?", "{0}-{1}-01")):
        m = re.fullmatch(pad, s)
        if m:
            return fmt.format(*m.groups())
    raise LayoutErro(f"Tesouro: mês do estoque inesperado {txt!r}")


def valor(txt):
    """Número em reais, formato brasileiro ou internacional, sem arredondar."""
    s = str(txt or "").strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if s in ("", "-", "..."):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _coluna(campos, *palavras):
    for c in campos:
        n = _norm(c)
        if all(p in n for p in palavras):
            return c
    return None


def parse_csv(texto, url, divisor=1e12, classe="mercado", meses=24):
    amostra = texto[:4000]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=";,")
    except csv.Error:
        dialeto = csv.excel
    leitor = csv.DictReader(io.StringIO(texto), dialect=dialeto)
    campos = leitor.fieldnames or []
    c_valor = _coluna(campos, "valor", "estoque")
    c_mes = _coluna(campos, "mes", "estoque")
    c_classe = _coluna(campos, "classe")
    if not (c_valor and c_mes and c_classe):
        raise LayoutErro(f"Tesouro: colunas de valor/mês/classe não encontradas: {campos}")
    soma, invalidas = {}, 0
    for linha in leitor:
        if _norm(linha.get(c_classe)) != classe:
            continue
        v = valor(linha.get(c_valor))
        if v is None:
            invalidas += 1
            continue
        ref = ref_mes(linha.get(c_mes))
        soma[ref] = soma.get(ref, 0.0) + v
    if not soma:
        raise LayoutErro(f"Tesouro: nenhuma linha da classe '{classe}' com valor")
    if invalidas > 50:
        raise LayoutErro(f"Tesouro: {invalidas} linhas com valor ilegível; layout provavelmente mudou")
    obs = [{"ref": r, "valor": v / divisor, "url": url} for r, v in sorted(soma.items())]
    return obs[-meses:]


def recurso_csv(meta):
    recursos = (meta.get("result") or {}).get("resources") or []
    csvs = [r for r in recursos if str(r.get("format", "")).upper() == "CSV" and r.get("url")]
    if not csvs:
        raise LayoutErro("Tesouro: dataset sem recurso CSV")
    preferidos = [r for r in csvs if "estoque" in _norm(r.get("name")) or "estoque" in _norm(r.get("url"))]
    return (preferidos or csvs)[0]["url"]


def coletar(ind, primeira, hoje, _json=http_json, _get=http_get):
    p = ind["params"]
    if not p.get("dataset"):
        raise Desativado("Tesouro: dataset não configurado")
    url = recurso_csv(_json(CKAN.format(quote(p["dataset"]))))
    bruto = _get(url)
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")  # arquivos do governo às vezes vêm em ISO-8859-1
    return parse_csv(texto, url, p.get("divisor", 1e12), p.get("classe", "mercado"),
                     24 if primeira else 6)
