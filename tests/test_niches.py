"""Calibración de los nichos.

El onboarding es el primer minuto del producto y se arma entero desde acá: las
preguntas del Coach y los ejemplos que las hacen entendibles. Un nicho mal
cargado no rompe nada visiblemente — simplemente deja al cliente mirando una
pregunta ambigua con un campo vacío.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

SEED = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_niches.py"


def _load_niches():
    spec = importlib.util.spec_from_file_location("seed_niches", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.NICHES


NICHES = _load_niches()
SLUGS = [n["slug"] for n in NICHES]


@pytest.mark.parametrize("niche", NICHES, ids=SLUGS)
def test_cada_nicho_tiene_preguntas(niche):
    questions = niche["config"].get("coach_questions", [])
    assert questions, f"{niche['slug']} sin preguntas: el onboarding quedaría vacío"


@pytest.mark.parametrize("niche", NICHES, ids=SLUGS)
def test_cada_pregunta_tiene_su_ejemplo(niche):
    """Los ejemplos se indexan por el TEXTO de la pregunta. Si alguien reescribe
    una pregunta y no toca el ejemplo, este test lo marca — sin él, el ejemplo
    desaparecería en silencio y nadie se enteraría hasta ver el onboarding."""
    config = niche["config"]
    questions = config.get("coach_questions", [])
    examples = config.get("coach_examples", {})

    faltantes = [q for q in questions if not examples.get(q, "").strip()]
    assert not faltantes, f"{niche['slug']}: preguntas sin ejemplo → {faltantes}"


@pytest.mark.parametrize("niche", NICHES, ids=SLUGS)
def test_no_hay_ejemplos_huerfanos(niche):
    """Un ejemplo cuya pregunta ya no existe es una edición a medio hacer."""
    config = niche["config"]
    questions = set(config.get("coach_questions", []))
    huerfanos = [q for q in config.get("coach_examples", {}) if q not in questions]
    assert not huerfanos, f"{niche['slug']}: ejemplos sin pregunta → {huerfanos}"


@pytest.mark.parametrize("niche", NICHES, ids=SLUGS)
def test_el_ejemplo_no_repite_la_pregunta(niche):
    """Un ejemplo que parafrasea la pregunta no ayuda a nadie: tiene que ser una
    RESPUESTA plausible, que es lo que destraba a quien no sabe qué escribir."""
    config = niche["config"]
    for question, example in config.get("coach_examples", {}).items():
        assert example.strip() != question.strip()
        assert not example.strip().startswith("¿"), (
            f"{niche['slug']}: el ejemplo de {question!r} es otra pregunta"
        )


def test_los_slugs_son_unicos():
    assert len(SLUGS) == len(set(SLUGS))
