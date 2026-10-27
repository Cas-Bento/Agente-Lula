"""DIEESE, Pesquisa Nacional da Cesta Básica (página HTML com tabela por capital).

Parser defensivo: exige (1) uma tabela com cabeçalho contendo "Valor", (2) uma linha cujo
primeiro campo é a cidade configurada e (3) o mês de referência por extenso na página.
Se qualquer item faltar, falha com LayoutErro e nada é gravado.
VALIDAR: a URL em config.py (params.url) e os rótulos do cabeçalho.
"""
from html.parser import HTMLParser

from coletores.util import Desativado, LayoutErro, http_get, mes_por_extenso, num


class _Tabelas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabelas, self._t, self._l, self._c, self.texto = [], None, None, None, []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._l = []
        elif tag in ("td", "th") and self._l is not None:
            self._c = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._c is not None:
            self._l.append(" ".join("".join(self._c).split()))
            self._c = None
        elif tag == "tr" and self._l is not None:
            self._t.append(self._l)
            self._l = None
        elif tag == "table" and self._t is not None:
            self.tabelas.append(self._t)
            self._t = None

    def handle_data(self, d):
        self.texto.append(d)
        if self._c is not None:
            self._c.append(d)


def parse(html, url, cidade):
    p = _Tabelas()
    p.feed(html)
    ref = mes_por_extenso(" ".join(p.texto))
    if not ref:
        raise LayoutErro("DIEESE: mês de referência não encontrado na página")
    for t in p.tabelas:
        if not t:
            continue
        cab = [c.lower() for c in t[0]]
        col = next((i for i, c in enumerate(cab) if "valor" in c), None)
        if col is None:
            continue
        for linha in t[1:]:
            if linha and linha[0].strip().lower() == cidade.lower() and len(linha) > col:
                v = num(linha[col])
                if v is None:
                    raise LayoutErro(f"DIEESE: valor ilegível para {cidade}: {linha[col]!r}")
                return [{"ref": ref, "valor": v, "url": url}]
    raise LayoutErro(f"DIEESE: linha '{cidade}' ou coluna 'Valor' não encontrada")


def coletar(ind, primeira, hoje):
    url = ind["params"].get("url")
    if not url:
        raise Desativado("DIEESE: URL não configurada (VALIDAR)")
    return parse(http_get(url).decode("utf-8", errors="replace"), url, ind["params"]["cidade"])
