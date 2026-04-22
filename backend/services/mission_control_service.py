"""
Mission Control integration service.

Exposes Tom's Personal Mission Control (running on rabbit) as a tool-calling
surface for the open-chat assistant. The LLM can log accomplishments, set
goals, and read current state via the tool schemas defined here.

Tools call the live MC API over HTTP (default: http://rabbit/api).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

MC_API_BASE = os.getenv("MC_API_BASE", "http://rabbit/api").rstrip("/")
HTTP_TIMEOUT = 10.0


def _local_today() -> str:
    """Return today's date in local time as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


# -----------------------------------------------------------------------------
# Tool schemas (OpenAI tool-calling format — also accepted by Ollama v0.4+)
# -----------------------------------------------------------------------------
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "log_accomplishment",
            "description": (
                "Record something Tom actually completed today in Mission Control. "
                "Use this when Tom reports finishing a task, shipping code, resolving "
                "an issue, or making meaningful progress. Only log things actually done, "
                "not plans or intentions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Short imperative phrase, e.g. 'Fixed nginx reverse proxy on rabbit'",
                    },
                    "category": {
                        "type": "string",
                        "description": "One of: dev, ops, learning, personal, work",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional one-line factual context",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD (local). Omit to default to today.",
                    },
                },
                "required": ["task", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_monthly_goal",
            "description": (
                "Replace the current month's headline goal in Mission Control. "
                "Use when Tom defines what matters most for the month ahead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Short goal phrase"},
                    "description": {
                        "type": "string",
                        "description": "Optional expanded description",
                    },
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_weekly_goal",
            "description": (
                "Set this week's focus under the current monthly goal. The dashboard "
                "uses the weekly goal text to auto-bucket accomplishments via keyword "
                "match, so phrasing matters."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todays_progress",
            "description": (
                "Fetch today's logged accomplishments and summary. Use when Tom asks "
                "'what did I do today?' or before deciding what he should work on next."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_goals",
            "description": (
                "Fetch the current monthly and weekly goals so you can ground your "
                "suggestions in what Tom is actually focused on."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_day_summary",
            "description": (
                "Set or replace the narrative summary for a day (any date). Use when "
                "Tom asks to update yesterday's summary, or to attach a summary to "
                "today, or to correct/replace a placeholder summary. This is NOT the "
                "same as logging a new accomplishment — it's a free-text description "
                "of what that day amounted to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD (local). Required. Use yesterday's date if Tom says 'yesterday'.",
                    },
                    "summary": {"type": "string"},
                },
                "required": ["date", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": (
                "Record what Tom ATE for a specific slot today (or past date). "
                "Use this when he reports having eaten something — not when he's "
                "planning ahead. Keep item short; put elaborations in notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slot": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                    },
                    "item": {"type": "string", "description": "Short meal description"},
                    "notes": {"type": "string"},
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD (local). Omit for today.",
                    },
                },
                "required": ["slot", "item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_meals",
            "description": (
                "Set Tom's PLANNED meals for a day (what he intends to eat, not what he's "
                "already eaten). Use this for forward-looking meal planning. Only pass the "
                "slots being planned — omitted slots stay untouched."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "breakfast": {"type": "string"},
                    "lunch": {"type": "string"},
                    "dinner": {"type": "string"},
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD (local). Omit for today.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todays_meals",
            "description": (
                "Fetch today's meal plan (what was planned) and what's been logged as "
                "eaten so far. Use before answering meal-related questions or before "
                "suggesting the next meal."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# -----------------------------------------------------------------------------
# Tool handlers — these are invoked when the LLM emits a tool call.
# Each returns a dict that gets JSON-encoded and sent back to the model as the
# tool's response. Keep responses small; the model doesn't need sprawling data.
# -----------------------------------------------------------------------------
async def _log_accomplishment(args: Dict[str, Any]) -> Dict[str, Any]:
    task = args.get("task", "").strip()
    category = args.get("category", "").strip() or "work"
    notes = args.get("notes", "").strip()
    date = args.get("date") or _local_today()

    if not task:
        return {"ok": False, "error": "task is required"}

    payload = {
        "date": date,
        "accomplishments": [
            {"task": task, "category": category, **({"notes": notes} if notes else {})}
        ],
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{MC_API_BASE}/accomplishments", json=payload)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    return {"ok": True, "logged": {"task": task, "category": category, "date": date}}


async def _set_monthly_goal(args: Dict[str, Any]) -> Dict[str, Any]:
    goal = args.get("goal", "").strip()
    description = args.get("description", "").strip()
    if not goal:
        return {"ok": False, "error": "goal is required"}

    payload = {"goal": goal, **({"description": description} if description else {})}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{MC_API_BASE}/goals", json=payload)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    return {"ok": True, "set": {"goal": goal}}


async def _set_weekly_goal(args: Dict[str, Any]) -> Dict[str, Any]:
    goal = args.get("goal", "").strip()
    description = args.get("description", "").strip()
    if not goal:
        return {"ok": False, "error": "goal is required"}

    payload = {"goal": goal, **({"description": description} if description else {})}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.put(f"{MC_API_BASE}/goals/weekly", json=payload)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
    return {"ok": True, "week": data.get("week"), "set": {"goal": goal}}


async def _get_todays_progress(_: Dict[str, Any]) -> Dict[str, Any]:
    date = _local_today()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{MC_API_BASE}/accomplishments", params={"date": date})
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        data = resp.json()

    # When filtered by date, the API returns a flat day object:
    #   { id, date, accomplishments: [task, task, ...], summary, logged_at }
    # When there's no match, it returns { date, accomplishments: [] }.
    entries = data.get("accomplishments") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {"ok": True, "date": date, "count": 0, "items": []}

    return {
        "ok": True,
        "date": date,
        "summary": data.get("summary"),
        "count": len(entries),
        "items": [
            {"task": e.get("task"), "category": e.get("category"), "notes": e.get("notes")}
            for e in entries
        ],
    }


async def _get_current_goals(_: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{MC_API_BASE}/goals")
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        data = resp.json()

    monthly = data.get("monthly_goals") or []
    if not monthly:
        return {"ok": True, "monthly": None, "weekly": None}
    m0 = monthly[0]
    weeklies = m0.get("weekly_goals") or []
    w0 = weeklies[0] if weeklies else None
    return {
        "ok": True,
        "monthly": {"goal": m0.get("goal"), "description": m0.get("description")},
        "weekly": {"goal": w0.get("goal"), "description": w0.get("description")} if w0 else None,
    }


async def _set_day_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    date = args.get("date", "").strip()
    summary = args.get("summary", "").strip()
    if not date:
        return {"ok": False, "error": "date is required (YYYY-MM-DD)"}
    if not summary:
        return {"ok": False, "error": "summary is required"}

    # The existing POST /api/accomplishments endpoint already updates the day's
    # summary when passed in the body alongside an (empty) accomplishments list.
    payload = {"date": date, "accomplishments": [], "summary": summary}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{MC_API_BASE}/accomplishments", json=payload)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    return {"ok": True, "date": date, "summary_set": summary}


async def _log_meal(args: Dict[str, Any]) -> Dict[str, Any]:
    slot = args.get("slot", "").strip()
    item = args.get("item", "").strip()
    notes = args.get("notes", "").strip()
    date = args.get("date") or _local_today()

    if slot not in {"breakfast", "lunch", "dinner", "snack"}:
        return {"ok": False, "error": "slot must be breakfast, lunch, dinner, or snack"}
    if not item:
        return {"ok": False, "error": "item is required"}

    payload = {"slot": slot, "item": item, "date": date}
    if notes:
        payload["notes"] = notes
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{MC_API_BASE}/meals", json=payload)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    return {"ok": True, "logged": {"slot": slot, "item": item, "date": date}}


async def _plan_meals(args: Dict[str, Any]) -> Dict[str, Any]:
    date = args.get("date") or _local_today()
    payload = {"date": date}
    for slot in ("breakfast", "lunch", "dinner"):
        if slot in args and args[slot] is not None:
            payload[slot] = args[slot]
    if len(payload) == 1:  # only date
        return {"ok": False, "error": "at least one of breakfast/lunch/dinner must be set"}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.put(f"{MC_API_BASE}/meals/plan", json=payload)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
    return {"ok": True, "date": date, "plan": data.get("plan")}


async def _get_todays_meals(_: Dict[str, Any]) -> Dict[str, Any]:
    date = _local_today()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{MC_API_BASE}/meals", params={"date": date})
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        day = resp.json()

    def slot_desc(s):
        if not s:
            return None
        return {k: v for k, v in s.items() if k in ("item", "notes")}

    return {
        "ok": True,
        "date": date,
        "planned": {k: slot_desc(day.get("plan", {}).get(k)) for k in ("breakfast", "lunch", "dinner")},
        "eaten": {k: slot_desc(day.get("eaten", {}).get(k)) for k in ("breakfast", "lunch", "dinner")},
        "snacks": [slot_desc(s) for s in (day.get("snacks") or [])],
    }


HANDLERS: Dict[str, Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {
    "log_accomplishment": _log_accomplishment,
    "set_monthly_goal": _set_monthly_goal,
    "set_weekly_goal": _set_weekly_goal,
    "get_todays_progress": _get_todays_progress,
    "get_current_goals": _get_current_goals,
    "set_day_summary": _set_day_summary,
    "log_meal": _log_meal,
    "plan_meals": _plan_meals,
    "get_todays_meals": _get_todays_meals,
}


async def dispatch_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke the named tool and return its result dict."""
    handler = HANDLERS.get(name)
    if not handler:
        return {"ok": False, "error": f"unknown tool: {name}"}
    try:
        return await handler(arguments)
    except httpx.RequestError as e:
        logger.warning("MC tool %s network error: %s", name, e)
        return {"ok": False, "error": f"network error talking to MC: {e}"}
    except Exception as e:
        logger.exception("MC tool %s failed", name)
        return {"ok": False, "error": f"unexpected error: {e}"}


MISSION_CONTROL_SYSTEM_PROMPT = """You are Tom's Personal Mission Control assistant.

Your role: help him track daily accomplishments, manage monthly and weekly goals, plan and log meals, and stay oriented on what he's actually working on.

Tools available:

Goals & accomplishments:
- log_accomplishment: record something Tom completed today
- set_monthly_goal: define the month's headline focus
- set_weekly_goal: set this week's focus
- get_todays_progress: read what's already been logged today
- get_current_goals: read the active monthly and weekly goals
- set_day_summary: set/replace the narrative summary for a given date (not a new accomplishment — the day's overall description)

Meals (separate from accomplishments — don't confuse the two):
- log_meal: record what Tom ACTUALLY ATE for a slot (breakfast/lunch/dinner/snack)
- plan_meals: set INTENDED meals for a day (forward-looking)
- get_todays_meals: read today's plan and what's been eaten so far

Guidance:
- Meals are a different concept than accomplishments. When Tom describes food, use the meal tools, NOT log_accomplishment. Only log eating as an accomplishment if Tom explicitly frames it that way (e.g. "logging that I finally cooked a proper dinner" — even then ask).
- If it's unclear whether he wants to plan or log a meal, ask one brief clarifying question: "Did you already eat that, or are you planning it?"
- If Tom asks to "update yesterday's summary" or similar, use set_day_summary with the right date — do NOT use log_accomplishment. Accomplishments and summaries are different things.
- Only log accomplishments Tom actually completed — not plans, not intentions.
- When Tom describes vague progress, ask short clarifying questions before logging.
- Accomplishment categories: dev, ops, learning, personal, work. Pick the closest fit.
- When suggesting next steps, first call get_current_goals and get_todays_progress so you're grounded in what's real.
- Respond conversationally and concisely. Don't over-explain the tools themselves.
"""
