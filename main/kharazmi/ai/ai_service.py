"""
Rask AI service — connects to z.ai GLM-4.5-flash for natural-language
route planning.

The user describes a goal ("I want to be home by 9 o'clock, my car is
broken") and the AI:

  1. Asks clarifying questions if the goal is ambiguous
  2. Builds a structured "Route" — a walkable graph of interconnected
     steps with:
       - Duration estimates (minutes)
       - Success probability (0..1)
       - Location
       - Description
       - Fallback strategy
       - Dependencies (which steps must complete first)
       - Sub-goals (smaller milestones)
  3. Computes overall success probability
  4. Suggests improvements
  5. Lists follow-up questions
  6. Returns a journal entry summarising the whole exchange

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
from typing import Callable, Optional, Any


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
    risk_level: str = "low"  # low / medium / high / severe

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "duration_minutes": self.duration_minutes,
            "success_probability": self.success_probability,
            "location": self.location,
            "description": self.description,
            "fallback": self.fallback,
            "depends_on": list(self.depends_on),
            "sub_goals": list(self.sub_goals),
            "cost_estimate": self.cost_estimate,
            "risk_level": self.risk_level,
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
        )


# ---- Journal ----

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
            "id": self.id,
            "timestamp": self.timestamp,
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
    Wraps calls to the z.ai GLM API.

    All public methods run on a worker thread and invoke the callback
    on completion — this keeps the UI responsive.
    """

    def __init__(self) -> None:
        self.settings = load_ai_settings()

    def update_settings(self, **changes) -> None:
        self.settings.update(changes)
        save_ai_settings(self.settings)

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.get("api_key"))

    # ---- Low-level API call ----
    def _call_api(self, messages: list[dict],
                  temperature: Optional[float] = None,
                  max_tokens: Optional[int] = None,
                  response_format_json: bool = False) -> dict:
        """Make a synchronous call to the z.ai API. Returns the parsed JSON response."""
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
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}") from e

    # ---- Async wrappers ----
    def _run_async(self, fn: Callable[[], Any],
                   callback: Callable[[bool, Any], None]) -> None:
        """Run `fn` on a worker thread, then call `callback(success, result_or_error)`."""
        def _worker():
            try:
                result = fn()
                callback(True, result)
            except Exception as e:
                callback(False, e)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # ---- Step 1: Generate clarifying questions ----
    def generate_clarifying_questions(self, user_goal: str,
                                       callback: Callable[[bool, Any], None]) -> None:
        """
        Ask the AI to come up with 2-4 clarifying questions about the goal.

        If the goal is already clear, returns an empty list.
        """
        system_prompt = (
            "You are Rask, an AI route-planning assistant. "
            "Your job is to help the user achieve a goal by breaking it down "
            "into a structured, walkable route of interconnected steps.\n\n"
            "Given the user's goal, decide whether it is clear enough to plan "
            "a route, or whether you need to ask clarifying questions first.\n\n"
            "Output STRICT JSON only (no markdown, no commentary) with this schema:\n"
            "{\n"
            "  \"is_clear\": boolean,\n"
            "  \"clarifying_questions\": [\"question 1\", \"question 2\", ...],\n"
            "  \"acknowledgment\": string\n"
            "}\n\n"
            "Rules:\n"
            "- If the goal is clear (specific time, specific location, specific "
            "constraint), set is_clear=true and leave clarifying_questions empty.\n"
            "- Otherwise, set is_clear=false and list 2-4 specific yes/no or "
            "short-answer questions that would help you plan the route.\n"
            "- The acknowledgment should be a short sentence acknowledging the "
            "user's goal in plain language (e.g. 'Got it — you need to be home "
            "by 9pm and your car is broken. Let me ask a few questions first.').\n"
            "- Maximum 4 questions. Each question should be specific.\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User goal: {user_goal}"},
        ]

        def _do():
            data = self._call_api(messages, temperature=0.3,
                                  response_format_json=True)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            # Sometimes the model wraps JSON in markdown; strip it
            content = _strip_markdown_fences(content)
            return json.loads(content)

        self._run_async(_do, callback)

    # ---- Step 2: Generate the route ----
    def generate_route(self, user_goal: str, clarifying_qa: list[tuple[str, str]],
                       callback: Callable[[bool, Any], None]) -> None:
        """
        Generate a complete Route given the user's goal and the
        clarifying Q&A.

        `clarifying_qa` is a list of (question, answer) tuples.
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
            "      \"description\": string,  // what to do, why, how\n"
            "      \"duration_minutes\": integer,\n"
            "      \"success_probability\": float,  // 0..1\n"
            "      \"location\": string,  // where this happens\n"
            "      \"fallback\": string,  // what to do if this step fails\n"
            "      \"depends_on\": [string],  // ids of steps that must complete first\n"
            "      \"sub_goals\": [string],  // smaller milestones within this step\n"
            "      \"cost_estimate\": string,  // estimated cost in plain language\n"
            "      \"risk_level\": string  // \"low\" | \"medium\" | \"high\" | \"severe\"\n"
            "    }\n"
            "  ],\n"
            "  \"overall_success_probability\": float,  // 0..1\n"
            "  \"total_duration_minutes\": integer,\n"
            "  \"improvements\": [string],  // 3-5 actionable suggestions to improve success\n"
            "  \"follow_up_questions\": [string]  // 2-3 questions to ask after the route\n"
            "}\n\n"
            "Rules:\n"
            "- Generate between 5 and 15 steps.\n"
            "- Steps should be ordered logically; use depends_on to express parallelism.\n"
            "- Each step should be concrete and actionable — not abstract.\n"
            "- Include realistic time estimates (in minutes).\n"
            "- Success probabilities should be honest (0.3-0.95).\n"
            "- Include fallbacks for steps that might fail.\n"
            "- Use sub_goals for steps that have multiple parts.\n"
            "- The overall_success_probability should be computed from the steps' probabilities, not just averaged.\n"
            "- total_duration_minutes should be the sum of step durations (or longest path if parallel).\n"
            "- improvements should be specific to THIS goal.\n"
            "- follow_up_questions should help the user reflect on the route.\n"
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
            data = self._call_api(messages, temperature=0.7,
                                  response_format_json=True,
                                  max_tokens=8192)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            content = _strip_markdown_fences(content)
            parsed = json.loads(content)
            route = Route.from_dict(parsed)
            route.raw_response = content
            return route

        self._run_async(_do, callback)

    # ---- Step 3: Free-form chat (for follow-up questions) ----
    def chat(self, messages: list[dict],
             callback: Callable[[bool, Any], None]) -> None:
        """Generic chat — send a list of messages, get a string response."""
        system = {"role": "system", "content":
            "You are Rask, an AI route-planning assistant. Be concise and helpful."}
        all_messages = [system] + messages

        def _do():
            data = self._call_api(all_messages, temperature=0.7)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content

        self._run_async(_do, callback)

    # ---- Test the connection ----
    def test_connection(self, callback: Callable[[bool, Any], None]) -> None:
        """Send a tiny test request to verify the API key works."""
        def _do():
            data = self._call_api(
                [{"role": "user", "content": "Reply with the single word OK."}],
                temperature=0.0,
                max_tokens=10,
            )
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if "OK" in content.upper():
                return f"Connected successfully using model {self.settings.get('model')}."
            return f"Got unexpected response: {content!r}"
        self._run_async(_do, callback)


# ---- Helpers ----

def _strip_markdown_fences(s: str) -> str:
    """Remove ```json ... ``` wrappers if the model added them despite instructions."""
    s = s.strip()
    if s.startswith("```"):
        # Remove first line (```json or ```)
        lines = s.split("\n", 1)
        if len(lines) > 1:
            s = lines[1]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
