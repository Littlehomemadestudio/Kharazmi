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
import os
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RouteStep":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "Untitled step")),
            duration_minutes=int(data.get("duration_minutes", 0)),
            success_probability=float(data.get("success_probability", 0.5)),
            location=str(data.get("location", "")),
            description=str(data.get("description", "")),
            fallback=str(data.get("fallback", "")),
            depends_on=[str(x) for x in data.get("depends_on", [])],
            sub_goals=[str(x) for x in data.get("sub_goals", [])],
            cost_estimate=str(data.get("cost_estimate", "")),
            risk_level=str(data.get("risk_level", "low")),
            branch=str(data.get("branch", "main")),
            kind=str(data.get("kind", "action")),
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
            "      \"kind\": string\n"
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
            "2. List ALL edges explicitly in the 'edges' array.\n"
            "3. Use edge kinds: 'primary' (normal), 'alternative' (different option), 'fallback' (if step fails), 'merge' (branches rejoin).\n"
            "4. Titles and descriptions should be COMPLETE — never truncate.\n"
            "5. Generate 2-4 floating insights.\n"
            "6. Be efficient with tokens — keep descriptions concise but complete.\n"
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
            "Respond in plain text (not JSON) unless asked for structured output."}
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
