"""DIEESE, Pesquisa Nacional da Cesta Básica (Conab/DIEESE).

Fonte: boletim mensal em PDF, com endereço previsível
    https://www.dieese.org.br/analisecestabasica/AAAA/AAAAMMcestabasica.pdf
A Tabela 1 do boletim traz, por capital: "Valor da cesta", variação mensal, % do salário
mínimo líquido e tempo de trabalho. Ex.: "São Paulo 915,01 -5,23 61,02 124h11m ...".

Regras do parser (defensivo):
1. o mês de referência vem do endereço e precisa constar por extenso no texto do PDF;
2. a cidade precisa aparecer seguida de um valor em reais e de uma variação percentual
   (padrão da Tabela 1); menções no corpo do texto, como "(R$ 915,01)", não casam;
3. se algo faltar, LayoutErro: nada é gravado e o valor anterior é mantido.
Meses ainda não publicados (HTTP 404) são ignorados.
"""
import io
import re
import unicodedata
from datetime import date

from coletores.util import ColetaErro, LayoutErro, MESES, http_get, num

URL = "https://www.dieese.org.br/analisecestabasica/{ano}/{ano}{mes:02d}cestabasica.pdf"
MESES_PRIMEIRA = 24   # histórico para os gráficos na primeira coleta
MESES_ROTINA = 4      # janela semanal: cobre atrasos de publicação


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def texto_pdf(conteudo):
    from pypdf import PdfReader  # import tardio: só exige pypdf quando o coletor roda
    leitor = PdfReader(io.BytesIO(conteudo))
    # A Tabela 1 fica nas primeiras páginas; limitar evita ler anexos longos.
    return "\n".join((p.extract_text() or "") for p in leitor.pages[:6])


def parse_texto(texto, ref, url, cidade):
    ano, mes = int(ref[:4]), int(ref[5:7])
    nome_mes = _sem_acento([m for m, i in MESES.items() if i == mes][0])
    plano = _sem_acento(" ".join(texto.split()))
    if not re.search(rf"{nome_mes}\s*(de|/)\s*{ano}", plano):
        raise LayoutErro(f"DIEESE: mês {nome_mes}/{ano} não consta no boletim {url}")
    padrao = rf"{re.escape(_sem_acento(cidade))}\s+(\d{{1,2}}\.\d{{3}},\d{{2}}|\d{{3,4}},\d{{2}})\s+[-+]?\d+,\d{{1,2}}"
    m = re.search(padrao, plano)
    if not m:
        raise LayoutErro(f"DIEESE: linha '{cidade}' da Tabela 1 não encontrada em {url}")
    v = num(m.group(1))
    if v is None:
        raise LayoutErro(f"DIEESE: valor ilegível para {cidade}: {m.group(1)!r}")
    return {"ref": ref, "valor": v, "url": url}


def meses_alvo(hoje, n):
    """Meses de referência a tentar, do mais antigo ao mais recente. O boletim do mês M sai
    no início de M+1, então o mês corrente nunca tem boletim."""
    a, m = hoje.year, hoje.month
    saida = []
    for _ in range(n):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        saida.append(date(a, m, 1))
    return sorted(saida)


def coletar(ind, primeira, hoje, _get=http_get, _texto=texto_pdf):
    cidade = ind["params"]["cidade"]
    obs, erros, ultimo_layout = [], [], None
    for d in meses_alvo(hoje, MESES_PRIMEIRA if primeira else MESES_ROTINA):
        url = URL.format(ano=d.year, mes=d.month)
        try:
            conteudo = _get(url)
        except ColetaErro as e:
            if "HTTP 404" in str(e):
                continue  # boletim ainda não publicado (ou mês sem pesquisa)
            erros.append(str(e))
            continue
        try:
            obs.append(parse_texto(_texto(conteudo), d.isoformat(), url, cidade))
            ultimo_layout = None
        except LayoutErro as e:
            ultimo_layout = e  # boletim antigo com layout diferente: o mês é pulado, nada é gravado
        except Exception as e:  # PDF corrompido ou ilegível
            ultimo_layout = LayoutErro(f"DIEESE: PDF ilegível em {url}: {type(e).__name__}")
    if ultimo_layout is not None:
        raise ultimo_layout  # o boletim mais recente não foi lido: provável mudança de layout
    if not obs:
        raise ColetaErro("DIEESE: nenhum boletim obtido. " + ("; ".join(erros) or "todos os meses com HTTP 404"))
    return obs
