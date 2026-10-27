"""MTE, Novo Caged (planilha oficial mensal .xlsx).

Parser defensivo: localiza a coluna cujo cabeçalho contém params.rotulo_coluna e a linha cujo
primeiro campo é params.rotulo_linha; o mês de referência precisa constar por extenso em
alguma célula de título. Qualquer divergência gera LayoutErro.
VALIDAR: URL e rótulos em config.py.
"""
import io

from coletores.util import Desativado, LayoutErro, http_get, mes_por_extenso, num


def parse(conteudo, url, rotulo_linha, rotulo_coluna):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as e:  # arquivo corrompido ou formato trocado
        raise LayoutErro(f"Caged: planilha ilegível: {e}") from e
    for ws in wb.worksheets:
        linhas = [[("" if c is None else str(c)).strip() for c in r]
                  for r in ws.iter_rows(values_only=True)]
        ref = mes_por_extenso(" ".join(" ".join(r) for r in linhas[:15]))
        col = None
        for r in linhas:
            for i, c in enumerate(r):
                if col is None and rotulo_coluna.lower() in c.lower():
                    col = i
            if col is not None and r and r[0].lower() == rotulo_linha.lower():
                v = num(r[col]) if len(r) > col else None
                if v is None or not ref:
                    raise LayoutErro("Caged: valor ou mês de referência ausente")
                return [{"ref": ref, "valor": v, "url": url}]
    raise LayoutErro("Caged: rótulos não encontrados na planilha")


def coletar(ind, primeira, hoje):
    p = ind["params"]
    if not p.get("url"):
        raise Desativado("Caged: URL não configurada (VALIDAR)")
    return parse(http_get(p["url"]), p["url"], p["rotulo_linha"], p["rotulo_coluna"])
