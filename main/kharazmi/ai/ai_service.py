"""
Rask AI service — connects to z.ai GLM-4.5-flash for natural-language
route planning with streaming responses.

Features:
  - Streaming chat (SSE chunks) for live "thinking" feedback
  - Clarifying questions with multiple-choice options (4 options + custom)
  - Route generation as a structured walkable graph
  - "Continue working" — after the route is built, AI proactively
    suggests alternatives, breakthroughs, and more questions

The AI uses your z.ai API key (stored in ~/.rask/ai_settings.json).
Free model: glm-4.5-flash.
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
    """Load AI settings from disk, falling back to defaults."""
    defaults = {
        "api_key": DEFAULT_API_KEY,
        "model": DEFAULT_MODEL,
        "base_url": API_URL,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            defaults.update(data)
    except Exception:
        pass
    return defaults


def save_ai_settings(settings: dict) -> None:
    """Persist AI settings."""
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
    """A single step in a route."""
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

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "duration_minutes": self.duration_minutes,
            "success_probability": self.success_probability,
            "location": self.location, "description": self.description,
            "fallback": self.fallback, "depends_on": list(self.depends_on),
            "sub_goals": list(self.sub_goals),
            "cost_estimate": self.cost_estimate, "risk_level": self.risk_level,
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
        )


@dataclass
class Insight:
    """A floating insight box that appears around the route graph."""
    kind: str  # "improvement" | "alternative" | "breakthrough" | "question" | "warning"
    title: str
    body: str
    # Optional anchor — if set, the insight floats near this step id
    anchor_step_id: Optional[str] = None
    # Position hint (relative units, 0..1) — used when no anchor
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
    """A clarifying question with 4 options + custom answer."""
    question: str
    options: list[str] = field(default_factory=list)
    allow_custom: bool = True
    # Optional helper text shown under the question
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "options": list(self.options),
            "allow_custom": self.allow_custom,
            "hint": self.hint,
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
    """A complete AI-generated route — a walkable graph of steps."""
    goal: str
    steps: list[RouteStep] = field(default_factory=list)
    overall_success_probability: float = 0.0
    total_duration_minutes: int = 0
    improvements: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    summary: str = ""
    clarifying_questions: list[str] = field(default_factory=list)
    raw_response: str = ""
    # New: structured insights (float around the graph as overlay boxes)
    insights: list[Insight] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
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
    """A single journal entry recording an AI interaction."""
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


# ---- AI service ----

class AIService:
    """
    Wraps calls to the z.ai GLM API with streaming support.

    All public methods run on a worker thread and invoke the callback
    on completion — this keeps the UI responsive. Streaming methods
    also accept an `on_chunk` callback that fires on each token.
    """

    def __init__(self) -> None:
        self.settings = load_ai_settings()
        self._cancel_flags: dict[str, bool] = {}  # request_id → cancel

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
                          else self.settings.get("max_tokens", 4096),
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
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}") from e

    # ---- Streaming API call ----
    def _call_api_streaming(self, messages: list[dict],
                             on_chunk: Callable[[str], None],
                             request_id: Optional[str] = None,
                             temperature: Optional[float] = None,
                             max_tokens: Optional[int] = None,
                             response_format_json: bool = False) -> str:
        """
        Stream a chat completion. Calls `on_chunk(text)` for each delta.

        Returns the full concatenated text.
        """
        payload = {
            "model": self.settings.get("model", DEFAULT_MODEL),
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": temperature if temperature is not None
                           else self.settings.get("temperature", 0.7),
            "max_tokens": max_tokens if max_tokens is not None
                          else self.settings.get("max_tokens", 4096),
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
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    # Check cancel
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

    # ---- Step 1: Generate clarifying questions (multiple-choice) ----
    def generate_clarifying_questions_streaming(
        self, user_goal: str,
        on_chunk: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Ask the AI for clarifying questions as multiple-choice.

        Each question has 4 options + allows custom answer.

        on_chunk is called with text deltas as the AI streams its response.
        callback is called with (success, result) when done.
        result is a dict:
          {
            "is_clear": bool,
            "acknowledgment": str,
            "questions": [MultipleChoiceQuestion, ...]
          }
        """
        system_prompt = (
            "You are Rask, an AI route-planning assistant. Your job is to "
            "help the user achieve a goal by breaking it down into a "
            "structured, walkable route of interconnected steps.\n\n"
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
            "      \"allow_custom\": true,  // always true\n"
            "      \"hint\": string  // optional helper text\n"
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
            "- Maximum 4 questions. Each question should be specific.\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User goal: {user_goal}"},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_chunk, request_id=request_id,
                temperature=0.3, response_format_json=True,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
            # Convert raw question dicts to MultipleChoiceQuestion objects
            raw_questions = parsed.get("questions", [])
            parsed["questions"] = [MultipleChoiceQuestion.from_dict(q) for q in raw_questions]
            return parsed

        self._run_async(_do, callback)

    # ---- Step 2: Generate the route (streaming) ----
    def generate_route_streaming(
        self, user_goal: str, clarifying_qa: list[tuple[str, str]],
        on_chunk: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        Generate a complete Route with streaming.

        on_chunk fires on each text delta (so the UI can show 'AI is thinking…').
        callback is called with (success, Route) when done.
        """
        system_prompt = (
            "You are Rask, an AI route-planning assistant. Given the user's "
            "goal and the answers to clarifying questions, you must produce "
            "a complete, walkable route of interconnected steps.\n\n"
            "Output STRICT JSON only (no markdown, no commentary) with this schema:\n"
            "{\n"
            "  \"goal\": string,\n"
            "  \"summary\": string,  // one-paragraph summary of the route\n"
            "  \"steps\": [\n"
            "    {\n"
            "      \"id\": string,  // short unique id like \"s1\", \"s2\"\n"
            "      \"title\": string,\n"
            "      \"description\": string,\n"
            "      \"duration_minutes\": integer,\n"
            "      \"success_probability\": float,  // 0..1\n"
            "      \"location\": string,\n"
            "      \"fallback\": string,\n"
            "      \"depends_on\": [string],\n"
            "      \"sub_goals\": [string],\n"
            "      \"cost_estimate\": string,\n"
            "      \"risk_level\": string  // \"low\" | \"medium\" | \"high\" | \"severe\"\n"
            "    }\n"
            "  ],\n"
            "  \"overall_success_probability\": float,\n"
            "  \"total_duration_minutes\": integer,\n"
            "  \"improvements\": [string],\n"
            "  \"follow_up_questions\": [string],\n"
            "  \"insights\": [\n"
            "    {\n"
            "      \"kind\": string,  // \"improvement\" | \"alternative\" | \"breakthrough\" | \"question\" | \"warning\"\n"
            "      \"title\": string,\n"
            "      \"body\": string,\n"
            "      \"anchor_step_id\": string | null,  // if set, floats near this step\n"
            "      \"x_hint\": float,  // 0..1, position on canvas if no anchor\n"
            "      \"y_hint\": float   // 0..1\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Generate between 5 and 15 steps.\n"
            "- Steps should be ordered logically; use depends_on for parallelism.\n"
            "- Each step should be concrete and actionable.\n"
            "- Include realistic time estimates (in minutes).\n"
            "- Success probabilities should be honest (0.3-0.95).\n"
            "- Include fallbacks for steps that might fail.\n"
            "- Use sub_goals for steps that have multiple parts.\n"
            "- The overall_success_probability should be computed from steps, not averaged.\n"
            "- total_duration_minutes should be the sum (or longest path if parallel).\n"
            "- improvements should be specific to THIS goal.\n"
            "- follow_up_questions should help the user reflect on the route.\n"
            "- Generate 3-6 insights that float around the route graph as "
            "overlay boxes. These should include at least: 1 alternative "
            "route suggestion, 1 breakthrough/creative idea, and 1-2 questions."
        )

        user_content = f"User goal: {user_goal}\n\n"
        if clarifying_qa:
            user_content += "Clarifying Q&A:\n"
            for q, a in clarifying_qa:
                user_content += f"  Q: {q}\n  A: {a}\n\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_chunk, request_id=request_id,
                temperature=0.7, response_format_json=True,
                max_tokens=8192,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
            route = Route.from_dict(parsed)
            route.raw_response = full
            return route

        self._run_async(_do, callback)

    # ---- Step 3: Continue working after route generation ----
    def continue_working_streaming(
        self, route: Route,
        on_chunk: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """
        After a route is generated, ask the AI to continue working:
          - Suggest alternative route options
          - Identify breakthroughs / creative ideas
          - Ask more questions for the user

        Returns a list of new Insight objects to add to the route.
        """
        system_prompt = (
            "You are Rask, an AI route-planning assistant. The user has "
            "already received a route. Now you should CONTINUE WORKING — "
            "proactively add more value.\n\n"
            "Generate additional insights that will float around the route "
            "graph as overlay boxes. Include:\n"
            "  - 2-3 ALTERNATIVE route options (different approaches)\n"
            "  - 1-2 BREAKTHROUGH ideas (creative, non-obvious suggestions)\n"
            "  - 1-2 more QUESTIONS for the user to consider\n"
            "  - Optional WARNINGS about things that could go wrong\n\n"
            "Output STRICT JSON only (no markdown, no commentary) with this schema:\n"
            "{\n"
            "  \"reflection\": string,  // 1-2 sentence reflection on the route\n"
            "  \"new_insights\": [\n"
            "    {\n"
            "      \"kind\": \"alternative\" | \"breakthrough\" | \"question\" | \"warning\",\n"
            "      \"title\": string,\n"
            "      \"body\": string,\n"
            "      \"anchor_step_id\": string | null,\n"
            "      \"x_hint\": float,\n"
            "      \"y_hint\": float\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Generate 4-8 new insights.\n"
            "- Make alternatives genuinely different (not minor variations).\n"
            "- Breakthroughs should be creative — things the user might not think of.\n"
            "- Questions should be specific and actionable.\n"
            "- Use anchor_step_id to attach an insight to a specific step when relevant.\n"
            "- Use x_hint/y_hint (0..1) to position unattached insights on the canvas.\n"
        )
        route_summary = (
            f"Goal: {route.goal}\n"
            f"Summary: {route.summary}\n"
            f"Steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            route_summary += f"  [{s.id}] {s.title} — {s.duration_minutes}m, {s.success_probability:.0%} success, risk={s.risk_level}\n"
            if s.depends_on:
                route_summary += f"    depends_on: {s.depends_on}\n"
            if s.fallback:
                route_summary += f"    fallback: {s.fallback}\n"
        route_summary += f"\nOverall success: {route.overall_success_probability:.0%}\n"
        route_summary += f"Total duration: {route.total_duration_minutes} min\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": route_summary},
        ]

        def _do():
            full = self._call_api_streaming(
                messages, on_chunk, request_id=request_id,
                temperature=0.9, response_format_json=True,
                max_tokens=4096,
            )
            full = _strip_markdown_fences(full)
            parsed = json.loads(full)
            new_insights = [Insight.from_dict(i) for i in parsed.get("new_insights", [])]
            return {
                "reflection": parsed.get("reflection", ""),
                "new_insights": new_insights,
            }

        self._run_async(_do, callback)

    # ---- Free-form chat (streaming) ----
    def chat_streaming(
        self, messages: list[dict],
        on_chunk: Callable[[str], None],
        callback: Callable[[bool, Any], None],
        request_id: Optional[str] = None,
    ) -> None:
        """Streaming chat — calls on_chunk with each text delta."""
        system = {"role": "system", "content":
            "You are Rask, an AI route-planning assistant. Be concise and helpful."}
        all_messages = [system] + messages

        def _do():
            full = self._call_api_streaming(
                all_messages, on_chunk, request_id=request_id,
                temperature=0.7,
            )
            return full

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
    """Remove ```json ... ``` wrappers if the model added them."""
    s = s.strip()
    if s.startswith("```"):
        lines = s.split("\n", 1)
        if len(lines) > 1:
            s = lines[1]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
