from coletores import (anp, b3, bcb_focus, bcb_sgs, cds, dieese, ibge_sidra, inpe_deter, mte_caged,
                       tesouro, tesouro_rtn)

REGISTRO = {
    "bcb_sgs": bcb_sgs.coletar,
    "bcb_focus": bcb_focus.coletar,
    "ibge_sidra": ibge_sidra.coletar,
    "dieese": dieese.coletar,
    "mte_caged": mte_caged.coletar,
    "tesouro": tesouro.coletar,
    "cds": cds.coletar,
    "anp": anp.coletar,
    "b3": b3.coletar,
    "inpe_deter": inpe_deter.coletar,
    "tesouro_rtn": tesouro_rtn.coletar,
}
