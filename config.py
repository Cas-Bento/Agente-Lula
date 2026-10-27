"""Catálogo de indicadores e parâmetros operacionais.

Convenções:
- "ref" é sempre ISO AAAA-MM-DD. Mensal = dia 01 do mês de referência; trimestral = dia 01
  do último mês do trimestre; anual = AAAA-12-01; diário = a própria data.
- "melhor": "alto", "baixo" ou "neutro" (define a cor no dashboard).
- "faixa": (mínimo, máximo) plausível. Fora disso, o valor vai para a quarentena.
- "var_max": ("abs", x) para variação absoluta máxima entre observações consecutivas,
  ("rel", x) para variação relativa máxima (0.10 = 10%).
- "atraso_max_dias": idade máxima aceitável da última referência (hoje - ref) antes do alerta
  de "dado atrasado". Regra: duração do período + defasagem típica de divulgação + ~10 dias
  de tolerância (ex.: IPCA ref. 01/09 só é sucedido em ~10/11, ou seja, 70 dias; limite 80). None = periodicidade esporádica.
- "ativo": False desliga o coletor automático (o indicador continua no dashboard e pode
  receber dado via manual.csv). Todo item com "validar" precisa de conferência (ver README).
"""

BASELINE_DATA = "2026-10-26"
USER_AGENT = "MonitorIndicadoresBR/1.0 (+https://github.com/; coleta semanal de dados oficiais)"
TIMEOUT_S = 30
TENTATIVAS = 3
BACKOFF_BASE_S = 2  # espera 2s, 4s entre tentativas
HISTORICO_INICIAL_ANOS = 2  # na primeira coleta, busca 2 anos para dar contexto aos gráficos
LIMITE_DADOS_BYTES = 4_000_000  # acima disso, logs e quarentena antigos vão para data/arquivo/
FALHAS_ALERTA_CRITICO = 2
DOMINIOS_OFICIAIS = (
    "bcb.gov.br", "ibge.gov.br", "tesourotransparente.gov.br", "tesouro.gov.br",
    "gov.br", "dieese.org.br",
)

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
SIDRA = "https://apisidra.ibge.gov.br/values/{path}"
OLINDA_FOCUS = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
                "ExpectativasMercadoAnuais")

EIXOS = ["Custo de vida", "Câmbio", "Juros", "Fiscal", "Trabalho", "Social",
         "Atividade", "Expectativas", "Externo"]


def _sgs(id_, nome, codigo, un, eixo, melhor, per, atraso, faixa, var, cal, validar=None):
    return dict(id=id_, nome=nome, un=un, eixo=eixo, melhor=melhor,
                fonte="Banco Central do Brasil (SGS)", coletor="bcb_sgs",
                params={"codigo": codigo},
                url=f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json",
                periodicidade=per, atraso_max_dias=atraso, faixa=faixa, var_max=var,
                calendario=cal, ativo=True, validar=validar)


def _sidra(id_, nome, path, per_tipo, un, eixo, melhor, per, atraso, faixa, var, cal,
           validar=None, ativo=True):
    return dict(id=id_, nome=nome, un=un, eixo=eixo, melhor=melhor,
                fonte="IBGE (SIDRA)", coletor="ibge_sidra",
                params={"path": path, "periodo": per_tipo},
                url=("https://sidra.ibge.gov.br/tabela/" + path.split("/")[1]) if path else
                "https://sidra.ibge.gov.br/",
                periodicidade=per, atraso_max_dias=atraso, faixa=faixa, var_max=var,
                calendario=cal, ativo=ativo and bool(path), validar=validar)


def _focus(id_, nome, indicador, un, melhor, faixa, var):
    return dict(id=id_, nome=nome, un=un, eixo="Expectativas", melhor=melhor,
                fonte="Banco Central do Brasil (Focus, API Olinda)", coletor="bcb_focus",
                params={"indicador": indicador},
                url="https://www.bcb.gov.br/publicacoes/focus",
                periodicidade="semanal", atraso_max_dias=15, faixa=faixa, var_max=var,
                calendario="Semanal, segunda-feira (dados da sexta anterior)",
                ativo=True, validar=None)


INDICADORES = [
    # ---------------- Banco Central, SGS (códigos conferidos na API em 27/10/2026) -------------
    _sgs("dolar", "Dólar PTAX venda", 1, "R$", "Câmbio", "neutro", "diaria", 7,
         (1, 15), ("rel", 0.10), "Diária, dias úteis"),
    _sgs("euro", "Euro PTAX venda", 21619, "R$", "Câmbio", "neutro", "diaria", 7,
         (1, 15), ("rel", 0.10), "Diária, dias úteis"),
    _sgs("selic", "Selic meta", 432, "% a.a.", "Juros", "baixo", "diaria", 10,
         (0, 40), ("abs", 3), "Muda nas reuniões do Copom (8 por ano)"),
    _sgs("ipca_m", "IPCA mensal", 433, "%", "Custo de vida", "baixo", "mensal", 80,
         (-3, 5), ("abs", 3), "Mensal, por volta do dia 10 do mês seguinte"),
    _sgs("ipca_12", "IPCA acumulado 12 meses", 13522, "%", "Custo de vida", "baixo",
         "mensal", 80, (-5, 50), ("abs", 3), "Mensal, junto com o IPCA"),
    _sgs("dbgg", "Dívida Bruta do Governo Geral", 13762, "% PIB", "Fiscal", "baixo",
         "mensal", 100, (30, 150), ("abs", 5), "Mensal, Estatísticas Fiscais do BCB (~30 dias após o mês)"),
    _sgs("dlsp", "Dívida Líquida do Setor Público", 4513, "% PIB", "Fiscal", "baixo",
         "mensal", 100, (0, 150), ("abs", 5), "Mensal, Estatísticas Fiscais do BCB"),
    # VALIDAR: 5793 = NFSP, resultado primário, setor público consolidado, 12 meses, % PIB.
    # Convenção NFSP: valor POSITIVO = DÉFICIT; negativo = superávit. Por isso "melhor": baixo.
    _sgs("primario", "Resultado primário 12m (NFSP: + déficit)", 5793, "% PIB", "Fiscal",
         "baixo", "mensal", 100, (-10, 15), ("abs", 3), "Mensal, Estatísticas Fiscais do BCB",
         validar="Confirmar no SGS que 5793 é o resultado primário 12 meses % PIB do setor público consolidado"),
    # 24364 = IBC-Br COM ajuste sazonal. O 24363 citado no briefing é a série SEM ajuste.
    _sgs("ibcbr", "IBC-Br dessazonalizado", 24364, "índice", "Atividade", "alto", "mensal",
         115, (50, 300), ("rel", 0.15), "Mensal, cerca de 45 dias após o mês",
         validar="Confirmar no SGS a descrição 'com ajuste sazonal' da série 24364"),
    _sgs("salario_min", "Salário mínimo vigente", 1619, "R$", "Custo de vida", "neutro",
         "mensal", 45, (500, 10000), ("rel", 0.25),
         "Reajuste anual (janeiro); a série do BCB traz meses futuros, descartados pelo coletor"),

    # ---------------- Banco Central, Focus -------------------------------------------------
    _focus("focus_ipca", "IPCA esperado (ano seguinte)", "IPCA", "%", "baixo", (-5, 30), ("abs", 2)),
    _focus("focus_selic", "Selic esperada (ano seguinte)", "Selic", "% a.a.", "baixo", (0, 40), ("abs", 3)),
    _focus("focus_pib", "PIB esperado (ano seguinte)", "PIB Total", "%", "alto", (-15, 15), ("abs", 3)),

    # ---------------- IBGE, SIDRA (conferidos na API em 27/10/2026, exceto os inativos) ------
    _sidra("desocup", "Taxa de desocupação", "t/6381/n1/all/v/4099", "mensal", "%", "Trabalho",
           "baixo", "mensal", 100, (0, 50), ("abs", 3),
           "Mensal (trimestre móvel), PNAD Contínua, fim do mês seguinte"),
    _sidra("ocup", "Nível de ocupação", "t/6379/n1/all/v/4097", "mensal", "%", "Trabalho",
           "alto", "mensal", 100, (20, 90), ("abs", 5), "Mensal (trimestre móvel), PNAD Contínua"),
    _sidra("informal", "Taxa de informalidade", "t/8529/n1/all/v/12466", "trimestral", "%",
           "Trabalho", "baixo", "trimestral", 180, (10, 80), ("abs", 5),
           "Trimestral, PNAD Contínua (trimestres civis)"),
    _sidra("renda_real", "Rendimento médio real habitual", "t/6390/n1/all/v/5933", "mensal",
           "R$", "Trabalho", "alto", "mensal", 100, (500, 20000), ("rel", 0.15),
           "Mensal (trimestre móvel), PNAD Contínua"),
    _sidra("pib_tri", "PIB trimestral, variação anual", "t/5932/n1/all/v/6561/c11255/90707",
           "trimestral", "%", "Atividade", "alto", "trimestral", 195, (-30, 30), ("abs", 15),
           "Trimestral, Contas Nacionais (~60 dias após o trimestre)"),
    _sidra("gini", "Índice de Gini (rendimento domiciliar per capita)",
           "t/7435/n1/all/v/10681", "anual", "índice", "Social", "baixo", "anual", 720,
           (0.3, 0.8), ("abs", 0.05), "Anual, PNAD Contínua rendimentos (2º semestre)"),
    _sidra("inseg_grave", "Insegurança alimentar grave (EBIA)", None, "anual", "% domicílios",
           "Social", "baixo", "esporadica", None, (0, 50), ("abs", 10),
           "Esporádica (suplemento da PNAD Contínua)",
           validar="Identificar a tabela SIDRA do suplemento de segurança alimentar"),
    _sidra("pobreza", "Pessoas em pobreza (SIS)", None, "anual", "% população", "Social",
           "baixo", "anual", 720, (0, 80), ("abs", 10),
           "Anual, Síntese de Indicadores Sociais (dezembro)",
           validar="SIS é publicada em planilhas; confirmar se há tabela SIDRA equivalente"),
    _sidra("ext_pobreza", "Pessoas em extrema pobreza (SIS)", None, "anual", "% população",
           "Social", "baixo", "anual", 720, (0, 50), ("abs", 10),
           "Anual, Síntese de Indicadores Sociais (dezembro)",
           validar="Idem pobreza"),

    # ---------------- Fontes sem API REST formal -------------------------------------------
    dict(id="cesta_sp", nome="Cesta básica São Paulo", un="R$", eixo="Custo de vida",
         melhor="baixo", fonte="DIEESE (Pesquisa Nacional da Cesta Básica)", coletor="dieese",
         params={"url": None, "cidade": "São Paulo"},  # VALIDAR: URL estável da tabela mensal
         url="https://www.dieese.org.br/cesta/", periodicidade="mensal", atraso_max_dias=75,
         faixa=(100, 5000), var_max=("rel", 0.20),
         calendario="Mensal, primeira quinzena do mês seguinte", ativo=False,
         validar="Definir a URL da tabela mensal do DIEESE e conferir o layout"),
    dict(id="sm_cestas", nome="Salário mínimo / cesta SP", un="cestas", eixo="Custo de vida",
         melhor="alto", fonte="Calculado: BCB SGS 1619 / DIEESE cesta SP", coletor="derivado",
         params={"formula": "salario_min(ref) / cesta_sp(ref)"},
         url="https://www.dieese.org.br/cesta/", periodicidade="mensal", atraso_max_dias=75,
         faixa=(0.3, 10), var_max=("rel", 0.25),
         calendario="Recalculado quando sai nova cesta", ativo=True, validar=None),
    dict(id="caged", nome="Saldo do Novo Caged", un="vagas", eixo="Trabalho", melhor="alto",
         fonte="Ministério do Trabalho e Emprego (Novo Caged)", coletor="mte_caged",
         params={"url": None, "rotulo_linha": "Brasil", "rotulo_coluna": "Saldo"},  # VALIDAR
         url="https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/novo-caged",
         periodicidade="mensal", atraso_max_dias=100, faixa=(-3_000_000, 3_000_000),
         var_max=("abs", 1_500_000), calendario="Mensal, ~30 dias após o mês", ativo=False,
         validar="Definir a URL da planilha oficial mensal e os rótulos de linha/coluna"),
    dict(id="dpf", nome="Dívida Pública Federal (estoque)", un="R$ trilhões", eixo="Fiscal",
         melhor="baixo", fonte="Tesouro Nacional (Tesouro Transparente/CKAN)", coletor="tesouro",
         params={"dataset": None, "col_data": None, "col_valor": None, "divisor": 1e12},  # VALIDAR
         url="https://www.tesourotransparente.gov.br/ckan/dataset",
         periodicidade="mensal", atraso_max_dias=95, faixa=(1, 50), var_max=("rel", 0.15),
         calendario="Mensal, Relatório Mensal da Dívida (~25 dias após o mês)", ativo=False,
         validar="Definir o id do dataset CKAN e as colunas de data e valor"),
    dict(id="cds", nome="Risco-país CDS 5 anos", un="pontos", eixo="Externo", melhor="baixo",
         fonte="Sem fonte gratuita e estável identificada", coletor="cds", params={},
         url="", periodicidade="diaria", atraso_max_dias=None, faixa=(0, 2000),
         var_max=("rel", 0.5), calendario="Diária (mercado)", ativo=False,
         validar="Desativado por decisão de arquitetura; ver README"),
]

CATALOGO = {i["id"]: i for i in INDICADORES}
