from coletores import bcb_focus, bcb_sgs, cds, dieese, ibge_sidra, mte_caged, tesouro

REGISTRO = {
    "bcb_sgs": bcb_sgs.coletar,
    "bcb_focus": bcb_focus.coletar,
    "ibge_sidra": ibge_sidra.coletar,
    "dieese": dieese.coletar,
    "mte_caged": mte_caged.coletar,
    "tesouro": tesouro.coletar,
    "cds": cds.coletar,
}
