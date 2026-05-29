"""JSON schemas constraining sage and judge output.

These schemas are passed to `--json-schema` on backends that support
structured output (Claude Code), or injected as instruction text on
backends that don't (Codex). The schemas are deliberately strict — fewer
free-form fields mean fewer "the model emitted a paragraph instead of an
array" failures.
"""

from __future__ import annotations


PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "minItems": 2,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["title", "rationale", "blast_radius", "category"],
                "properties": {
                    "title": {"type": "string", "maxLength": 200},
                    "rationale": {"type": "string", "maxLength": 3000},
                    "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                    "category": {
                        "enum": [
                            "code-fix",
                            "future-feature",
                            "strategic-direction",
                            "research-thread",
                        ],
                        "description": (
                            "code-fix: improve existing code · "
                            "future-feature: new capability to build · "
                            "strategic-direction: where the project should go · "
                            "research-thread: open question worth investigating"
                        ),
                    },
                    "files_touched": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 300},
                        "maxItems": 10,
                    },
                    "horizon": {
                        "enum": ["now", "next-quarter", "next-year"],
                        "description": "Time horizon. 'now' = this PR; 'next-quarter' = real work; 'next-year' = vision.",
                    },
                },
            },
        }
    },
}

CRITIQUE_SCHEMA = {
    "type": "object",
    "required": ["endorses", "challenges", "amendments"],
    "properties": {
        "endorses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["proposal_title", "proposed_by"],
                "properties": {
                    "proposal_title": {"type": "string"},
                    "proposed_by": {"type": "string"},
                    "reason": {"type": "string", "maxLength": 500},
                },
            },
        },
        "challenges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["proposal_title", "proposed_by", "objection"],
                "properties": {
                    "proposal_title": {"type": "string"},
                    "proposed_by": {"type": "string"},
                    "objection": {"type": "string", "maxLength": 1500},
                },
            },
        },
        "amendments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "rationale", "blast_radius"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string", "maxLength": 1500},
                    "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                    "files_touched": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


JUDGE_SCHEMA = {
    "type": "object",
    "required": ["summary", "unanimous", "tasks", "strategic_vision"],
    "properties": {
        "summary": {"type": "string"},
        "unanimous": {"type": "boolean"},
        "tasks": {
            "type": "array",
            "description": "Tactical/code-fix items the user can execute now",
            "items": {
                "type": "object",
                "required": ["title", "rationale", "blast_radius", "supporting_sages"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                    "category": {"enum": ["code-fix", "future-feature", "strategic-direction", "research-thread"]},
                    "horizon": {"enum": ["now", "next-quarter", "next-year"]},
                    "supporting_sages": {"type": "array", "items": {"type": "string"}},
                    "files_touched": {"type": "array", "items": {"type": "string"}},
                    "auto_executable": {"type": "boolean"},
                    "priority": {"type": "integer"},
                },
            },
        },
        "strategic_vision": {
            "type": "object",
            "required": ["headline", "where_to_take_it", "future_features", "research_threads"],
            "description": "Forward-looking synthesis: where the project should go, not just what to fix.",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "1-sentence vision statement.",
                },
                "where_to_take_it": {
                    "type": "string",
                    "description": "2-4 paragraphs on the project's direction over the next year, derived from the council's strategic-direction proposals.",
                },
                "future_features": {
                    "type": "array",
                    "description": "Concrete new capabilities worth building (not bugs to fix).",
                    "items": {
                        "type": "object",
                        "required": ["title", "why", "horizon"],
                        "properties": {
                            "title": {"type": "string"},
                            "why": {"type": "string"},
                            "horizon": {"enum": ["next-quarter", "next-year"]},
                            "supporting_sages": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "research_threads": {
                    "type": "array",
                    "description": "Open questions worth investigating before committing to a path.",
                    "items": {
                        "type": "object",
                        "required": ["question", "why_it_matters"],
                        "properties": {
                            "question": {"type": "string"},
                            "why_it_matters": {"type": "string"},
                        },
                    },
                },
            },
        },
        "unresolved_disagreements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "positions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


TURN_SCHEMA = {
    "type": "object",
    "required": ["message", "plan_diff", "vote"],
    "properties": {
        "message": {
            "type": "string",
            "description": (
                "What you say to the council this turn. Address other sages "
                "by id when reacting. Keep it under 6 sentences."
            ),
        },
        "plan_diff": {
            "type": "object",
            "properties": {
                "add": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "rationale", "blast_radius"],
                        "properties": {
                            "title": {"type": "string"},
                            "rationale": {"type": "string"},
                            "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                            "category": {
                                "enum": [
                                    "code-fix", "future-feature",
                                    "strategic-direction", "research-thread",
                                ],
                            },
                            "horizon": {"enum": ["now", "next-quarter", "next-year"]},
                            "files_touched": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "amend": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["target_title"],
                        "properties": {
                            "target_title": {"type": "string"},
                            "new_title": {"type": "string"},
                            "new_rationale": {"type": "string"},
                            "new_blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                            "new_category": {
                                "enum": [
                                    "code-fix", "future-feature",
                                    "strategic-direction", "research-thread",
                                ],
                            },
                            "new_horizon": {"enum": ["now", "next-quarter", "next-year"]},
                            "new_files_touched": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Replace the item's files_touched array "
                                    "entirely. Use this to fix incorrect or "
                                    "missing file references — otherwise the "
                                    "item becomes an 'immortal cockroach' that "
                                    "no amount of debate can correct."
                                ),
                            },
                        },
                    },
                },
                "remove": {"type": "array", "items": {"type": "string"}},
            },
        },
        "vote": {
            "type": "object",
            "required": ["signed"],
            "properties": {
                "signed": {
                    "type": "boolean",
                    "description": (
                        "true ONLY if you endorse every current plan item AND "
                        "the plan is non-empty."
                    ),
                },
                "objections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Titles of items you block. Empty if signed=true.",
                },
                "reasoning": {"type": "string"},
            },
        },
    },
}


_VISION_SCHEMA = {
    "type": "object",
    "required": ["headline", "where_to_take_it"],
    "properties": {
        "headline": {"type": "string", "maxLength": 240},
        "where_to_take_it": {"type": "string"},
        "future_features": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "rationale", "horizon"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "horizon": {"enum": ["next-quarter", "next-year"]},
                    "supporting_sages": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "research_threads": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question", "why_it_matters"],
                "properties": {
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
            },
        },
    },
}

