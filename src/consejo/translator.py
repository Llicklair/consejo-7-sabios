"""Pipeline de traducción ES ↔ EN.

Razón (ARCHITECTURE.md):
- Los sabios debaten internamente en INGLÉS (más consistencia con LLMs)
- El usuario describe el atasco en ESPAÑOL y recibe el reporte en ESPAÑOL
- La transcripción original (EN) se conserva para auditabilidad

Modelo: Haiku 4.5 (rápido y suficiente para texto técnico).

Modos:
- mock: identidad (sin coste, devuelve la entrada tal cual)
- real: anthropic SDK con `claude-haiku-4-5`
"""

from __future__ import annotations

import copy


async def translate(text: str, src: str, dst: str, mode: str = "mock") -> str:
    """Traduce `text` de idioma `src` a `dst`. src/dst ∈ {'es', 'en'}."""
    if not text or src == dst:
        return text
    if mode == "mock":
        return text
    if mode == "real":
        return await _real_translate(text, src, dst)
    raise ValueError(f"mode desconocido: {mode}")


async def _real_translate(text: str, src: str, dst: str) -> str:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK no instalado. `pip install anthropic`.") from e
    client = AsyncAnthropic()
    name_src = "Spanish" if src == "es" else "English"
    name_dst = "Spanish" if dst == "es" else "English"
    resp = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": (
                f"Translate the following from {name_src} to {name_dst}. "
                f"Preserve verbatim: technical terms, file paths, function/class "
                f"names, library names, identifiers, code snippets. Translate only "
                f"the surrounding prose. Output ONLY the translation — no preface, "
                f"no quotes, no markdown fences.\n\n---\n{text}\n---"
            ),
        }],
    )
    out = resp.content[0].text.strip()
    # Limpia posibles delimitadores
    for delim in ("---", "```"):
        out = out.removeprefix(delim).removesuffix(delim).strip()
    return out


async def translate_atasco_to_en(atasco_es: str, mode: str = "mock") -> str:
    """Traduce el atasco del usuario (ES) a EN antes de pasarlo al consejo."""
    return await translate(atasco_es, "es", "en", mode)


async def translate_plan_to_es(plan_en: dict, mode: str = "mock") -> dict:
    """Traduce los campos human-readable del plan a español.

    El plan original (EN) se preserva en `plan['_original_en']` para auditar
    qué dijeron de verdad los sabios. El reporte bilingüe muestra ambos."""
    if mode == "mock":
        return plan_en
    plan = copy.deepcopy(plan_en)
    plan["_original_en"] = copy.deepcopy(plan_en)
    # Traduce solo lo que el usuario lee:
    plan["summary"] = await translate(plan.get("summary", ""), "en", "es", mode)
    for t in plan.get("tasks", []):
        t["title"] = await translate(t.get("title", ""), "en", "es", mode)
        t["rationale"] = await translate(t.get("rationale", ""), "en", "es", mode)
    for d in plan.get("unresolved_disagreements", []):
        if "critique" in d:
            d["critique"] = await translate(d["critique"], "en", "es", mode)
        if "judge_call" in d:
            d["judge_call"] = await translate(d["judge_call"], "en", "es", mode)
    return plan
