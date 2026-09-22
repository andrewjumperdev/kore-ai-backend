"""Oportunidades: las reglas que sostienen los números del pipeline.

Casi todo acá son invariantes, no comportamiento: si una etapa nueva queda sin
clasificar, o si el monto se vuelve float, los totales siguen calculándose y
dando un número — solo que el número está mal, y nadie se entera hasta que un
cliente lo audita contra su propia planilla.
"""
from __future__ import annotations

import pytest

from app.api.v1.deals import _check_stage, _name_key
from app.core.exceptions import ValidationError
from app.models.crm import CLOSED_STAGES, DEAL_STAGES, OPEN_STAGES, Deal


# ── El embudo está completo y sin superposiciones ───────────────────

def test_toda_etapa_esta_clasificada_como_abierta_o_cerrada():
    """El invariante que más importa: los totales del pipeline se calculan
    filtrando por estos dos conjuntos. Una etapa nueva sin clasificar
    desaparece de las sumas sin romper nada — el peor tipo de bug."""
    assert set(OPEN_STAGES) | set(CLOSED_STAGES) == set(DEAL_STAGES)


def test_ninguna_etapa_es_abierta_y_cerrada_a_la_vez():
    """Si se superpusieran, su monto se contaría dos veces en el total."""
    assert not (set(OPEN_STAGES) & set(CLOSED_STAGES))


def test_ganada_y_perdida_son_las_unicas_terminales():
    assert set(CLOSED_STAGES) == {"won", "lost"}


def test_las_etapas_estan_en_orden_de_avance():
    """El orden es lo que hace que el embudo se lea como embudo: la UI las
    dibuja en esta secuencia."""
    assert DEAL_STAGES.index("new") < DEAL_STAGES.index("qualified")
    assert DEAL_STAGES.index("qualified") < DEAL_STAGES.index("proposal")
    assert DEAL_STAGES.index("proposal") < DEAL_STAGES.index("negotiation")


# ── Validación de entrada ───────────────────────────────────────────

def test_una_etapa_inventada_se_rechaza():
    """Sin esto, un typo del integrador crea una etapa fantasma que no aparece
    en ningún total pero sí existe en la base."""
    with pytest.raises(ValidationError):
        _check_stage("casi-cerrado")


def test_las_etapas_validas_pasan():
    for stage in DEAL_STAGES:
        _check_stage(stage)


# ── Deduplicación de empresas ───────────────────────────────────────

def test_la_misma_empresa_escrita_distinto_es_la_misma():
    assert _name_key("ACME S.A.") == _name_key("acme s.a.")


def test_los_espacios_de_mas_no_crean_una_empresa_nueva():
    """Copiar y pegar de una planilla arrastra espacios dobles constantemente."""
    assert _name_key("Acme  S.A. ") == _name_key("Acme S.A.")


# ── El monto ────────────────────────────────────────────────────────

def test_el_monto_es_entero_en_centavos():
    """Un float acá hace que 0.1 + 0.2 != 0.3 y el pipeline no cierre contra la
    planilla del cliente por centavos que nadie puede explicar."""
    col = Deal.__table__.columns["amount_cents"]
    assert col.type.python_type is int


def test_una_oportunidad_sin_monto_es_valida():
    """Recién abierta muchas veces no se sabe cuánto es. Forzar 0 mentiría en
    el total del pipeline; nullable deja distinguir 'no sé' de 'cero'."""
    assert Deal.__table__.columns["amount_cents"].nullable


def test_una_oportunidad_abierta_se_reconoce_como_abierta():
    assert Deal(title="x", stage="proposal").is_open


def test_una_ganada_ya_no_esta_abierta():
    """Si siguiera contando como abierta, el pipeline sumaría dos veces lo ya
    cerrado."""
    assert not Deal(title="x", stage="won").is_open
