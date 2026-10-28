# Monitor de indicadores econômicos e sociais do Brasil

Agente autônomo que, toda segunda-feira às 08h (Brasília), coleta indicadores de fontes oficiais,
grava o histórico versionado no Git, compara cada indicador com a linha de base de **26/10/2026**,
gera um relatório semanal (seções numéricas por código, interpretação por IA) e publica um
dashboard no GitHub Pages. Falhas viram Issues e alertas por e-mail.

## Fluxo de cada execução

```
pytest ─► coletor.py ─► analista.py ─► dashboard.py ─► commit ─► Pages ─► notificacao.py ─► keepalive ─► backup mensal
         (coleta,       (IA opcional,   (site/)                          (e-mail + Issues)
          validação,     nunca bloqueia)
          gravação,
          saúde)
```

Se os testes falharem, nada é gravado. Se uma fonte falhar, as demais seguem. Se a IA falhar, o
relatório sai com as seções numéricas e um aviso.

## Estrutura

```
config.py               catálogo de indicadores, faixas de sanidade, prazos de atraso
coletores/              um módulo por fonte (bcb_sgs, bcb_focus, ibge_sidra, dieese, tesouro, tesouro_rtn, anp, b3, inpe_deter)
validacao.py            faixa plausível, variação máxima, domínio oficial, data futura
coletor.py              orquestrador: dedup, revisões, quarentena, trava e selo da linha de base, saúde, rotação
resumo.py               variações contra período anterior e linha de base (código, não IA)
analista.py             relatório semanal + chamada à API da Anthropic + controle de rastreabilidade
dashboard.py            gera site/dashboard.html a partir do template.html
notificacao.py          e-mail SMTP e Issues (abre em falha, fecha na recuperação)
template.html           dashboard (Chart.js via CDN, tema escuro, responsivo)
manual.csv              CONTINGÊNCIA (id,ref,valor,url)
data/dados.json         histórico (gerado)        data/saude.json   autodiagnóstico (gerado)
data/arquivo/AAAA.json  logs antigos após rotação  relatorios/AAAA-MM-DD.md
tests/                  pytest (parsers, dedup, linha de base, sanidade, falhas, relatório, Issues)
.github/workflows/monitor.yml
```

## Implantação

1. **Criar o repositório** no GitHub e subir todos os arquivos deste pacote.
   No plano gratuito, o GitHub Pages exige repositório **público**. Os dados são públicos por natureza; nenhuma credencial fica no código.
2. **Secrets** (Settings > Secrets and variables > Actions > New repository secret):
   `ANTHROPIC_API_KEY`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_DESTINO` e, opcionalmente, `SMTP_PORT` (padrão 587; use 465 para SSL).
   Para Gmail, use uma senha de app, nunca a senha da conta.
3. **Permissões do Actions**: Settings > Actions > General > Workflow permissions > *Read and write permissions*.
4. **Pages**: Settings > Pages > Source: *GitHub Actions*.
5. **Primeira execução manual** (trava a linha de base): Actions > monitor-semanal > Run workflow.
   No log da etapa "Coleta", confira as linhas `LINHA DE BASE travada <id>`. A primeira coleta busca 2 anos de histórico para contexto dos gráficos; a linha de base é o último ponto com referência até 26/10/2026.
6. Abra `https://<usuario>.github.io/<repositorio>/dashboard.html`.

A partir daí não há rotina manual: você só lê o dashboard, o e-mail e as Issues.

## Contingência (manual.csv)

Use **somente** quando um coletor quebrar ou estiver desativado. Cada linha passa pela mesma validação
(faixa, variação, domínio oficial na URL) e deduplicação. Linhas de indicadores cujo coletor está
funcionando são ignoradas.

```
id,ref,valor,url
cesta_sp,2026-09-01,850.12,https://www.dieese.org.br/...
```

`ref`: mensal = AAAA-MM-01; trimestral = dia 01 do último mês do trimestre; anual = AAAA-12-01.
O ponto fica marcado `origem: manual` no dados.json e com selo no dashboard.

## Quarentena

Valores reprovados na sanidade não entram na série e abrem Issue. Se, conferido na fonte, o valor estiver correto:

```
python coletor.py --liberar desocup 2026-10-01 --motivo "conferido no SIDRA em 03/11"
```

A liberação fica registrada no log de coletas e no próprio ponto. Se o caso se repetir, ajuste `faixa` ou `var_max` em `config.py`.

## Códigos: conferidos e pendentes (VALIDAR)

Conferidos nas APIs oficiais em 27/10/2026:

| id | Fonte | Código | Resultado da conferência |
|---|---|---|---|
| desocup | SIDRA | 6381 / v4099 | Taxa de desocupação, trimestre móvel; 5,3% em jun-jul-ago 2026 |
| ocup | SIDRA | 6379 / v4097 | Nível da ocupação; 58,9% em jun-jul-ago 2026 |
| renda_real | SIDRA | 6390 / v5933 | Rendimento médio real habitual; R$ 3.777 |
| informal | SIDRA | 8529 / v12466 | Taxa de informalidade, trimestral; 37,4% no 2º tri 2026 |
| pib_tri | SIDRA | 5932 / v6561 / c11255=90707 | Taxa trimestral vs. mesmo período do ano anterior, PIB a preços de mercado; 2,0% no 2º tri 2026 |
| gini | SIDRA | 7435 / v10681 | Gini do rendimento domiciliar per capita; 0,511 em 2025 |
| ibcbr | SGS | **24364** | Série suavizada (110,37 / 110,03 / 110,41) frente à 24363 (110,18 / 114,49 / 111,72): 24364 é a dessazonalizada. O briefing citava 24363, que é a série sem ajuste |
| primario | SGS | 5793 | Valores de 0,62 a 1,19 em jun-ago/2026, compatíveis com resultado primário 12m em % do PIB. **Convenção NFSP: positivo = déficit** |
| dbgg | SGS | 13762 | 82,87% PIB em ago/2026 |
| salario_min | SGS | 1619 | R$ 1.621 em out/2026. A série traz meses futuros; o coletor descarta referências posteriores à data da coleta |
| cesta_sp | DIEESE/Conab | boletim PDF `analisecestabasica/AAAA/AAAAMMcestabasica.pdf` | Endereço e layout da Tabela 1 conferidos no boletim de jul/2026 (São Paulo R$ 915,01). Ativado em 27/10/2026 |
| dpf | Tesouro Transparente | dataset CKAN 0998f610-bc25-4ce3-b32c-a873447500c2 | Colunas conforme documento de metadados do Tesouro. Indicador = soma da classe Mercado (DPF em poder do público), em R$ trilhões. Ativado em 27/10/2026 |
| gasolina, etanol, diesel | ANP | `semanal-brasil-desde-2013.xlsx`, produtos GASOLINA COMUM, ETANOL HIDRATADO, OLEO DIESEL S10 | Layout conferido em 28/10/2026: semana 18 a 24/10/2026 com R$ 6,49 / 4,11 / 7,32 por litro |
| desmat_deter | INPE TerraBrasilis | WFS `deter-amz:deter_amz`, classes DESMATAMENTO_CR + DESMATAMENTO_VEG + MINERACAO, soma de `areamunkm` por mês de `view_date` | Conferido em 28/10/2026: set/2026 = 350,19 km²; histórico desde ago/2016 |
| ibovespa | B3 | `indexStatisticsProxy/IndexCall/GetPortfolioDay` (IBOV, ano) | Conferido em 28/10/2026: 205.082,56 em 23/10 e 176.608,23 em 26/10/2026 (queda de 13,9% no dia da linha de base; `var_max` ajustado para 25% para não mandar para quarentena) |
| arrecadacao | Tesouro (RTN) | dataset CKAN `resultado-do-tesouro-nacional`, aba 1.1, linha "Receita Total", soma de 12 meses | Conferido em 28/10/2026 (seriehistoricajul26.xlsx): rótulo real "1. RECEITA TOTAL 1/"; 12 meses até jul/2026 = R$ 3.074,31 bilhões |
| caged | SGS | 28763 | Estoque de empregos formais do Novo Caged: 48.244.696 em ago/2026. A variação mensal equivale ao saldo |
| inseg_grave | SIDRA | 6665 / v800 / c12404=109102 | ODS 2.1.2, % de domicílios com insegurança alimentar grave: 4,1% (2023) e 3,2% (2024) |
| pobreza | SIDRA | 5877 / v9948 | ODS 1.2.1, % abaixo da linha de pobreza nacional: 26,5% em 2024 |
| ext_pobreza | SIDRA | 5817 / v9617 | ODS 1.1.1, % abaixo da linha de pobreza internacional: 4,7% em 2024 |

Pendentes:

| id | Situação | Como validar |
|---|---|---|
| primario | código conferido por valor, não por descrição | Abrir o SGS (www3.bcb.gov.br/sgspub), buscar 5793 e confirmar "NFSP sem desvalorização cambial, resultado primário, 12 meses, % PIB, setor público consolidado" |
| ibcbr | idem | Buscar 24364 no SGS e confirmar "com ajuste sazonal" |
| dolar, euro, selic, ipca_m, ipca_12, dlsp | códigos do briefing, padrão de mercado | Buscar no SGS e confirmar descrição e unidade. Teste rápido: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.<código>/dados/ultimos/3?formato=json` |
| focus_* | nomes "IPCA", "Selic", "PIB Total" | `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais?$top=5&$format=json&$filter=Indicador eq 'PIB Total'` deve retornar linhas |

Para ativar um coletor: preencher os parâmetros, mudar `ativo` para `True` em `config.py`, rodar `pytest` e `python coletor.py --hoje <data>` localmente.

### Indicadores retirados

- **Risco-país (CDS 5 anos)**, retirado em 28/10/2026. Não há fonte gratuita, oficial e estável: as cotações de CDS são de provedores pagos, e a série EMBI+ Risco-Brasil do Ipeadata (JPM366_EMBI366) está inativa. Para reincluir, criar um coletor licenciado e devolver a entrada ao `config.py`.
- Quando um indicador sai do `config.py`, o coletor o move para `descontinuados` no dados.json, com série, linha de base e selo. Nada é apagado.

### Escolhas de fonte (28/10/2026)

- **Pobreza e extrema pobreza vêm dos indicadores ODS do IBGE, não da SIS.** A SIS só sai em planilhas; os ODS têm tabela no SIDRA com a mesma base (PNAD Contínua), mas as linhas de corte podem diferir das usadas na SIS, então os percentuais não são diretamente comparáveis com as manchetes da SIS. Antes de citar, conferir a definição da linha nos metadados ODS do IBGE.
- **Insegurança alimentar** é um suplemento esporádico da PNAD Contínua (2004, 2009, 2013, 2018, 2023, 2024): não gera alerta de atraso.
- **Impostômetro não foi usado.** É uma estimativa da Associação Comercial de São Paulo, não um dado oficial. O equivalente oficial é a Receita Total do Governo Central, do Resultado do Tesouro Nacional, acumulada em 12 meses (soma dos valores mensais publicados; evita a sazonalidade mensal). Cobre só a esfera federal.
- **Desmatamento usa DETER, não PRODES.** DETER é o sistema de alerta mensal do INPE; PRODES é a taxa oficial anual (ago a jul), divulgada uma vez por ano. DETER serve para acompanhar tendência; não deve ser citado como taxa oficial. O mês só é gravado 15 dias após terminar, porque avisos atrasados ainda entram nesse prazo.
- **Ibovespa vem da B3**, que calcula o índice. É a única fonte não governamental do sistema (exceção prevista para dados de mercado). O endpoint é o da página pública da B3, sem documentação formal: pode mudar sem aviso.

## Periodicidade e calendário típico

O calendário é indicativo. A data efetiva é a do calendário oficial de cada órgão. O alerta de "dado atrasado" dispara quando a idade da última referência passa do limite abaixo (período + defasagem típica + ~10 dias).

| id | Periodicidade | Divulgação típica | Limite de atraso (dias) |
|---|---|---|---|
| dolar, euro | diária | dias úteis | 7 |
| selic | diária (muda no Copom) | 8 reuniões/ano | 10 |
| ipca_m, ipca_12 | mensal | ~dia 10 do mês seguinte | 80 |
| dbgg, dlsp, primario | mensal | ~30 dias após o mês | 100 |
| ibcbr | mensal | ~45 dias após o mês | 115 |
| salario_min | mensal (reajuste anual) | janeiro | 45 |
| focus_ipca, focus_selic, focus_pib | semanal | segunda-feira | 15 |
| desocup, ocup, renda_real | mensal (trimestre móvel) | fim do mês seguinte | 100 |
| informal | trimestral | ~45 dias após o trimestre | 180 |
| pib_tri | trimestral | ~60 dias após o trimestre | 195 |
| gini, pobreza, ext_pobreza | anual | 2º semestre / dezembro | 720 |
| inseg_grave | esporádica | suplemento PNAD | sem alerta |
| cesta_sp, sm_cestas | mensal | 1ª quinzena do mês seguinte | 75 |
| caged | mensal | ~30 dias após o mês | 100 |
| dpf | mensal | ~25 dias após o mês | 95 |
| gasolina, etanol, diesel | semanal | segunda/terça da semana seguinte | 21 |
| ibovespa | diária | dias úteis | 7 |
| desmat_deter | mensal | gravado 15 dias após o mês | 80 |
| arrecadacao | mensal | RTN, ~30 dias após o mês | 100 |

## Regras de integridade implementadas

- **Sem estimativa**: valores ausentes (`...`, `-`, vazio) são ignorados, nunca completados. Sem arredondamento na gravação.
- **Deduplicação** por (indicador, referência). Se a fonte **revisar** um valor já gravado, a série mantém o original e a revisão vai para `revisoes` no dados.json (auditável). Ver "Pontos de atenção".
- **Linha de base imutável**: travada uma única vez e selada com SHA-256 em `baseline_selos`. Alteração manual é detectada, deixa o status vermelho e abre Issue de integridade. O sistema não "corrige" sozinho: restaure pelo histórico do Git ou pela Release de backup.
- **Quarentena** para valor fora da faixa, variação anormal, URL fora de domínio oficial ou referência futura.
- **IA sem acesso a números brutos para cálculo**: recebe variações já calculadas, não gera a tabela, e o relatório informa se a IA citou algum número sem correspondência nos dados (controle de rastreabilidade).

## Continuidade de 4 anos

- **Agendamento**: o GitHub desativa workflows agendados em repositório público após 60 dias sem atividade. Há três defesas: commit semanal do próprio dados.json, chamada à API `.../actions/workflows/monitor.yml/enable` a cada execução (keepalive) e e-mail semanal: se ele parar de chegar, algo parou.
- **Fixação de versões**: Python 3.12.7, `ubuntu-24.04`, actions por tag major e dependências com versão exata. Recomendado trocar as tags pelo SHA do commit de cada action e ativar o Dependabot apenas para `github-actions`, revisando os PRs.
- **Rotação**: acima de 4 MB, logs de coleta e quarentena de anos anteriores vão para `data/arquivo/AAAA.json`. Séries, linha de base e selos nunca saem do arquivo principal. Estimativa: o dados.json fica abaixo de 2 MB em 4 anos.
- **Backup**: Release `backup-AAAA-MM` com dados.json e saude.json na primeira execução de cada mês.

## Simulação

`tests/` cobre os cenários unitários. Uma simulação de 4 semanas com fonte fictícia (fora do pacote) produziu:

| Semana | Evento simulado | Resultado |
|---|---|---|
| 27/10 | primeira coleta | 143 pontos de histórico, linha de base travada, coletores VALIDAR como "cinza" |
| 02/11 | novos meses | 54 pontos novos, sem duplicidade |
| 09/11 | PIB com layout alterado | erro isolado, Issue aberta, demais indicadores gravados, valor anterior mantido |
| 16/11 | 2ª falha do PIB, 503 no Gini, desocupação = 60% | PIB vermelho (crítico), Gini amarelo, 60% para quarentena; linha de base intacta |

Execução real neste ambiente: todas as APIs foram bloqueadas pelo proxy (403), e a rotina terminou normalmente com status amarelo, registrando cada erro. Esse é o comportamento esperado em falha total de rede.

## Custos

- GitHub Actions e Pages: sem custo em repositório público. Cada execução leva poucos minutos.
- API da Anthropic (Claude Sonnet 5.5, US$ 2 por milhão de tokens de entrada e US$ 10 por milhão de saída): estimativa de ~15 mil tokens de entrada e ~2 mil de saída por execução, cerca de US$ 0,05 por semana e **US$ 0,20 a 0,25 por mês**. Defina `ANTHROPIC_MODEL` como variável para trocar o modelo; o Haiku 5.5 reduz o custo em ~20 vezes, com perda de qualidade de redação.
- E-mail: SMTP gratuito (Gmail com senha de app ou equivalente).
