from coletores import (anp, b3, bcb_focus, bcb_sgs, dieese, ibge_sidra, inpe_deter, tesouro,
                       tesouro_rtn)

REGISTRO = {
    "bcb_sgs": bcb_sgs.coletar,
    "bcb_focus": bcb_focus.coletar,
    "ibge_sidra": ibge_sidra.coletar,
    "dieese": dieese.coletar,
    "tesouro": tesouro.coletar,
    "tesouro_rtn": tesouro_rtn.coletar,
    "anp": anp.coletar,
    "b3": b3.coletar,
    "inpe_deter": inpe_deter.coletar,
}
