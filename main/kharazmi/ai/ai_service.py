"""
Rask AI service — connects to z.ai GLM-4.5-flash for natural-language
route planning with streaming responses.

The AI generates COMPLEX, INTERCONNECTED route graphs:
  - Multiple branches (parallel paths)
  - Alternative steps connected with dashed "alternative" edges
  - Fallback steps connected with dotted "fallback" edges
  - Branch merge points
  - No straight single-chain routes

Streaming sends meaningful status text (not raw JSON) to the UI.
"""
from __future__ import annotations

import json
import math
import os
import random
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Any, Iterator


# ---- Configuration ----

API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.5-flash"
POWER_MODEL = "glm-4.5"  # More capable model for complex planning tasks
DEFAULT_API_KEY = "b795a49bd12348c8b9cc4a081c73374b.fmbP9oDfIWJ8zWiy"

SETTINGS_PATH = Path.home() / ".rask" / "ai_settings.json"


def load_ai_settings() -> dict:
    defaults = {
        "api_key": DEFAULT_API_KEY,
        "model": DEFAULT_MODEL,
        "base_url": API_URL,
        "temperature": 0.7,
        "max_tokens": 16384,
    }
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            defaults.update(data)
    except Exception:
        pass
    return defaults


def save_ai_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


# ---- Route domain ----

@dataclass
class RouteStep:
    """A single step in a route. Auto-sizes to fit title + description."""
    id: str
    title: str
    duration_minutes: int
    success_probability: float
    location: str
    description: str
    fallback: str
    depends_on: list[str] = field(default_factory=list)
    sub_goals: list[str] = field(default_factory=list)
    cost_estimate: str = ""
    risk_level: str = "low"
    # Which branch this step belongs to (e.g. "main", "alt-1", "fallback-1")
    branch: str = "main"
    # Step kind: "action" | "decision" | "milestone" | "wait" | "checkpoint" | "research" | "review" | "deliver" | "collaborate"
    kind: str = "action"
    # AI-suggested x position for creative layout
    x_hint: float = 0.0
    # AI-suggested y position for creative layout
    y_hint: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "duration_minutes": self.duration_minutes,
            "success_probability": self.success_probability,
            "location": self.location, "description": self.description,
            "fallback": self.fallback, "depends_on": list(self.depends_on),
            "sub_goals": list(self.sub_goals),
            "cost_estimate": self.cost_estimate, "risk_level": self.risk_level,
            "branch": self.branch, "kind": self.kind,
            "x_hint": self.x_hint, "y_hint": self.y_hint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RouteStep":
        # Strip stray RTL/LTR control characters but preserve Persian text
        import re as _re
        _ctrl_pat = _re.compile(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069]')
        def _clean(val: str) -> str:
            return _ctrl_pat.sub('', val)
        def _ensure_list(val):
            """Ensure a value is a list of strings.
            The AI sometimes returns a plain string instead of a list for
            fields like sub_goals/depends_on. Iterating a string yields
            individual characters (♦ب ♦ر ♦س ♦ی bug), so we wrap it.
            """
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                # Split by comma if it looks like a comma-separated list
                if ',' in val:
                    return [v.strip() for v in val.split(',') if v.strip()]
                # Single string — wrap in a list
                return [val] if val.strip() else []
            return []
        raw_depends = data.get("depends_on", [])
        raw_sub_goals = data.get("sub_goals", [])
        return cls(
            id=_clean(str(data.get("id", ""))),
            title=_clean(str(data.get("title", "Untitled step"))),
            duration_minutes=int(data.get("duration_minutes", 0)),
            success_probability=float(data.get("success_probability", 0.5)),
            location=_clean(str(data.get("location", ""))),
            description=_clean(str(data.get("description", ""))),
            fallback=_clean(str(data.get("fallback", ""))),
            depends_on=[_clean(str(x)) for x in _ensure_list(raw_depends)],
            sub_goals=[_clean(str(x)) for x in _ensure_list(raw_sub_goals)],
            cost_estimate=_clean(str(data.get("cost_estimate", ""))),
            risk_level=_clean(str(data.get("risk_level", "low"))),
            branch=_clean(str(data.get("branch", "main"))),
            kind=_clean(str(data.get("kind", "action"))),
            x_hint=float(data.get("x_hint", data.get("x", 0.0))),
            y_hint=float(data.get("y_hint", data.get("y", 0.0))),
        )


@dataclass
class RouteEdge:
    """
    An edge between two steps. Can be:
      - "primary" (solid arrow, normal dependency)
      - "alternative" (dashed arrow, optional alternative path)
      - "fallback" (dotted arrow, used if the source step fails)
      - "merge" (thick arrow, where branches rejoin)
    """
    source_id: str
    target_id: str
    kind: str = "primary"  # primary | alternative | fallback | merge
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id, "target_id": self.target_id,
            "kind": self.kind, "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RouteEdge":
        return cls(
            source_id=str(data.get("source_id", "")),
            target_id=str(data.get("target_id", "")),
            kind=str(data.get("kind", "primary")),
            label=str(data.get("label", "")),
        )


@dataclass
class Insight:
    """A floating insight box that appears around the route graph.

    kind can be:
      - "improvement"  — a suggested improvement
      - "alternative"  — an alternative approach
      - "breakthrough" — a BIG BLUE FLASH: a radical alternative way to achieve the goal
      - "skip"         — a WHIRLY ARROW: you can skip this part entirely
      - "loop"         — a CIRCLING ARROW: this step can be repeated/looped
      - "question"     — an open question
      - "warning"      — a risk or warning
    """
    kind: str  # "improvement" | "alternative" | "breakthrough" | "skip" | "loop" | "question" | "warning"
    title: str
    body: str
    anchor_step_id: Optional[str] = None
    x_hint: float = 0.5
    y_hint: float = 0.5

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "body": self.body,
            "anchor_step_id": self.anchor_step_id,
            "x_hint": self.x_hint, "y_hint": self.y_hint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Insight":
        return cls(
            kind=str(data.get("kind", "improvement")),
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            anchor_step_id=data.get("anchor_step_id"),
            x_hint=float(data.get("x_hint", 0.5)),
            y_hint=float(data.get("y_hint", 0.5)),
        )


@dataclass
class MultipleChoiceQuestion:
    question: str
    options: list[str] = field(default_factory=list)
    allow_custom: bool = True
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question, "options": list(self.options),
            "allow_custom": self.allow_custom, "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MultipleChoiceQuestion":
        return cls(
            question=str(data.get("question", "")),
            options=[str(x) for x in data.get("options", [])],
            allow_custom=bool(data.get("allow_custom", True)),
            hint=str(data.get("hint", "")),
        )


@dataclass
class Route:
    """
    A complete AI-generated route — a complex interconnected graph.

    Has multiple branches, alternative paths, fallbacks, and merge points.
    NOT a straight line.
    """
    goal: str
    steps: list[RouteStep] = field(default_factory=list)
    edges: list[RouteEdge] = field(default_factory=list)  # explicit edges
    overall_success_probability: float = 0.0
    total_duration_minutes: int = 0
    improvements: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    summary: str = ""
    clarifying_questions: list[str] = field(default_factory=list)
    raw_response: str = ""
    insights: list[Insight] = field(default_factory=list)
    # AI-chosen creative layout style: "organic", "spiral", "tree", "constellation", etc.
    layout_style: str = ""

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "edges": [e.to_dict() for e in self.edges],
            "overall_success_probability": self.overall_success_probability,
            "total_duration_minutes": self.total_duration_minutes,
            "improvements": list(self.improvements),
            "follow_up_questions": list(self.follow_up_questions),
            "summary": self.summary,
            "clarifying_questions": list(self.clarifying_questions),
            "raw_response": self.raw_response,
            "insights": [i.to_dict() for i in self.insights],
            "layout_style": self.layout_style,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Route":
        return cls(
            goal=str(data.get("goal", "")),
            steps=[RouteStep.from_dict(s) for s in data.get("steps", [])],
            edges=[RouteEdge.from_dict(e) for e in data.get("edges", [])],
            overall_success_probability=float(data.get("overall_success_probability", 0.0)),
            total_duration_minutes=int(data.get("total_duration_minutes", 0)),
            improvements=[str(x) for x in data.get("improvements", [])],
            follow_up_questions=[str(x) for x in data.get("follow_up_questions", [])],
            summary=str(data.get("summary", "")),
            clarifying_questions=[str(x) for x in data.get("clarifying_questions", [])],
            raw_response=str(data.get("raw_response", "")),
            insights=[Insight.from_dict(i) for i in data.get("insights", [])],
            layout_style=str(data.get("layout_style", "")),
        )


@dataclass
class JournalEntry:
    id: str
    timestamp: str
    user_goal: str
    clarifying_questions_asked: list[str]
    user_answers: list[str]
    route: Optional[Route]
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "timestamp": self.timestamp,
            "user_goal": self.user_goal,
            "clarifying_questions_asked": list(self.clarifying_questions_asked),
            "user_answers": list(self.user_answers),
            "route": self.route.to_dict() if self.route else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JournalEntry":
        return cls(
            id=str(data.get("id", "")),
            timestamp=str(data.get("timestamp", "")),
            user_goal=str(data.get("user_goal", "")),
            clarifying_questions_asked=[str(x) for x in data.get("clarifying_questions_asked", [])],
            user_answers=[str(x) for x in data.get("user_answers", [])],
            route=Route.from_dict(data["route"]) if data.get("route") else None,
            notes=str(data.get("notes", "")),
        )


# ---- Status messages for streaming ----

# When streaming JSON, we periodically emit meaningful status messages
# to the UI so the user sees progress (not raw JSON).

_STATUS_PHRASES = [
    "Analysing your goal…",
    "Breaking the goal into sub-problems…",
    "Identifying key constraints…",
    "Mapping out the primary path…",
    "Considering alternative approaches…",
    "Building fallback branches…",
    "Adding checkpoint milestones…",
    "Computing time estimates…",
    "Estimating success probabilities…",
    "Connecting the dots…",
    "Adding parallel branches…",
    "Refining the route graph…",
    "Generating insights…",
    "Finalising the route…",
]


# ---- AI service ----

class AIService:
    """
    Wraps calls to the z.ai GLM API with streaming support.

    Streaming sends MEANINGFUL STATUS TEXT to the UI (not raw JSON).
    The UI shows a 'building route…' box while the JSON streams in
    invisibly.
    """

    def __init__(self) -> None:
        self.settings = load_ai_settings()
        self._cancel_flags: dict[str, bool] = {}

    def update_settings(self, **changes) -> None:
        self.settings.update(changes)
        save_ai_settings(self.settings)

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.get("api_key"))

    # ---- Low-level API call (non-streaming) ----
    def _call_api(self, messages: list[dict],
                  temperature: Optional[float] = None,
                  max_tokens: Optional[int] = None,
                  response_format_json: bool = False) -> dict:
        payload = {
            "model": self.settings.get("model", DEFAULT_MODEL),
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": temperature if temperature is not None
                           else self.settings.get("temperature", 0.7),
            "max_tokens": max_tokens if max_tokens is not None
                          else self.settings.get("max_tokens", 8192),
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.settings.get("base_url", API_URL),
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.get('api_key', '')}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}") from e

    # ---- Streaming API call (returns full text, fires on_status for progress) ----
    def _call_api_streaming(self, messages: list[dict],
                             on_status: Optional[Callable[[str], None]] = None,
                             request_id: Optional[str] = None,
                             temperature: Optional[float] = None,
                             max_tokens: Optional[int] = None,
                             response_format_json: bool = False) -> str:
        """
        Stream a chat completion. Returns the full concatenated text.

        Instead of sending raw JSON chunks to the UI, we periodically
        emit meaningful status messages via on_status so the user sees
        progress like 'Building fallback branches…' instead of JSON.
        """
        payload = {
            "model": self.settings.get("model", DEFAULT_MODEL),
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": temperature if temperature is not None
                           else self.settings.get("temperature", 0.7),
            "max_tokens": max_tokens if max_tokens is not None
                          else self.settings.get("max_tokens", 8192),
            "stream": True,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.settings.get("base_url", API_URL),
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.get('api_key', '')}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        full_text = ""
        chunk_count = 0
        status_idx = 0
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    if request_id and self._cancel_flags.get(request_id):
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        chunk_count += 1
                        # Every ~50 chunks, emit a meaningful status message
                        if on_status is not None and chunk_count % 50 == 0:
                            if status_idx < len(_STATUS_PHRASES):
                                try:
                                    on_status(_STATUS_PHRASES[status_idx])
                                except Exception:
                                    pass
                                status_idx += 1
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}") from e
        return full_text

    def cancel_request(self, request_id: str) -> None:
        self._cancel_flags[request_id] = True

    # ---- Async wrappers ----
    def _run_async(self, fn: Callable[[], Any],
                   callback: Callable[[bool, Any], None]) -> None:
        def _worker():
            try:
                result = fn()
                callback(True, result)
            except Exception as e:
                callback(False, e)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # ---- Step 1: Generate clarifying questions (multiple-choice, streaming status) ----
    def generate_clarifying_questions_streaming(
        self, user_goal: str,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Ask the AI for clarifying questions as multiple-choice.
        on_status fires with meaningful messages like 'Analysing your goal…'.
        """
        # Emit initial status immediately
        try:
            on_status("Analysing your goal…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask, an AI route-planning assistant. Your job is to "
            "help the user achieve a goal by breaking it down into a "
            "COMPLEX, INTERCONNECTED route graph with multiple branches, "
            "alternatives, and fallbacks.\n\n"
            "PERSIAN / FARSI LANGUAGE RULES:\n"
            "If the user's goal is in Persian (Farsi), ask ALL clarifying questions "
            "in Persian. Use natural, idiomatic Persian — not translated English. "
            "Options should be in Persian too.\n\n"
            "Given the user's goal, decide whether it is clear enough to plan "
            "a route, or whether you need to ask clarifying questions first.\n\n"
            "Output STRICT JSON only (no markdown, no commentary) with this schema:\n"
            "{\n"
            "  \"is_clear\": boolean,\n"
            "  \"acknowledgment\": string,  // short sentence acknowledging the goal\n"
            "  \"questions\": [\n"
            "    {\n"
            "      \"question\": string,\n"
            "      \"options\": [string, string, string, string, string, string],  // 4-6 options\n"
            "      \"allow_custom\": true,\n"
            "      \"hint\": string\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- If the goal is clear (specific time, location, constraint), set "
            "is_clear=true and leave questions empty.\n"
            "- Otherwise, generate 2-8 multiple-choice questions.\n"
            "- Each question MUST have 4-6 options (more options = more precision).\n"
            "- Options should cover the most common cases AND edge cases.\n"
            "- The user will be able to type a custom answer if none of the options fit.\n"
            "- Ask DEEP questions: not just 'when?' but also 'what's the biggest risk?', "
            "'what resources are available?', 'who else is involved?', 'what happens if it fails?'.\n"
            "- Think about: constraints, resources, timeline, risks, dependencies, "
            "stakeholders, budget, quality requirements, and success criteria.\n"
            "- Maximum 8 questions but make each one count.\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User goal: {user_goal}"},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.4, response_format_json=True,
                max_tokens=8192,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
            raw_questions = parsed.get("questions", [])
            parsed["questions"] = [MultipleChoiceQuestion.from_dict(q) for q in raw_questions]
            return parsed

        self._run_async(_do, callback)

    # ---- Step 2: Generate the route (COMPLEX interconnected graph) ----
    def generate_route_streaming(
        self, user_goal: str, clarifying_qa: list[tuple[str, str]],
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
        on_step: Optional[Callable[[RouteStep], None]] = None,
        on_edge: Optional[Callable[[RouteEdge], None]] = None,
        on_insight: Optional[Callable[[Insight], None]] = None,
        existing_context: Optional[str] = None,
    ) -> None:
        """
        Generate a complete Route with COMPLEX, INTERCONNECTED structure.

        TRUE STREAMING: as the AI generates each step/edge/insight,
        the corresponding callback fires IMMEDIATELY so the UI can
        add nodes to the canvas one-by-one (not all at once).

        Args:
          on_status: meaningful progress messages
          on_step: called for EACH step as soon as it's parsed
          on_edge: called for each edge as soon as it's parsed
          on_insight: called for each insight as soon as it's parsed
          existing_context: optional text describing existing tasks/nodes
                            the AI should be aware of
          callback: final (success, Route) when done
        """
        try:
            on_status("Building the route graph…")
        except Exception:
            pass


        system_prompt = (
            "You are Rask, an AI route-planning assistant. Given the user's "
            "goal and the answers to clarifying questions, you must produce "
            "a COMPLEX, INTERCONNECTED route graph — NOT a straight line.\n\n"
            "PERSIAN / FARSI LANGUAGE RULES:\n"
            "If the user's goal is in Persian (Farsi), respond ENTIRELY in Persian. "
            "All titles, descriptions, labels, and insights should be in Persian. "
            "Use Persian digits (۰-۹) in text where appropriate. "
            "Persian text in 'title' and 'description' fields should be naturally "
            "flowing — written as a native Persian speaker would express it, "
            "NOT translated word-by-word from English.\n\n"
            "The route MUST have:\n"
            "  - At least 3 branches (places where the path splits into parallel options)\n"
            "  - At least one 'alternative' edge (a different way to achieve a sub-goal)\n"
            "  - At least one 'fallback' edge (what to do if a step fails)\n"
            "  - A merge point where branches rejoin\n"
            "  - At least one 'decision' node, one 'checkpoint' node, and one 'review' node\n"
            "  - Between 10 and 20 steps total (more steps = more granular and actionable plan)\n"
            "  - Each step should have 1-3 sub_goals when appropriate\n\n"
            "Output STRICT JSON only (no markdown, no commentary) with this schema:\n"
            "{\n"
            "  \"goal\": string,\n"
            "  \"summary\": string,\n"
            "  \"layout_style\": string,  // your creative layout name: \"organic\", \"spiral\", \"tree\", \"constellation\", \"wave\", \"river\", \"galaxy\"\n"
            "  \"steps\": [\n"
            "    {\n"
            "      \"id\": string,\n"
            "      \"title\": string,\n"
            "      \"description\": string,\n"
            "      \"duration_minutes\": integer,\n"
            "      \"success_probability\": float,\n"
            "      \"location\": string,\n"
            "      \"fallback\": string,\n"
            "      \"depends_on\": [string],\n"
            "      \"sub_goals\": [string],  // IMPORTANT: MUST be a JSON array of strings, e.g. [\"sub-goal 1\", \"sub-goal 2\"]. NEVER a single string!\n"
            "      \"cost_estimate\": string,\n"
            "      \"risk_level\": string,\n"
            "      \"branch\": string,\n"
            "      \"kind\": string,  // \"action\" | \"decision\" | \"milestone\" | \"wait\" | \"checkpoint\" | \"research\" | \"review\" | \"deliver\" | \"collaborate\"\n"
            "      \"x\": float,  // your suggested x pixel position for this node\n"
            "      \"y\": float   // your suggested y pixel position for this node\n"
            "    }\n"
            "  ],\n"
            "  \"edges\": [\n"
            "    {\n"
            "      \"source_id\": string,\n"
            "      \"target_id\": string,\n"
            "      \"kind\": string,\n"
            "      \"label\": string\n"
            "    }\n"
            "  ],\n"
            "  \"overall_success_probability\": float,\n"
            "  \"total_duration_minutes\": integer,\n"
            "  \"improvements\": [string],\n"
            "  \"follow_up_questions\": [string],\n"
            "  \"insights\": [\n"
            "    {\n"
            "      \"kind\": string,\n"
            "      \"title\": string,\n"
            "      \"body\": string,\n"
            "      \"anchor_step_id\": string | null,\n"
            "      \"x_hint\": float,\n"
            "      \"y_hint\": float\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "CRITICAL RULES:\n"
            "1. Generate 10-20 steps. NOT a single linear chain — at least 3 branches.\n"
            "2. List ALL edges explicitly in the 'edges' array. EVERY connection between "
            "steps MUST appear in 'edges'. The number of edges should be AT LEAST "
            "steps.length - 1, typically more because of branches and alternatives.\n"
            "3. CRITICAL: The 'id' field of each step MUST be used EXACTLY as-is in "
            "'source_id' and 'target_id' of edges and in 'depends_on' arrays. "
            "Use simple short IDs like 'a', 'b', 'c' or '1', '2', '3'. "
            "Do NOT add prefixes or change the format between steps and edges.\n"
            "4. Use edge kinds: 'primary' (normal), 'alternative' (different option), "
            "'fallback' (if step fails), 'merge' (branches rejoin).\n"
            "5. Titles and descriptions should be COMPLETE — never truncate.\n"
            "6. Generate 5-10 floating insights. Include these special annotation types:\n"
            "   - 'breakthrough': A radical alternative way — a completely different approach that could "
            "shortcut the entire plan. Use when there's a creative or unexpected path.\n"
            "   - 'skip': A step or section that can be entirely skipped with an explanation of why. "
            "Use when something is optional or can be bypassed.\n"
            "   - 'loop': A step that can be repeated/looped multiple times to accumulate results. "
            "Use when repetition helps achieve the goal faster.\n"
            "   Also include regular insights: 'improvement', 'alternative', 'warning', 'question'.\n"
            "   Each insight MUST have an 'anchor_step_id' pointing to the relevant step.\n"
            "7. Be THOROUGH — provide detailed descriptions that explain WHY each step matters, "
            "not just WHAT to do. Include tips, gotchas, and pro-tips in descriptions.\n"
            "8. CRITICAL: sub_goals MUST be a JSON ARRAY of strings, never a plain string.\n"
            "   Correct: \"sub_goals\": [\"research competitors\", \"define target audience\"]\n"
            "   WRONG: \"sub_goals\": \"research competitors, define target audience\"\n"
            "   WRONG: \"sub_goals\": \"بررسی رقبا\" (this breaks the UI!)\n"
            "9. depends_on MUST also be a JSON ARRAY of step IDs.\n"
            "10. Each step's 'depends_on' array MUST list the IDs of steps it depends on. "
            "These MUST match the step IDs exactly.\n\n"
            "CREATIVE LAYOUT RULES — you decide how the nodes are positioned:\n"
            "- Every step MUST have 'x' and 'y' fields with pixel positions.\n"
            "- The coordinate system: (0,0) is center. Positive x goes RIGHT, positive y goes DOWN.\n"
            "- STARTING steps (no dependencies) should be placed on the RIGHT side (high x values like 800-1200).\n"
            "- ENDING steps (no dependents) should be placed on the LEFT side (negative x values like -800 to -1200).\n"
            "- This creates a RIGHT-TO-LEFT flow direction, matching RTL reading.\n"
            "- Different branches should spread out VERTICALLY — main branch near y=0, "
            "alternatives above (negative y), fallbacks below (positive y).\n"
            "- Nodes should be at LEAST 300 pixels apart from each other.\n"
            "- Be CREATIVE with layout! Try layouts like:\n"
            "  * 'spiral' — nodes spiral outward from the start\n"
            "  * 'constellation' — nodes form a star pattern with the goal at center\n"
            "  * 'tree' — classic tree with root on the right\n"
            "  * 'wave' — nodes follow a sine-wave pattern\n"
            "  * 'river' — main path flows like a river with tributaries\n"
            "  * 'galaxy' — clusters of nodes around key decision points\n"
            "- The 'layout_style' field should name your chosen layout style.\n"
            "- Connected nodes should be closer together than unconnected ones.\n"
            "- Make the layout visually beautiful and easy to follow.\n"
        )

        user_content = f"User goal: {user_goal}\n\n"
        if clarifying_qa:
            user_content += "Clarifying Q&A:\n"
            for q, a in clarifying_qa:
                user_content += f"  Q: {q}\n  A: {a}\n\n"
        if existing_context:
            user_content += (
                "\nEXISTING CONTEXT — the user already has these tasks/nodes "
                "in their workspace. Build the route AROUND them where "
                "relevant, and you may reference them in depends_on by their id:\n"
                f"{existing_context}\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.85, response_format_json=True,
                max_tokens=16384,
            )
            full = _strip_markdown_fences(full)
            # Parse with fallback for partial/malformed JSON
            try:
                parsed = json.loads(full)
            except json.JSONDecodeError:
                repaired = _repair_json(full)
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = _extract_partial(full)
            route = Route.from_dict(parsed)
            route.raw_response = full
            # Fire per-step / per-edge / per-insight callbacks for TRUE streaming
            if on_step is not None:
                for step in route.steps:
                    try:
                        on_step(step)
                    except Exception:
                        pass
            if on_edge is not None:
                for edge in route.edges:
                    try:
                        on_edge(edge)
                    except Exception:
                        pass
            if on_insight is not None:
                for insight in route.insights:
                    try:
                        on_insight(insight)
                    except Exception:
                        pass
            return route

        self._run_async(_do, callback)

    # ---- Step 3: Continue working after route generation ----
    def continue_working_streaming(
        self, route: Route,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        After a route is generated, ask the AI to continue working:
          - Suggest alternative route options
          - Identify breakthroughs
          - Ask more questions
          - Add MORE nodes/edges to the graph (not just insights)
        """
        try:
            on_status("Continuing to work on your route…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask. The user has a route. Now CONTINUE WORKING:\n"
            "  - Add MORE steps and edges to the graph (alternative paths, fallbacks)\n"
            "  - Suggest breakthrough ideas\n"
            "  - Ask follow-up questions\n"
            "  - Flag warnings\n\n"
            "PERSIAN / FARSI LANGUAGE RULES:\n"
            "If the user's goal is in Persian (Farsi), respond ENTIRELY in Persian. "
            "All titles, descriptions, labels, and insights should be in Persian. "
            "Use Persian digits (۰-۹) in text where appropriate.\n\n"
            "Output STRICT JSON only with this schema:\n"
            "{\n"
            "  \"reflection\": string,  // 1-2 sentence reflection\n"
            "  \"new_steps\": [RouteStep],  // same schema as before, NEW steps to add\n"
            "  \"new_edges\": [RouteEdge],  // edges connecting new steps to existing ones\n"
            "  \"new_insights\": [Insight]  // floating insights\n"
            "}\n\n"
            "Rules:\n"
            "- Generate 3-8 new steps that branch off the existing route.\n"
            "- Connect them via 'alternative' or 'fallback' edges to existing steps.\n"
            "- Generate 3-6 new insights including breakthrough/skip/loop types.\n"
            "- Make alternatives genuinely different (not minor variations).\n"
            "- IMPORTANT: sub_goals and depends_on MUST be JSON ARRAYS, never plain strings.\n"
        )
        route_summary = (
            f"Goal: {route.goal}\n"
            f"Summary: {route.summary}\n"
            f"Existing steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            route_summary += f"  [{s.id}] {s.title} (branch={s.branch}, kind={s.kind})\n"
        route_summary += f"\nExisting edges ({len(route.edges)}):\n"
        for e in route.edges:
            route_summary += f"  {e.source_id} --{e.kind}--> {e.target_id}\n"
        route_summary += f"\nOverall success: {route.overall_success_probability:.0%}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": route_summary},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.9, response_format_json=True,
                max_tokens=16384,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
            from_dict = RouteStep.from_dict
            from_edge = RouteEdge.from_dict
            from_insight = Insight.from_dict
            return {
                "reflection": parsed.get("reflection", ""),
                "new_steps": [from_dict(s) for s in parsed.get("new_steps", [])],
                "new_edges": [from_edge(e) for e in parsed.get("new_edges", [])],
                "new_insights": [from_insight(i) for i in parsed.get("new_insights", [])],
            }

        self._run_async(_do, callback)

    # ---- Schedule route in calendar (context-aware, intelligent) ----
    def schedule_in_calendar_streaming(
        self, route: Route, start_datetime: str,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        preferences: Optional[dict] = None,
        existing_events: Optional[list[dict]] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Context-aware, intelligent AI scheduler.

        Creates a REALISTIC schedule that guarantees goal achievement by
        respecting user preferences, existing calendar events, and pacing
        work appropriately for the goal's scope.

        New parameters:
          preferences: dict with keys like:
            - daily_hours: float (hours available per day)
            - preferred_time: str ("morning" | "afternoon" | "evening")
            - start_date: str (ISO date)
            - avoid_days: list[str] (e.g. ["Friday"])
            - intensity: str ("relaxed" | "balanced" | "intensive")
          existing_events: list[dict] where each has:
            - title: str
            - start_iso: str (ISO 8601 datetime)
            - end_iso: str (ISO 8601 datetime)

        Returns a dict with:
          events: list of event dicts
          schedule_summary: dict with total_events, total_hours, etc.
        """
        try:
            on_status("Building your intelligent schedule…")
        except Exception:
            pass

        preferences = preferences or {}
        existing_events = existing_events or []

        # ── Comprehensive system prompt ──────────────────────────────────
        system_prompt = (
            "You are Rask, an intelligent scheduling AI. You create MEANINGFUL, "
            "REALISTIC schedules that guarantee the user reaches their goal.\n\n"
            "CRITICAL RULES:\n"
            "1. CONTEXT AWARENESS: You receive the user's existing calendar events. "
            "NEVER schedule over them. Leave gaps before/after existing events.\n"
            "2. GOAL-APPROPRIATE PACING:\n"
            "   - Short goals (baking a cake, 1 meeting) → schedule within days\n"
            "   - Medium goals (learning a skill, small project) → schedule over weeks\n"
            "   - Long-term goals (کنکور/Konkur exam, university degree) → schedule "
            "over MONTHS or YEARS with daily/weekly study blocks\n"
            "3. MEANINGFUL TIME BLOCKS:\n"
            "   - Study blocks should be 45-90 minutes (research-backed optimal focus duration)\n"
            "   - Include 10-15 min breaks between blocks\n"
            "   - Don't cram — space learning over time (spaced repetition)\n"
            "   - For long-term goals, create RECURRING patterns (e.g., 'Math Practice' "
            "every Mon/Wed/Fri)\n"
            "4. NO OVERFLOW: Respect the user's daily available hours. Don't schedule "
            "more than they said they can do.\n"
            "5. REALISTIC DAILY LOAD:\n"
            "   - 'Relaxed' intensity → 2-3 hours of work per day max\n"
            "   - 'Balanced' → 4-6 hours\n"
            "   - 'Intensive' → 6-8 hours with proper breaks\n"
            "6. AVOID SCHEDULING ON: user-specified avoid_days (e.g., Fridays for rest)\n"
            "7. PREFERRED TIME: Schedule during the user's preferred hours "
            "(morning: 7-12, afternoon: 13-17, evening: 18-22)\n"
            "8. GUARANTEE: The schedule MUST be completable. Every step in the route "
            "should have allocated time. If a step takes 300 hours and the user has "
            "2 hours/day, that's 150 days — schedule it accordingly.\n\n"
            "OUTPUT FORMAT — Strict JSON:\n"
            "{\n"
            '  "events": [\n'
            "    {\n"
            '      "title": string,          // Clear, actionable title\n'
            '      "start": string,          // ISO 8601 datetime (e.g., "2024-03-15T09:00:00")\n'
            '      "end": string,            // ISO 8601 datetime\n'
            '      "description": string,    // What to do in this block + which route step it serves\n'
            '      "color": string,          // Hex color based on step kind\n'
            '      "step_id": string,        // ID of the route step this maps to\n'
            '      "recurrence": string|null // RRULE for recurring events (e.g., "FREQ=WEEKLY;BYDAY=MO,WE,FR") or null\n'
            "    }\n"
            "  ],\n"
            '  "schedule_summary": {\n'
            '    "total_events": int,\n'
            '    "total_hours": float,\n'
            '    "estimated_completion": string,  // ISO date\n'
            '    "daily_hours_average": float,\n'
            '    "guarantee_note": string  // Brief explanation of how this schedule ensures goal completion\n'
            "  }\n"
            "}\n\n"
            "COLOR MAPPING for event types:\n"
            '- action/study: "#D4AF37" (gold)\n'
            '- decision: "#5A8A5A" (green)\n'
            '- milestone: "#C07060" (warm red)\n'
            '- wait: "#5A7FA8" (blue)\n'
            '- checkpoint/review: "#8A6AAA" (purple)\n'
            '- research: "#5A8A8A" (teal)\n'
            '- deliver: "#D4AF37" (gold)\n'
            '- collaborate: "#7A6AAA" (violet)\n'
            '- default: "#D4AF37"\n\n'
            "PERSIAN LANGUAGE: If the route goal is in Persian/Farsi, write event titles "
            "and descriptions in Persian. Use natural, fluent Persian — not word-by-word "
            "translation.\n"
        )

        # ── Build rich context string from parameters ────────────────────
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Route steps with durations, kinds, dependencies
        route_section = (
            f"ROUTE GOAL: {route.goal}\n"
            f"TOTAL ROUTE DURATION: {route.total_duration_minutes} minutes "
            f"({route.total_duration_minutes / 60:.1f} hours)\n"
            f"OVERALL SUCCESS PROBABILITY: {route.overall_success_probability:.0%}\n"
            f"ROUTE SUMMARY: {route.summary}\n"
            f"LAYOUT STYLE: {route.layout_style}\n\n"
            f"STEPS ({len(route.steps)}):\n"
        )
        for s in route.steps:
            deps = ", ".join(s.depends_on) if s.depends_on else "none"
            route_section += (
                f"  [{s.id}] {s.title}\n"
                f"    Duration: {s.duration_minutes} min | "
                f"Kind: {s.kind} | Branch: {s.branch}\n"
                f"    Risk: {s.risk_level} | Success prob: {s.success_probability:.0%} | "
                f"Depends on: {deps}\n"
                f"    Description: {s.description}\n"
                f"    Location: {s.location or 'n/a'} | "
                f"Fallback: {s.fallback or 'none'}\n"
            )

        route_section += f"\nEDGES ({len(route.edges)}):\n"
        for e in route.edges:
            route_section += (
                f"  {e.source_id} --[{e.kind}]--> {e.target_id}"
                f"{' (' + e.label + ')' if e.label else ''}\n"
            )

        # User preferences section
        pref_section = "USER SCHEDULING PREFERENCES:\n"
        if preferences:
            daily_hours = preferences.get("daily_hours")
            pref_section += f"  Daily available hours: {daily_hours}\n" if daily_hours else ""
            preferred_time = preferences.get("preferred_time")
            pref_section += f"  Preferred time of day: {preferred_time}\n" if preferred_time else ""
            start_date = preferences.get("start_date")
            pref_section += f"  Start date: {start_date}\n" if start_date else ""
            avoid_days = preferences.get("avoid_days")
            pref_section += f"  Avoid days: {avoid_days}\n" if avoid_days else ""
            intensity = preferences.get("intensity")
            pref_section += f"  Intensity: {intensity}\n" if intensity else ""
            # Pass through any other preference keys
            known_keys = {"daily_hours", "preferred_time", "start_date", "avoid_days", "intensity"}
            for k, v in preferences.items():
                if k not in known_keys:
                    pref_section += f"  {k}: {v}\n"
        else:
            pref_section += "  (No specific preferences provided — use balanced defaults)\n"

        pref_section += f"\n  Requested start datetime: {start_datetime}\n"

        # Existing calendar events (next 30 days)
        events_section = "EXISTING CALENDAR EVENTS (DO NOT SCHEDULE OVER THESE):\n"
        if existing_events:
            for ev in existing_events:
                events_section += (
                    f"  • {ev.get('title', 'Untitled')}: "
                    f"{ev.get('start_iso', '?')} → {ev.get('end_iso', '?')}\n"
                )
        else:
            events_section += "  (No existing events — calendar is clear)\n"

        # Combine everything into the user message
        user_message = (
            f"CURRENT DATE/TIME (UTC): {now_iso}\n\n"
            f"{route_section}\n"
            f"{pref_section}\n"
            f"{events_section}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.4, response_format_json=True,
                max_tokens=8192,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
            return parsed

        self._run_async(_do, callback)

    # ---- Calendar AI chat (streaming) ----
    def calendar_chat_streaming(
        self, user_message: str, context: dict,
        on_chunk: Callable[[str], None],
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Context-aware AI chat for the Calendar view.

        context contains:
          - current_date: str (Shamsi formatted)
          - current_view: str (month/week/day/year)
          - visible_events: list[dict] (events currently in view)
          - upcoming_events: list[dict] (next 7 days)
          - today_events: list[dict]
        """
        try:
            on_status("Thinking about your schedule…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask, a calendar-savvy AI assistant. You help users understand "
            "their schedule, find conflicts, suggest optimizations, and plan around "
            "busy periods.\n\n"
            "You have access to the user's current calendar view and events. Use this "
            "context to give specific, actionable answers.\n\n"
            "RULES:\n"
            "1. Be concise and practical. Suggest concrete actions.\n"
            "2. When you see conflicts, point them out and suggest resolutions.\n"
            "3. Help the user find free time slots for new activities.\n"
            "4. If the user asks to move things around, suggest the best new times "
            "based on their existing schedule.\n"
            "5. Notice patterns: too many back-to-back meetings, no break time, "
            "overloaded days, etc.\n"
            "6. PERSIAN LANGUAGE: If the user writes in Persian/Farsi, respond "
            "ENTIRELY in Persian. Use natural, idiomatic Persian.\n"
            "7. Never invent events that aren't in the provided context.\n"
            "8. Respond in plain text (not JSON).\n"
        )

        # Build calendar context string
        ctx_parts = []
        current_date = context.get("current_date", "")
        if current_date:
            ctx_parts.append(f"Current date (Shamsi): {current_date}")
        current_view = context.get("current_view", "")
        if current_view:
            ctx_parts.append(f"Current calendar view: {current_view}")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ctx_parts.append(f"Current UTC time: {now_iso}")

        today_events = context.get("today_events", [])
        if today_events:
            ctx_parts.append("\nTODAY'S EVENTS:")
            for ev in today_events:
                ctx_parts.append(
                    f"  • {ev.get('title', '?')}: "
                    f"{ev.get('start_iso', ev.get('start', '?'))} → "
                    f"{ev.get('end_iso', ev.get('end', '?'))}"
                )
        else:
            ctx_parts.append("\nTODAY'S EVENTS: (none)")

        upcoming_events = context.get("upcoming_events", [])
        if upcoming_events:
            ctx_parts.append("\nUPCOMING EVENTS (next 7 days):")
            for ev in upcoming_events:
                ctx_parts.append(
                    f"  • {ev.get('title', '?')}: "
                    f"{ev.get('start_iso', ev.get('start', '?'))} → "
                    f"{ev.get('end_iso', ev.get('end', '?'))}"
                )
        else:
            ctx_parts.append("\nUPCOMING EVENTS (next 7 days): (none)")

        visible_events = context.get("visible_events", [])
        if visible_events:
            ctx_parts.append("\nVISIBLE EVENTS IN CURRENT VIEW:")
            for ev in visible_events:
                ctx_parts.append(
                    f"  • {ev.get('title', '?')}: "
                    f"{ev.get('start_iso', ev.get('start', '?'))} → "
                    f"{ev.get('end_iso', ev.get('end', '?'))}"
                )

        context_str = "\n".join(ctx_parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Calendar context:\n{context_str}\n\nUser question: {user_message}"},
        ]

        def _do():
            # For calendar chat, we stream text chunks directly (like chat_streaming)
            payload = {
                "model": self.settings.get("model", DEFAULT_MODEL),
                "messages": messages,
                "thinking": {"type": "disabled"},
                "temperature": 0.6,
                "max_tokens": self.settings.get("max_tokens", 8192),
                "stream": True,
            }
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.settings.get("base_url", API_URL),
                data=body,
                headers={
                    "Authorization": f"Bearer {self.settings.get('api_key', '')}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                method="POST",
            )
            full_text = ""
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        if request_id and self._cancel_flags.get(request_id):
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            try:
                                on_chunk(content)
                            except Exception:
                                pass
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
            except urllib.error.URLError as e:
                raise RuntimeError(f"Network error: {e.reason}") from e
            return full_text

        self._run_async(_do, callback)

    # ---- AI Calendar Scheduling (streaming, interactive) ----
    def ai_schedule_streaming(
        self, user_request: str, context: dict,
        conversation_history: list[dict],
        on_chunk: Callable[[str], None],
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        AI-powered calendar scheduling.

        The AI has a conversation with the user to understand their scheduling
        needs, then creates events directly in their calendar. It asks
        clarifying questions when necessary.

        context contains:
          - current_date: str (Shamsi formatted)
          - today_events: list[dict]
          - upcoming_events: list[dict]
          - working_hours: str (e.g. "08:00-22:00")
          - calendars: list[dict] (available calendars with id, name, color)

        conversation_history: previous messages in this scheduling session

        The AI responds in one of two modes:
          1. "ask" mode: needs more info → returns { "mode": "ask", "message": "..." }
          2. "schedule" mode: ready to create events → returns {
               "mode": "schedule",
               "message": "...",
               "events": [
                 {
                   "title": "...",
                   "start_iso": "2025-01-15T09:00:00",
                   "end_iso": "2025-01-15T10:00:00",
                   "calendar_id": "cal-default",
                   "description": "...",
                   "all_day": false,
                   "event_type": "task"
                 },
                 ...
               ]
             }

        The callback receives the parsed response dict.
        """
        try:
            on_status("Planning your schedule…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask, an AI scheduling assistant. You help users organize their "
            "calendar by having a natural conversation and then creating events.\n\n"
            "PROCESS:\n"
            "1. Understand what the user wants to schedule (study plan, work blocks, "
            "meetings, habits, etc.)\n"
            "2. Ask clarifying questions if needed (preferred times, durations, "
            "breaks, priorities, conflicts)\n"
            "3. When you have enough information, create a schedule by outputting "
            "events in the specified JSON format.\n\n"
            "RULES:\n"
            "1. Be concise and practical. Don't over-explain.\n"
            "2. If the user writes in Persian/Farsi, respond ENTIRELY in Persian "
            "including event titles and descriptions.\n"
            "3. Respect the user's existing events — don't schedule over them.\n"
            "4. Include reasonable breaks between blocks.\n"
            "5. Start from the current date/time when scheduling.\n"
            "6. Use 24-hour format for times.\n"
            "7. All dates must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).\n"
            "8. The calendar uses Shamsi/Jalali dates internally but events are "
            "stored in Gregorian datetime — always use Gregorian ISO dates in output.\n\n"
            "OUTPUT FORMAT — respond with STRICT JSON only (no markdown):\n"
            "If you need more information:\n"
            '{\n'
            '  "mode": "ask",\n'
            '  "message": "Your clarifying question here..."\n'
            '}\n\n'
            "If you're ready to schedule:\n"
            '{\n'
            '  "mode": "schedule",\n'
            '  "message": "Brief summary of what you\'re scheduling...",\n'
            '  "events": [\n'
            '    {\n'
            '      "title": "Event title",\n'
            '      "start_iso": "2025-01-15T09:00:00",\n'
            '      "end_iso": "2025-01-15T10:30:00",\n'
            '      "calendar_id": "cal-default",\n'
            '      "description": "Optional description",\n'
            '      "all_day": false,\n'
            '      "event_type": "task"\n'
            '    }\n'
            '  ]\n'
            '}\n'
        )

        # Build context string
        ctx_parts = []
        current_date = context.get("current_date", "")
        if current_date:
            ctx_parts.append(f"Current date (Shamsi): {current_date}")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ctx_parts.append(f"Current UTC time: {now_iso}")

        # Local time
        import time as _time
        local_now = datetime.now()
        ctx_parts.append(f"Local time: {local_now.strftime('%Y-%m-%d %H:%M (%A)')}")

        working_hours = context.get("working_hours", "08:00-22:00")
        ctx_parts.append(f"Preferred working hours: {working_hours}")

        today_events = context.get("today_events", [])
        if today_events:
            ctx_parts.append("\nTODAY'S EVENTS:")
            for ev in today_events:
                ctx_parts.append(
                    f"  • {ev.get('title', '?')}: "
                    f"{ev.get('start_iso', ev.get('start', '?'))} → "
                    f"{ev.get('end_iso', ev.get('end', '?'))}"
                )
        else:
            ctx_parts.append("\nTODAY'S EVENTS: (none)")

        upcoming_events = context.get("upcoming_events", [])
        if upcoming_events:
            ctx_parts.append("\nUPCOMING EVENTS (next 7 days):")
            for ev in upcoming_events:
                ctx_parts.append(
                    f"  • {ev.get('title', '?')}: "
                    f"{ev.get('start_iso', ev.get('start', '?'))} → "
                    f"{ev.get('end_iso', ev.get('end', '?'))}"
                )
        else:
            ctx_parts.append("\nUPCOMING EVENTS (next 7 days): (none)")

        calendars = context.get("calendars", [])
        if calendars:
            ctx_parts.append("\nAVAILABLE CALENDARS:")
            for cal in calendars:
                ctx_parts.append(f"  • {cal.get('id', '?')}: {cal.get('name', '?')} ({cal.get('color', '#D4AF37')})")

        context_str = "\n".join(ctx_parts)

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": f"Calendar context:\n{context_str}"})

        # Add conversation history
        for msg in conversation_history:
            messages.append(msg)

        # Add the current user request
        messages.append({"role": "user", "content": user_request})

        def _do():
            payload = {
                "model": self.settings.get("model", DEFAULT_MODEL),
                "messages": messages,
                "thinking": {"type": "disabled"},
                "temperature": 0.5,
                "max_tokens": self.settings.get("max_tokens", 8192),
                "stream": True,
            }
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.settings.get("base_url", API_URL),
                data=body,
                headers={
                    "Authorization": f"Bearer {self.settings.get('api_key', '')}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                method="POST",
            )
            full_text = ""
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        if request_id and self._cancel_flags.get(request_id):
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            try:
                                on_chunk(content)
                            except Exception:
                                pass
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
            except urllib.error.URLError as e:
                raise RuntimeError(f"Network error: {e.reason}") from e

            # Parse the response
            full_text = _strip_markdown_fences(full_text)
            try:
                parsed = json.loads(full_text)
            except json.JSONDecodeError:
                # If AI didn't return valid JSON, treat it as an "ask" response
                parsed = {
                    "mode": "ask",
                    "message": full_text,
                }
            return parsed

        self._run_async(_do, callback)

    # ---- Free-form chat (streaming) ----
    def chat_streaming(
        self, messages: list[dict],
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """Streaming chat — calls on_status with text deltas (REAL text, not JSON)."""
        system = {"role": "system", "content":
            "You are Rask, an AI route-planning assistant. Be concise and helpful. "
            "Respond in plain text (not JSON) unless asked for structured output. "
            "If the user's goal is in Persian (Farsi), respond ENTIRELY in Persian. "
            "All titles, descriptions, labels, and insights should be in Persian. "
            "Use Persian digits (۰-۹) in text where appropriate."}
        all_messages = [system] + messages

        def _do():
            # For chat, we use the streaming API but the chunks ARE the
            # user-visible text (no JSON wrapping)
            payload = {
                "model": self.settings.get("model", DEFAULT_MODEL),
                "messages": all_messages,
                "thinking": {"type": "disabled"},
                "temperature": 0.7,
                "max_tokens": self.settings.get("max_tokens", 8192),
                "stream": True,
            }
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.settings.get("base_url", API_URL),
                data=body,
                headers={
                    "Authorization": f"Bearer {self.settings.get('api_key', '')}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                method="POST",
            )
            full_text = ""
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        if request_id and self._cancel_flags.get(request_id):
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            # For chat, each chunk IS meaningful text
                            try:
                                on_status(content)
                            except Exception:
                                pass
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
            except urllib.error.URLError as e:
                raise RuntimeError(f"Network error: {e.reason}") from e
            return full_text

        self._run_async(_do, callback)

    # ---- AI Route Optimizer ----
    def optimize_route_streaming(
        self, route: Route,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Ask the AI to analyze and optimize the current route:
          - Identify bottlenecks and weak points
          - Suggest parallelization opportunities
          - Add missing fallbacks
          - Optimize time estimates
          - Restructure for better success probability
        """
        try:
            on_status("Analyzing route for optimization opportunities…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask, an AI route optimization expert. Analyze the user's route "
            "and provide OPTIMIZATION suggestions that will improve the route's success "
            "probability, reduce total time, and strengthen the plan.\n\n"
            "Output STRICT JSON only with this schema:\n"
            "{\n"
            "  \"analysis\": string,  // 2-3 sentence analysis of the route\n"
            "  \"overall_health\": float,  // 0.0-1.0 health score\n"
            "  \"optimizations\": [\n"
            "    {\n"
            "      \"kind\": string,  // \"parallelize\" | \"add_fallback\" | \"reorder\" | \"split\" | \"merge\" | \"remove_redundancy\"\n"
            "      \"step_ids\": [string],  // which steps are affected\n"
            "      \"title\": string,  // short title\n"
            "      \"description\": string,  // what to do and why\n"
            "      \"impact\": string,  // \"high\" | \"medium\" | \"low\"\n"
            "      \"estimated_time_savings_minutes\": integer,\n"
            "      \"estimated_probability_boost\": float  // 0.0-1.0\n"
            "    }\n"
            "  ],\n"
            "  \"new_steps\": [RouteStep],  // optional new steps to add\n"
            "  \"new_edges\": [RouteEdge],  // optional new edges\n"
            "  \"new_insights\": [Insight]  // optional new insights\n"
            "}\n\n"
            "Rules:\n"
            "- Generate 5-10 specific, actionable optimizations.\n"
            "- Focus on HIGH-IMPACT changes first.\n"
            "- Each optimization must reference specific step IDs.\n"
            "- Provide realistic time savings and probability boosts.\n"
            "- Optionally add new steps/edges that implement the optimizations.\n"
        )
        route_summary = (
            f"Goal: {route.goal}\n"
            f"Summary: {route.summary}\n"
            f"Overall success: {route.overall_success_probability:.0%}\n"
            f"Total duration: {route.total_duration_minutes} min\n\n"
            f"Steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            route_summary += (
                f"  [{s.id}] {s.title} — {s.duration_minutes}m, "
                f"success={s.success_probability:.0%}, risk={s.risk_level}, "
                f"branch={s.branch}, fallback={'yes' if s.fallback else 'none'}\n"
            )
        route_summary += f"\nEdges ({len(route.edges)}):\n"
        for e in route.edges:
            route_summary += f"  {e.source_id} --{e.kind}--> {e.target_id}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": route_summary},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.6, response_format_json=True,
                max_tokens=8192,
            )
            full = _strip_markdown_fences(full)
            try:
                parsed = json.loads(full)
            except json.JSONDecodeError:
                repaired = _repair_json(full)
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = _extract_partial(full)
            # Parse new steps/edges/insights if present
            if "new_steps" in parsed:
                parsed["new_steps"] = [RouteStep.from_dict(s) for s in parsed.get("new_steps", [])]
            else:
                parsed["new_steps"] = []
            if "new_edges" in parsed:
                parsed["new_edges"] = [RouteEdge.from_dict(e) for e in parsed.get("new_edges", [])]
            else:
                parsed["new_edges"] = []
            if "new_insights" in parsed:
                parsed["new_insights"] = [Insight.from_dict(i) for i in parsed.get("new_insights", [])]
            else:
                parsed["new_insights"] = []
            return parsed

        self._run_async(_do, callback)

    # ---- AI Step Breakdown ----
    def breakdown_step_streaming(
        self, step: RouteStep, route: Route,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Ask the AI to break down a complex step into 2-4 smaller sub-steps.
        Returns new RouteSteps and edges to replace the original step.
        """
        try:
            on_status(f"Breaking down step: {step.title}…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask. The user wants to break down a complex step into smaller "
            "sub-steps. Generate 2-4 new steps that together accomplish the same goal "
            "as the original step, but with better granularity and tracking.\n\n"
            "Output STRICT JSON only:\n"
            "{\n"
            "  \"analysis\": string,  // why this step benefits from breakdown\n"
            "  \"new_steps\": [RouteStep],  // 2-4 sub-steps (use same schema)\n"
            "  \"new_edges\": [RouteEdge],  // edges connecting sub-steps\n"
            "  \"edges_to_parents\": [RouteEdge]  // edges connecting first/last sub-step to the original step's neighbors\n"
            "}\n\n"
            "Rules:\n"
            "- Each sub-step should have a clear, actionable title.\n"
            "- The first sub-step should depend on the original step's predecessors.\n"
            "- The last sub-step should connect to the original step's successors.\n"
            "- Total duration of sub-steps should approximate the original duration.\n"
            "- Assign realistic success probabilities (sub-steps can be higher than parent).\n"
            "- Use unique IDs for new steps (e.g., 'sub-{original_id}-1').\n"
        )
        user_content = (
            f"Original step to break down:\n"
            f"  ID: {step.id}\n"
            f"  Title: {step.title}\n"
            f"  Description: {step.description}\n"
            f"  Duration: {step.duration_minutes} min\n"
            f"  Success probability: {step.success_probability:.0%}\n"
            f"  Risk: {step.risk_level}\n"
            f"  Depends on: {step.depends_on}\n"
            f"  Fallback: {step.fallback}\n\n"
            f"Route context ({len(route.steps)} total steps):\n"
        )
        for s in route.steps:
            if s.id != step.id:
                user_content += f"  [{s.id}] {s.title}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.7, response_format_json=True,
                max_tokens=6144,
            )
            full = _strip_markdown_fences(full)
            try:
                parsed = json.loads(full)
            except json.JSONDecodeError:
                repaired = _repair_json(full)
                parsed = json.loads(repaired)
            parsed["new_steps"] = [RouteStep.from_dict(s) for s in parsed.get("new_steps", [])]
            parsed["new_edges"] = [RouteEdge.from_dict(e) for e in parsed.get("new_edges", [])]
            parsed["edges_to_parents"] = [RouteEdge.from_dict(e) for e in parsed.get("edges_to_parents", [])]
            return parsed

        self._run_async(_do, callback)

    # ---- AI Risk Analysis ----
    def analyze_risks_streaming(
        self, route: Route,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Deep risk analysis of the route using AI. Identifies:
          - Single points of failure
          - Cascade failure risks
          - Resource conflicts
          - External dependencies
          - Mitigation strategies
        """
        try:
            on_status("Running deep risk analysis on your route…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask, an AI risk analysis expert. Perform a deep risk analysis "
            "of the user's route. Identify all potential failure modes, cascade effects, "
            "and provide concrete mitigation strategies.\n\n"
            "Output STRICT JSON only:\n"
            "{\n"
            "  \"overall_risk_level\": string,  // \"low\" | \"medium\" | \"high\" | \"critical\"\n"
            "  \"risk_score\": float,  // 0.0-1.0 (0=safe, 1=very risky)\n"
            "  \"analysis\": string,  // 2-3 sentence summary\n"
            "  \"risks\": [\n"
            "    {\n"
            "      \"kind\": string,  // \"single_point_of_failure\" | \"cascade\" | \"resource_conflict\" | \"external_dependency\" | \"time_pressure\" | \"probability_gap\"\n"
            "      \"severity\": string,  // \"critical\" | \"high\" | \"medium\" | \"low\"\n"
            "      \"affected_steps\": [string],  // step IDs\n"
            "      \"title\": string,\n"
            "      \"description\": string,\n"
            "      \"mitigation\": string,  // concrete action to reduce risk\n"
            "      \"mitigation_type\": string  // \"add_fallback\" | \"add_alternative\" | \"reorder\" | \"add_step\" | \"change_resource\" | \"adjust_timeline\"\n"
            "    }\n"
            "  ],\n"
            "  \"critical_path_risks\": [string],  // step IDs on critical path with risks\n"
            "  \"recommended_actions\": [string]  // top 3-5 prioritized actions\n"
            "}\n\n"
            "Rules:\n"
            "- Identify 5-12 specific risks.\n"
            "- Every risk must have a concrete, actionable mitigation.\n"
            "- Prioritize risks on the critical path.\n"
            "- Consider cascade effects (if step X fails, what else fails?).\n"
        )
        route_summary = (
            f"Goal: {route.goal}\n"
            f"Overall success: {route.overall_success_probability:.0%}\n\n"
            f"Steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            route_summary += (
                f"  [{s.id}] {s.title} — {s.duration_minutes}m, "
                f"success={s.success_probability:.0%}, risk={s.risk_level}, "
                f"fallback={'yes' if s.fallback else 'none'}, "
                f"deps={s.depends_on}\n"
            )
        route_summary += f"\nEdges ({len(route.edges)}):\n"
        for e in route.edges:
            route_summary += f"  {e.source_id} --{e.kind}--> {e.target_id}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": route_summary},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.5, response_format_json=True,
                max_tokens=8192,
            )
            full = _strip_markdown_fences(full)
            try:
                parsed = json.loads(full)
            except json.JSONDecodeError:
                repaired = _repair_json(full)
                parsed = json.loads(repaired)
            return parsed

        self._run_async(_do, callback)

    # ---- Smart Re-plan ----
    def smart_replan_streaming(
        self, route: Route, changed_step_id: str, change_description: str,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        When the user edits a step, ask the AI to suggest adjustments to
        dependent steps so the whole route stays coherent.
        """
        try:
            on_status("Adjusting the route based on your changes…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask. The user has edited a step in their route. You must "
            "suggest adjustments to OTHER steps that are affected by this change, "
            "so the entire route stays coherent and achievable.\n\n"
            "Output STRICT JSON only:\n"
            "{\n"
            "  \"analysis\": string,  // how the change affects the route\n"
            "  \"step_adjustments\": [\n"
            "    {\n"
            "      \"step_id\": string,\n"
            "      \"field\": string,  // which field to change\n"
            "      \"old_value\": any,\n"
            "      \"new_value\": any,\n"
            "      \"reason\": string\n"
            "    }\n"
            "  ],\n"
            "  \"new_steps\": [RouteStep],  // optional new steps needed\n"
            "  \"new_edges\": [RouteEdge],  // optional new edges\n"
            "  \"new_insights\": [Insight]  // insights about the impact\n"
            "}\n\n"
            "Rules:\n"
            "- Only suggest changes that are NECESSARY due to the edit.\n"
            "- Don't modify steps that are unaffected.\n"
            "- Provide clear reasons for each adjustment.\n"
            "- If the change invalidates the route, suggest how to restructure.\n"
        )
        step = next((s for s in route.steps if s.id == changed_step_id), None)
        step_info = ""
        if step:
            step_info = (
                f"Changed step:\n"
                f"  ID: {step.id}\n"
                f"  Title: {step.title}\n"
                f"  Duration: {step.duration_minutes}m\n"
                f"  Success: {step.success_probability:.0%}\n\n"
            )
        user_content = (
            f"{step_info}"
            f"Change description: {change_description}\n\n"
            f"Full route ({len(route.steps)} steps):\n"
        )
        for s in route.steps:
            user_content += f"  [{s.id}] {s.title} — {s.duration_minutes}m, success={s.success_probability:.0%}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.6, response_format_json=True,
                max_tokens=16384,
            )
            full = _strip_markdown_fences(full)
            try:
                parsed = json.loads(full)
            except json.JSONDecodeError:
                repaired = _repair_json(full)
                parsed = json.loads(repaired)
            if "new_steps" in parsed:
                parsed["new_steps"] = [RouteStep.from_dict(s) for s in parsed.get("new_steps", [])]
            else:
                parsed["new_steps"] = []
            if "new_edges" in parsed:
                parsed["new_edges"] = [RouteEdge.from_dict(e) for e in parsed.get("new_edges", [])]
            else:
                parsed["new_edges"] = []
            if "new_insights" in parsed:
                parsed["new_insights"] = [Insight.from_dict(i) for i in parsed.get("new_insights", [])]
            else:
                parsed["new_insights"] = []
            return parsed

        self._run_async(_do, callback)

    # ---- AI Self-Critique and Improve ----
    def critique_and_improve_streaming(
        self, route: Route,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Ask the AI to critically review its OWN route plan and suggest
        concrete improvements. This is a 'second pass' that catches
        issues the first generation missed.

        Generates:
          - Identified weaknesses and blind spots
          - New steps that fill gaps
          - New edges for missing connections
          - New insights about improvements
          - A quality score
        """
        try:
            on_status("Critically reviewing the route plan…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask, acting as a CRITICAL REVIEWER of a route plan. "
            "You previously generated this route, but now you must find its "
            "weaknesses, blind spots, and missing elements.\n\n"
            "PERSIAN / FARSI LANGUAGE RULES:\n"
            "If the original goal was in Persian (Farsi), all output text "
            "(titles, descriptions, critiques) should be in Persian.\n\n"
            "Output STRICT JSON only:\n"
            "{\n"
            "  \"quality_score\": float,  // 0.0-1.0 overall plan quality\n"
            "  \"critique\": string,  // 3-5 sentence honest assessment\n"
            "  \"weaknesses\": [\n"
            "    {\n"
            "      \"kind\": string,  // \"missing_step\" | \"weak_fallback\" | \"unrealistic_time\" | \"missing_dependency\" | \"poor_branching\" | \"vague_description\" | \"no_review_checkpoint\"\n"
            "      \"severity\": string,  // \"critical\" | \"high\" | \"medium\" | \"low\"\n"
            "      \"description\": string,\n"
            "      \"suggestion\": string  // how to fix it\n"
            "    }\n"
            "  ],\n"
            "  \"new_steps\": [RouteStep],  // steps to fill identified gaps\n"
            "  \"new_edges\": [RouteEdge],  // edges for new connections\n"
            "  \"new_insights\": [Insight]  // insights about improvements\n"
            "}\n\n"
            "Rules:\n"
            "- Be HONEST — don't say the plan is perfect. Every plan has weaknesses.\n"
            "- Identify 4-8 specific weaknesses.\n"
            "- Generate 2-6 new steps that address the biggest gaps.\n"
            "- Common issues: missing review/checkpoint steps, no fallbacks for risky steps, "
            "unrealistic time estimates, missing dependencies between steps, vague descriptions.\n"
            "- IMPORTANT: sub_goals and depends_on MUST be JSON ARRAYS, never plain strings.\n"
            "- Think about: What would a skeptical project manager say about this plan?\n"
        )
        route_summary = (
            f"Goal: {route.goal}\n"
            f"Summary: {route.summary}\n"
            f"Overall success: {route.overall_success_probability:.0%}\n"
            f"Total duration: {route.total_duration_minutes} min\n\n"
            f"Steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            route_summary += (
                f"  [{s.id}] {s.title} — {s.duration_minutes}m, "
                f"success={s.success_probability:.0%}, risk={s.risk_level}, "
                f"kind={s.kind}, branch={s.branch}\n"
                f"    fallback={'yes' if s.fallback else 'NONE'}, "
                f"sub_goals={s.sub_goals}, deps={s.depends_on}\n"
            )
        route_summary += f"\nEdges ({len(route.edges)}):\n"
        for e in route.edges:
            route_summary += f"  {e.source_id} --{e.kind}--> {e.target_id}\n"
        route_summary += f"\nInsights ({len(route.insights)}):\n"
        for i in route.insights:
            route_summary += f"  [{i.kind}] {i.title}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": route_summary},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.7, response_format_json=True,
                max_tokens=16384,
            )
            full = _strip_markdown_fences(full)
            try:
                parsed = json.loads(full)
            except json.JSONDecodeError:
                repaired = _repair_json(full)
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = _extract_partial(full)
            if "new_steps" in parsed:
                parsed["new_steps"] = [RouteStep.from_dict(s) for s in parsed.get("new_steps", [])]
            else:
                parsed["new_steps"] = []
            if "new_edges" in parsed:
                parsed["new_edges"] = [RouteEdge.from_dict(e) for e in parsed.get("new_edges", [])]
            else:
                parsed["new_edges"] = []
            if "new_insights" in parsed:
                parsed["new_insights"] = [Insight.from_dict(i) for i in parsed.get("new_insights", [])]
            else:
                parsed["new_insights"] = []
            return parsed

        self._run_async(_do, callback)

    # ---- Test the connection ----
    def test_connection(self, callback: Callable[[bool, Any], None]) -> None:
        def _do():
            data = self._call_api(
                [{"role": "user", "content": "Reply with the single word OK."}],
                temperature=0.0, max_tokens=10,
            )
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if "OK" in content.upper():
                return f"Connected successfully using model {self.settings.get('model')}."
            return f"Got unexpected response: {content!r}"
        self._run_async(_do, callback)


# ---- Monte Carlo Simulation Engine ----

class MonteCarloSimulator:
    """
    Simulate a route thousands of times to compute realistic completion
    time estimates and step-level risk metrics.

    Each simulation:
      1. For each step, randomly decide success/failure based on success_probability.
      2. If a step fails and has a fallback, the fallback duration is used instead.
      3. If a step fails with no fallback, the route is marked as "failed at that step".
      4. Compute the critical-path duration considering only successful steps.

    Outputs: P50/P75/P90 completion times, failure rate, per-step failure count.
    """

    def __init__(self, route: Route, n_simulations: int = 5000) -> None:
        self.route = route
        self.n_simulations = n_simulations

    def run(self) -> 'SimulationResult':
        """Run the Monte Carlo simulation and return a SimulationResult."""
        steps_by_id = {s.id: s for s in self.route.steps}
        step_fail_counts: dict[str, int] = {s.id: 0 for s in self.route.steps}
        completion_times: list[int] = []  # in minutes
        failures = 0
        step_completion_times: dict[str, list[int]] = {s.id: [] for s in self.route.steps}

        # Build adjacency for the route graph
        successors: dict[str, list[str]] = {s.id: [] for s in self.route.steps}
        predecessors: dict[str, list[str]] = {s.id: [] for s in self.route.steps}
        for edge in self.route.edges:
            if edge.source_id in successors and edge.target_id in predecessors:
                successors[edge.source_id].append(edge.target_id)
                predecessors[edge.target_id].append(edge.source_id)
        for step in self.route.steps:
            for dep_id in step.depends_on:
                if dep_id in successors and step.id in predecessors:
                    if dep_id not in predecessors[step.id]:
                        predecessors[step.id].append(dep_id)
                    if step.id not in successors[dep_id]:
                        successors[dep_id].append(step.id)

        # Find root steps (no predecessors)
        roots = [s.id for s in self.route.steps if not predecessors.get(s.id)]

        for _ in range(self.n_simulations):
            # Randomly determine success/failure for each step
            step_succeeded: dict[str, bool] = {}
            step_duration: dict[str, int] = {}
            for step in self.route.steps:
                if random.random() < step.success_probability:
                    step_succeeded[step.id] = True
                    # Add some variance to duration (±20%)
                    variance = random.uniform(0.8, 1.2)
                    step_duration[step.id] = int(step.duration_minutes * variance)
                else:
                    step_succeeded[step.id] = False
                    step_fail_counts[step.id] += 1
                    if step.fallback:
                        # Fallback: use 1.5x duration as penalty
                        step_duration[step.id] = int(step.duration_minutes * 1.5)
                    else:
                        step_duration[step.id] = 0  # Will be excluded

            # Compute earliest finish time for each step (topological)
            earliest_finish: dict[str, int] = {}
            visited: set[str] = set()
            failed = False

            def compute_ef(sid: str) -> int:
                if sid in visited:
                    return earliest_finish.get(sid, 0)
                visited.add(sid)
                if not step_succeeded.get(sid, True) and not steps_by_id[sid].fallback:
                    earliest_finish[sid] = 0
                    return 0
                max_pred_ef = 0
                for pid in predecessors.get(sid, []):
                    if not step_succeeded.get(pid, True) and not steps_by_id.get(pid, RouteStep(id="", title="", duration_minutes=0, success_probability=0, location="", description="", fallback="")).fallback:
                        # Predecessor failed without fallback — this step can't start
                        compute_ef(pid)
                        if earliest_finish.get(pid, 0) == 0:
                            earliest_finish[sid] = 0
                            return 0
                    pred_ef = compute_ef(pid)
                    max_pred_ef = max(max_pred_ef, pred_ef)
                ef = max_pred_ef + step_duration.get(sid, 0)
                earliest_finish[sid] = ef
                step_completion_times[sid].append(ef)
                return ef

            for sid in roots:
                compute_ef(sid)

            # Total completion = max of all leaf steps' finish times
            leaves = [s.id for s in self.route.steps if not successors.get(s.id)]
            total = max((earliest_finish.get(lid, 0) for lid in leaves), default=0)

            # Check if any critical step failed without fallback
            for step in self.route.steps:
                if not step_succeeded.get(step.id, True) and not step.fallback:
                    # Check if this step is on any path to a leaf
                    if any(lid in visited for lid in leaves):
                        failed = True
                        break

            if failed:
                failures += 1
            elif total > 0:
                completion_times.append(total)

        # Compute percentiles
        completion_times.sort()
        n = len(completion_times)
        result = SimulationResult(
            n_simulations=self.n_simulations,
            p50_minutes=completion_times[int(n * 0.50)] if n > 0 else 0,
            p75_minutes=completion_times[int(n * 0.75)] if n > 0 else 0,
            p90_minutes=completion_times[int(n * 0.90)] if n > 0 else 0,
            p99_minutes=completion_times[int(n * 0.99)] if n > 0 else 0,
            min_minutes=completion_times[0] if n > 0 else 0,
            max_minutes=completion_times[-1] if n > 0 else 0,
            mean_minutes=sum(completion_times) / n if n > 0 else 0,
            failure_rate=failures / self.n_simulations,
            step_failure_counts=step_fail_counts,
            step_completion_times=step_completion_times,
            completion_time_distribution=self._build_distribution(completion_times),
        )
        return result

    def _build_distribution(self, times: list[int], n_bins: int = 20) -> list[dict]:
        """Build a histogram of completion times for visualization."""
        if not times:
            return []
        min_t = times[0]
        max_t = times[-1]
        if max_t == min_t:
            return [{"start": min_t, "end": max_t, "count": len(times)}]
        bin_width = (max_t - min_t) / n_bins
        bins = []
        for i in range(n_bins):
            start = min_t + i * bin_width
            end = start + bin_width
            count = sum(1 for t in times if start <= t < end)
            bins.append({"start": round(start), "end": round(end), "count": count})
        # Last bin is inclusive
        if bins:
            bins[-1]["count"] += sum(1 for t in times if t == max_t)
        return bins


@dataclass
class SimulationResult:
    """Result of a Monte Carlo simulation of a route."""
    n_simulations: int = 0
    p50_minutes: int = 0
    p75_minutes: int = 0
    p90_minutes: int = 0
    p99_minutes: int = 0
    min_minutes: int = 0
    max_minutes: int = 0
    mean_minutes: float = 0.0
    failure_rate: float = 0.0
    step_failure_counts: dict[str, int] = field(default_factory=dict)
    step_completion_times: dict[str, list[int]] = field(default_factory=dict)
    completion_time_distribution: list[dict] = field(default_factory=list)

    @property
    def histogram(self) -> dict[int, int]:
        """Convert completion_time_distribution to a dict of {bin_start_minute: count}.

        This is the format expected by _HistogramWidget in simulation_view.py.
        """
        if not self.completion_time_distribution:
            return {}
        result: dict[int, int] = {}
        for bin_data in self.completion_time_distribution:
            key = int(bin_data.get("start", 0))
            count = bin_data.get("count", 0)
            result[key] = count
        return result

    def to_dict(self) -> dict:
        return {
            "n_simulations": self.n_simulations,
            "p50_minutes": self.p50_minutes,
            "p75_minutes": self.p75_minutes,
            "p90_minutes": self.p90_minutes,
            "p99_minutes": self.p99_minutes,
            "min_minutes": self.min_minutes,
            "max_minutes": self.max_minutes,
            "mean_minutes": self.mean_minutes,
            "failure_rate": self.failure_rate,
            "step_failure_counts": self.step_failure_counts,
            "completion_time_distribution": self.completion_time_distribution,
        }


# ---- Route Health Score Engine ----

class RouteHealthEngine:
    """
    Computes a comprehensive health score for a route based on:
      - Step success probabilities
      - Risk levels
      - Fallback coverage
      - Branch complexity
      - Critical path vulnerability
      - Time estimates vs. dependencies

    Health score is 0-100, where:
      90-100: Excellent (well-structured, high probability, good fallbacks)
      70-89:  Good (minor issues)
      50-69:  Fair (some risks, missing fallbacks)
      30-49:  Poor (significant risks, low probabilities)
      0-29:   Critical (route likely to fail)
    """

    @staticmethod
    def compute(route: Route) -> 'RouteHealthReport':
        if not route.steps:
            return RouteHealthReport(overall_score=0, grade="F", metrics={})

        steps = route.steps
        n_steps = len(steps)

        # 1. Average success probability (0-100, weighted)
        avg_prob = sum(s.success_probability for s in steps) / n_steps
        prob_score = avg_prob * 40  # Up to 40 points

        # 2. Fallback coverage (what % of steps have fallbacks?)
        fallback_pct = sum(1 for s in steps if s.fallback) / n_steps
        fallback_score = fallback_pct * 15  # Up to 15 points

        # 3. Risk level distribution
        risk_weights = {"low": 1.0, "medium": 0.6, "high": 0.3, "severe": 0.1}
        avg_risk = sum(risk_weights.get(s.risk_level, 0.5) for s in steps) / n_steps
        risk_score = avg_risk * 15  # Up to 15 points

        # 4. Branch complexity (having alternatives is good, but not too many)
        branches = set(s.branch for s in steps)
        n_branches = len(branches)
        if n_branches <= 1:
            branch_score = 5  # No alternatives = poor
        elif n_branches <= 3:
            branch_score = 12  # Good variety
        elif n_branches <= 5:
            branch_score = 10  # Getting complex
        else:
            branch_score = 6  # Too complex

        # 5. Step kind variety (having decisions and checkpoints is good)
        kinds = set(s.kind for s in steps)
        kind_variety_score = min(len(kinds) * 3, 10)  # Up to 10 points

        # 6. Dependency health (are there steps with too many deps?)
        max_deps = max((len(s.depends_on) for s in steps), default=0)
        if max_deps <= 2:
            dep_score = 10
        elif max_deps <= 4:
            dep_score = 7
        elif max_deps <= 6:
            dep_score = 4
        else:
            dep_score = 2

        overall = prob_score + fallback_score + risk_score + branch_score + kind_variety_score + dep_score
        overall = max(0, min(100, overall))

        # Grade
        if overall >= 90:
            grade = "A+"
        elif overall >= 80:
            grade = "A"
        elif overall >= 70:
            grade = "B"
        elif overall >= 60:
            grade = "C"
        elif overall >= 50:
            grade = "D"
        else:
            grade = "F"

        # Identify bottlenecks (steps with low success probability that many others depend on)
        bottlenecks = []
        dependents_count: dict[str, int] = {}
        for edge in route.edges:
            dependents_count[edge.source_id] = dependents_count.get(edge.source_id, 0) + 1
        for step in steps:
            n_deps = dependents_count.get(step.id, 0)
            if step.success_probability < 0.6 and n_deps >= 2:
                bottlenecks.append(step.id)
            elif step.success_probability < 0.4:
                bottlenecks.append(step.id)

        # Identify orphan steps (no edges to/from them)
        connected = set()
        for edge in route.edges:
            connected.add(edge.source_id)
            connected.add(edge.target_id)
        for step in steps:
            for dep_id in step.depends_on:
                connected.add(dep_id)
                connected.add(step.id)
        orphans = [s.id for s in steps if s.id not in connected]

        metrics = {
            "avg_success_probability": round(avg_prob, 3),
            "fallback_coverage_pct": round(fallback_pct, 3),
            "avg_risk_score": round(avg_risk, 3),
            "n_branches": n_branches,
            "n_kinds": len(kinds),
            "max_dependency_depth": max_deps,
            "bottleneck_steps": bottlenecks,
            "orphan_steps": orphans,
            "prob_score": round(prob_score, 1),
            "fallback_score": round(fallback_score, 1),
            "risk_score": round(risk_score, 1),
            "branch_score": round(branch_score, 1),
            "kind_score": round(kind_variety_score, 1),
            "dep_score": round(dep_score, 1),
        }

        return RouteHealthReport(
            overall_score=round(overall, 1),
            grade=grade,
            metrics=metrics,
            bottlenecks=bottlenecks,
            orphans=orphans,
            recommendations=RouteHealthEngine._generate_recommendations(metrics, steps),
        )

    @staticmethod
    def _generate_recommendations(metrics: dict, steps: list[RouteStep]) -> list[str]:
        recs = []
        if metrics["avg_success_probability"] < 0.6:
            recs.append("⚠ Overall success probability is low. Consider adding fallbacks or breaking down risky steps.")
        if metrics["fallback_coverage_pct"] < 0.3:
            recs.append("⚠ Less than 30% of steps have fallbacks. Add fallback plans for critical steps.")
        if metrics["avg_risk_score"] < 0.5:
            recs.append("⚠ Average risk is high. Review high-risk steps and add mitigations.")
        if metrics["n_branches"] <= 1:
            recs.append("💡 No alternative branches detected. Adding parallel paths improves resilience.")
        if metrics["bottleneck_steps"]:
            recs.append(f"🔴 {len(metrics['bottleneck_steps'])} bottleneck step(s) detected. These are low-probability steps that many others depend on.")
        if metrics["orphan_steps"]:
            recs.append(f"🔗 {len(metrics['orphan_steps'])} orphan step(s) detected — they have no connections to other steps.")
        if metrics["max_dependency_depth"] > 4:
            recs.append("📐 Some steps have too many dependencies (>4). Consider simplifying the dependency graph.")
        if not recs:
            recs.append("✅ Route health looks good! Consider running Monte Carlo simulation for deeper analysis.")
        return recs


@dataclass
class RouteHealthReport:
    """Health assessment of a route."""
    overall_score: float = 0.0
    grade: str = "F"
    metrics: dict = field(default_factory=dict)
    bottlenecks: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "grade": self.grade,
            "metrics": self.metrics,
            "bottlenecks": self.bottlenecks,
            "orphans": self.orphans,
            "recommendations": self.recommendations,
        }


# ---- Helpers ----

def _strip_markdown_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        lines = s.split("\n", 1)
        if len(lines) > 1:
            s = lines[1]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _repair_json(s: str) -> str:
    """Attempt to repair common JSON issues: unclosed braces, trailing commas, etc."""
    s = s.strip()
    # Count braces/brackets
    stack = []
    for ch in s:
        if ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    # Close unclosed structures
    while stack:
        ch = stack.pop()
        s += "}" if ch == "{" else "]"
    # Remove trailing commas before closing braces/brackets
    import re
    s = re.sub(r',\s*([}\]])', r'\1', s)
    return s


def _extract_partial(s: str) -> dict:
    """Extract whatever we can from a partially-formed JSON response."""
    result: dict = {}
    import re
    # Try to extract top-level string fields
    for key in ["goal", "summary", "reflection"]:
        m = re.search(rf'"{key}"\s*:\s*"([^"]*?)"', s)
        if m:
            result[key] = m.group(1)
    # Try to extract numeric fields
    for key in ["overall_success_probability", "total_duration_minutes"]:
        m = re.search(rf'"{key}"\s*:\s*([0-9.]+)', s)
        if m:
            result[key] = float(m.group(1))
    # Try to extract steps array (even partial)
    steps_match = re.search(r'"steps"\s*:\s*\[', s)
    if steps_match:
        # Find all step objects
        step_pattern = re.compile(r'\{[^{}]*"id"\s*:\s*"([^"]+)"[^{}]*\}', re.DOTALL)
        found_steps = []
        for m in step_pattern.finditer(s[steps_match.start():]):
            try:
                step_json = json.loads(m.group(0))
                found_steps.append(step_json)
            except json.JSONDecodeError:
                continue
        if found_steps:
            result["steps"] = found_steps
    if "edges" not in result:
        result["edges"] = []
    if "insights" not in result:
        result["insights"] = []
    if "steps" not in result:
        result["steps"] = []
    return result
