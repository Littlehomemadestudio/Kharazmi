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
from pathlib import Path
from typing import Callable, Optional, Any, Iterator


# ---- Configuration ----

API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.5-flash"
DEFAULT_API_KEY = "b795a49bd12348c8b9cc4a081c73374b.fmbP9oDfIWJ8zWiy"

SETTINGS_PATH = Path.home() / ".rask" / "ai_settings.json"


def load_ai_settings() -> dict:
    defaults = {
        "api_key": DEFAULT_API_KEY,
        "model": DEFAULT_MODEL,
        "base_url": API_URL,
        "temperature": 0.7,
        "max_tokens": 8192,
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
    # Step kind: "action" | "decision" | "milestone" | "wait" | "checkpoint"
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
        return cls(
            id=_clean(str(data.get("id", ""))),
            title=_clean(str(data.get("title", "Untitled step"))),
            duration_minutes=int(data.get("duration_minutes", 0)),
            success_probability=float(data.get("success_probability", 0.5)),
            location=_clean(str(data.get("location", ""))),
            description=_clean(str(data.get("description", ""))),
            fallback=_clean(str(data.get("fallback", ""))),
            depends_on=[_clean(str(x)) for x in data.get("depends_on", [])],
            sub_goals=[_clean(str(x)) for x in data.get("sub_goals", [])],
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
    """A floating insight box that appears around the route graph."""
    kind: str  # "improvement" | "alternative" | "breakthrough" | "question" | "warning"
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
            "Given the user's goal, decide whether it is clear enough to plan "
            "a route, or whether you need to ask clarifying questions first.\n\n"
            "Output STRICT JSON only (no markdown, no commentary) with this schema:\n"
            "{\n"
            "  \"is_clear\": boolean,\n"
            "  \"acknowledgment\": string,  // short sentence acknowledging the goal\n"
            "  \"questions\": [\n"
            "    {\n"
            "      \"question\": string,\n"
            "      \"options\": [string, string, string, string],  // EXACTLY 4 options\n"
            "      \"allow_custom\": true,\n"
            "      \"hint\": string\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- If the goal is clear (specific time, location, constraint), set "
            "is_clear=true and leave questions empty.\n"
            "- Otherwise, generate 2-4 multiple-choice questions.\n"
            "- Each question MUST have EXACTLY 4 options.\n"
            "- Options should cover the most common cases.\n"
            "- The user will be able to type a custom answer if none of the 4 fit.\n"
            "- Maximum 4 questions.\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User goal: {user_goal}"},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.3, response_format_json=True,
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
            "  - At least 2 branches (places where the path splits into parallel options)\n"
            "  - At least one 'alternative' edge (a different way to achieve a sub-goal)\n"
            "  - At least one 'fallback' edge (what to do if a step fails)\n"
            "  - A merge point where branches rejoin\n"
            "  - At least one 'decision' node and one 'checkpoint' node\n"
            "  - Between 8 and 12 steps total\n\n"
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
            "      \"sub_goals\": [string],\n"
            "      \"cost_estimate\": string,\n"
            "      \"risk_level\": string,\n"
            "      \"branch\": string,\n"
            "      \"kind\": string,\n"
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
            "1. Generate 8-12 steps. NOT a single linear chain — at least 2 branches.\n"
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
            "6. Generate 2-4 floating insights.\n"
            "7. Be efficient with tokens — keep descriptions concise but complete.\n"
            "8. Each step's 'depends_on' array MUST list the IDs of steps it depends on. "
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
                temperature=0.8, response_format_json=True,
                max_tokens=6144,
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
            "- Generate 2-5 new steps that branch off the existing route.\n"
            "- Connect them via 'alternative' or 'fallback' edges to existing steps.\n"
            "- Generate 2-4 new insights.\n"
            "- Make alternatives genuinely different (not minor variations).\n"
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
                max_tokens=8192,
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

    # ---- Schedule route in calendar ----
    def schedule_in_calendar_streaming(
        self, route: Route, start_datetime: str,
        on_status: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Break the route into bite-sized calendar events at the right times.

        Returns a list of event dicts:
          {title, start, end, location, description, calendar_name}
        """
        try:
            on_status("Scheduling route into your calendar…")
        except Exception:
            pass

        system_prompt = (
            "You are Rask. Convert the user's route into bite-sized calendar "
            "events starting at the given start time.\n\n"
            "Output STRICT JSON only:\n"
            "{\n"
            "  \"events\": [\n"
            "    {\n"
            "      \"title\": string,\n"
            "      \"start\": string,  // ISO 8601 datetime\n"
            "      \"end\": string,    // ISO 8601 datetime\n"
            "      \"location\": string,\n"
            "      \"description\": string,\n"
            "      \"calendar_name\": string  // \"Personal\" | \"Work\" | etc.\n"
            "    }\n"
            "  ],\n"
            "  \"summary\": string\n"
            "}\n\n"
            "Rules:\n"
            "- Create one event per step in the route's primary path.\n"
            "- Sequence events back-to-back, respecting duration_minutes.\n"
            "- Use the start time as the beginning of the first event.\n"
            "- Set the calendar_name based on the step's nature (work, personal, etc.).\n"
        )
        route_summary = (
            f"Route goal: {route.goal}\n"
            f"Start datetime: {start_datetime}\n"
            f"Steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            route_summary += (
                f"  [{s.id}] {s.title} — {s.duration_minutes}m, "
                f"location={s.location or 'n/a'}, branch={s.branch}\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": route_summary},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_status, request_id=request_id,
                temperature=0.3, response_format_json=True,
                max_tokens=4096,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
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
            "- Generate 3-7 specific, actionable optimizations.\n"
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
            "- Identify 4-8 specific risks.\n"
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
                max_tokens=6144,
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
