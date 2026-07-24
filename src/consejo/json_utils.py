"""JSON parsing helpers shared by all backends.

`_extract_json_object` is the heuristic parser used to recover JSON
emitted by an LLM that may have wrapped it in markdown fences or added
a preamble. Without this, a minor formatting deviation wastes a full
round trip.
"""

from __future__ import annotations

import json
import re


def _extract_json_object(text: str) -> dict:
    """Parse text as JSON; on failure, extract the first balanced {...} block.

    The model often wraps output in ```json ... ``` fences or adds a short
    preamble. We strip fences and scan for the first balanced object so a
    minor formatting deviation doesn't waste a $0.08 round trip.
    """
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            # A bare list/scalar isn't a JSON object; fall through to the
            # brace-scan so an embedded object (e.g. '[{"plan": 1}]') can
            # still be recovered instead of returning a non-dict.
            raise json.JSONDecodeError("parsed value is not an object", s, 0)
        return obj
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start < 0:
        raise json.JSONDecodeError("no '{' in response", s, 0)
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    obj = json.loads(s[start:i + 1])
                    if not isinstance(obj, dict):
                        # Belt-and-suspenders: a balanced {...} scan should
                        # always yield a dict, but guard anyway so this
                        # function never returns a non-dict.
                        raise json.JSONDecodeError("scanned value is not an object", s, start)
                    return obj
    raise json.JSONDecodeError("unbalanced braces", s, start)
