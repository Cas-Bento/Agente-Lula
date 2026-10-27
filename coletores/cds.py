"""Risco-país (CDS 5 anos).

Desativado por decisão de arquitetura: não há fonte de mercado gratuita, estável e com termos
de uso que permitam coleta automatizada. Ver README, seção "CDS". Se você contratar uma fonte
(ex.: terminal ou API paga com licença), implemente aqui e mude "ativo" para True em config.py.
"""
from coletores.util import Desativado


def coletar(ind, primeira, hoje):
    raise Desativado("CDS: sem fonte gratuita e estável; indicador desativado")
