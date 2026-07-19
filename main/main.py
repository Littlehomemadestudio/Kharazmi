"""
Premium Planner UI with AI Assistant - Complete Integration
Features: Month, Week, Day Views, Task CRUD, Animations, 4 Visual Themes, and Offline AI Brain
Author: LittleFoxes (Enhanced with AI Integration)
"""

import customtkinter as ctk  # type: ignore
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime, timedelta # type: ignore
from typing import Callable, Optional, List, Dict, Any
import calendar # type: ignore
import threading # type: ignore
import json # type: ignore  
import re # type: ignore
import os # type: ignore
from pathlib import Path # type: ignore
from gpt4all import GPT4All  # pip install gpt4all # type: ignore
import requests
import queue
import subprocess
import time
import sys
import webbrowser
import os   

# Register custom Persian font
def load_custom_font():
    try:
        font_path = os.path.join(os.path.dirname(__file__), "Gulzar", "Gulzar-Regular.ttf")
        if os.path.exists(font_path):
            tkfont.Font(family="Gulzar", size=10)
            print(f"Custom font loaded: {font_path}")
            return True
    except Exception as e:
        print(f"Could not load custom font: {e}")
    return False

# --- THEME DEFINITIONS --- 
THEMES = {
    "Midnight Dev": {  # GitHub Dark inspired
        'mode': 'Dark',
        'bg_primary': '#0D1117',
        'bg_secondary': '#161B22',
        'bg_hover': '#21262D',
        'accent_primary': '#58A6FF',
        'accent_secondary': '#8957E5',
        'accent_tertiary': '#FF7B72',
        'text_primary': '#C9D1D9',
        'text_secondary': '#8B949E',
        'text_tertiary': '#484F58',
        'border': '#30363D',
        'success': '#3FB950',
        'warning': '#D29922',
        'error': '#F85149',
        'today': '#22272E',
        'selected': '#1F6FEB',
        'task_dot': '#8957E5',
        'transparent': '#0D1117',
    },
    "Seraph": {  # Claude AI inspired (Warm/Earthy)
        'mode': 'Dark',
        'bg_primary': '#252422',
        'bg_secondary': '#302F2D',
        'bg_hover': '#3F3E3C',
        'accent_primary': '#D97757',   # Terracotta
        'accent_secondary': '#D4C5A9', # Beige
        'accent_tertiary': '#C26D5F',
        'text_primary': '#F4F0E8',
        'text_secondary': '#A5A198',
        'text_tertiary': '#5E5C58', 
        'border': '#454340',
        'success': '#7D9C86',
        'warning': '#D4A66A',
        'error': '#C26D5F',
        'today': '#383633',
        'selected': '#D97757',
        'task_dot': '#D4C5A9',
        'transparent': '#252422',
    },
    "Nebula": {  # ChatGPT inspired (Slate/Teal)
        'mode': 'Dark',
        'bg_primary': '#343541',
        'bg_secondary': '#444654',
        'bg_hover': '#555767',
        'accent_primary': '#10A37F',   # Teal
        'accent_secondary': '#707285',
        'accent_tertiary': '#EF4444',
        'text_primary': '#ECECF1',
        'text_secondary': '#C5C5D2',
        'text_tertiary': '#565869',
        'border': '#565869',
        'success': '#10A37F',
        'warning': '#F59E0B',
        'error': '#EF4444',
        'today': '#40414F',
        'selected': '#10A37F',
        'task_dot': '#10A37F',
        'transparent': '#343541',
    },
    "Daylight": {  # Original Light Theme
        'mode': 'Light',
        'bg_primary': '#FAFBFC',
        'bg_secondary': '#FFFFFF',
        'bg_hover': '#F5F7FA',
        'accent_primary': '#6366F1',
        'accent_secondary': '#8B5CF6',
        'accent_tertiary': '#EC4899',
        'text_primary': '#1F2937',
        'text_secondary': '#6B7280',
        'text_tertiary': '#9CA3AF',
        'border': '#E5E7EB',
        'success': '#10B981',
        'warning': '#F59E0B',
        'error': '#EF4444',
        'today': '#EEF2FF',
        'selected': '#6366F1',
        'task_dot': '#8B5CF6',
        'transparent': '#FAFBFC',
    }
}


class AIAssistant:
    """
    AI Assistant using Ollama API with enhanced features from royal_hafozaligh
    Handles task generation and personalized scheduling
    
    IMPROVED AI TASK EXTRACTION:
    - Fully autonomous AI decision-making for task classification
    - Enhanced prompts that give AI complete authority to choose categories, priorities, and classifications
    - Multiple JSON extraction strategies for better accuracy
    - Retry mechanism with improved prompts
    - Context-aware extraction with user preferences
    - Increased context window (4096) and token limit (1500) for complex analysis
    - Advanced validation and normalization of AI-extracted tasks
    - No fallback to hardcoded parsing - AI works solo
    """
    
    def __init__(self):
        self.model = None
        self.is_loaded = False 
        self.loading = False
        self.ollama_model = "gemma3:4b"
        self.ollama_url = "http://localhost:11434/api/generate"
        self.system_prompt = "You are a helpful AI advisor. Respond concisely and thoughtfully."
        
    def _check_ollama_running(self) -> bool:
        """Check if Ollama is already running"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _start_ollama(self) -> bool:
        try:
            # Since Ollama is already working, try to start it using the system command
            subprocess.run(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False  # Don't raise exception if already running
            )
            return True
        except Exception as e:
            print(f"Error starting Ollama: {e}")
            return False


                    
            
        
    def load_model(self, callback: Callable[[bool, str], None]):
        """Check if Ollama is available, start it if not running"""
        if self.is_loaded or self.loading:
            callback(True, "Model already loaded")
            return
            
        self.loading = True
        
        def _load():
            try:
                # First, check if Ollama is already running
                if self._check_ollama_running():
                    self.is_loaded = True
                    self.loading = False
                    callback(True, "Ollama connected successfully")
                    return
                
                # If not running, try to start it
                callback(False, "🔄 Ollama not running. Attempting to start it...")
                if self._start_ollama():
                    # Wait for Ollama to start (up to 10 seconds)
                    max_attempts = 20
                    for attempt in range(max_attempts):
                        time.sleep(0.5)  # Wait 0.5 seconds between attempts
                        if self._check_ollama_running():
                            self.is_loaded = True
                            self.loading = False
                            callback(True, "✅ Ollama started and connected successfully!")
                            return
                    
                    self.loading = False
                    callback(False, "Ollama started but not responding. Please check if it's installed correctly.")
                else:
                    self.loading = False
                    callback(False, "❌ Could not start Ollama automatically. Please start it manually or ensure it's installed.")
                    
            except Exception as e:
                self.loading = False
                callback(False, f"Error connecting to Ollama: {str(e)}")
        
        thread = threading.Thread(target=_load, daemon=True)
        thread.start()
    
    def extract_tasks_with_ai(self, user_input: str, callback: Callable[[bool, any], None]):
        """Extract tasks from user input using AI - fully autonomous AI-driven extraction"""
        if not self.is_loaded:
            callback(False, "Model not loaded")
            return
        
        def _extract():
            try:
                # Enhanced prompt that gives AI full autonomy and decision-making power
                prompt = f"""You are an expert task extraction and analysis AI. Your role is to autonomously analyze user input and extract ALL tasks with complete decision-making authority.

USER INPUT: "{user_input}"

YOUR AUTONOMOUS ANALYSIS PROCESS:
1. Carefully read and understand the entire user input
2. Identify ALL tasks, activities, or actions mentioned (even if implicit or combined)
3. For each task, YOU decide and determine:
   - title: A clear, concise, actionable task name (you choose the best phrasing)
   - difficulty: 1-10 scale (YOU assess based on task complexity, requirements, and your judgment)
   - energy: 1-10 scale (YOU determine mental/physical energy needed based on task nature)
   - ideal_time: morning/afternoon/evening (YOU choose based on task characteristics and best practices)
   - category: YOU classify as academic, creative, errand, chore, social, communication, domestic, professional, analytical, or other (you decide)
   - priority: YOU assign as high, medium, or low based on urgency and importance (you assess)
   - estimated_duration: YOU estimate in minutes based on task complexity (you decide)

IMPORTANT AUTONOMOUS DECISIONS YOU MAKE:
- Split combined tasks intelligently (e.g., "study math and physics" = 2 tasks)
- Detect implicit tasks (e.g., "need groceries" = "buy groceries")
- Determine task relationships and dependencies if present
- Assess context clues for better classification
- Choose appropriate difficulty/energy based on YOUR understanding of the task
- Select ideal_time based on task type and YOUR knowledge of productivity patterns

EXTRACTION RULES:
- Be thorough: extract every task mentioned, even if casually phrased
- Be intelligent: understand context and intent, not just keywords
- Be precise: create clear, actionable task titles
- Be autonomous: use your judgment for all classifications

OUTPUT FORMAT - Return ONLY valid JSON array, no explanations, no markdown, no code blocks:
[
    {{"title": "Task name you choose", "difficulty": YOUR_ASSESSMENT, "energy": YOUR_ASSESSMENT, "ideal_time": "YOUR_CHOICE", "category": "YOUR_CLASSIFICATION", "priority": "YOUR_ASSESSMENT", "estimated_duration": YOUR_ESTIMATE}},
    ...
]

EXAMPLES OF YOUR AUTONOMOUS DECISIONS:
Input: "study math physics make a cake"
Your extraction:
[
    {{"title": "Study mathematics", "difficulty": 7, "energy": 8, "ideal_time": "morning", "category": "academic", "priority": "high", "estimated_duration": 120}},
    {{"title": "Study physics", "difficulty": 7, "energy": 8, "ideal_time": "morning", "category": "academic", "priority": "high", "estimated_duration": 120}},
    {{"title": "Make a cake", "difficulty": 4, "energy": 5, "ideal_time": "afternoon", "category": "domestic", "priority": "medium", "estimated_duration": 90}}
]

Input: "I need to finish my report and call mom"
Your extraction:
[
    {{"title": "Finish report", "difficulty": 6, "energy": 7, "ideal_time": "morning", "category": "professional", "priority": "high", "estimated_duration": 180}},
    {{"title": "Call mom", "difficulty": 2, "energy": 3, "ideal_time": "afternoon", "category": "communication", "priority": "medium", "estimated_duration": 30}}
]

NOW ANALYZE AND EXTRACT FROM: "{user_input}"
Remember: You have full autonomy. Use your intelligence to make the best decisions.
"""

                # First attempt with optimized settings
                tasks = self._ai_extract_with_retry(prompt, max_retries=3)
                
                if tasks:
                    callback(True, tasks)
                else:
                    # If all retries fail, try with a simpler, more direct prompt
                    simple_prompt = f"""Extract tasks from: "{user_input}"

Return JSON array only:
[{{"title": "task", "difficulty": 1-10, "energy": 1-10, "ideal_time": "morning/afternoon/evening", "category": "type", "priority": "high/medium/low", "estimated_duration": minutes}}]"""
                    
                    tasks = self._ai_extract_with_retry(simple_prompt, max_retries=2, temperature=0.1)
                    
                    if tasks:
                        callback(True, tasks)
                    else:
                        # Last resort: minimal fallback with AI guidance
                        callback(False, "AI extraction failed after multiple attempts")
                    
            except Exception as e:
                callback(False, f"Error during AI extraction: {str(e)}")
        
        thread = threading.Thread(target=_extract, daemon=True)
        thread.start()
    
    def _ai_extract_with_retry(self, prompt: str, max_retries: int = 3, temperature: float = 0.2) -> Optional[List[Dict]]:
        """Extract tasks using AI with retry mechanism and improved JSON parsing"""
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_ctx": 4096,  # Increased context for better understanding
                            "temperature": temperature,
                            "num_predict": 1500,  # More tokens for complex extractions
                            "top_p": 0.9,
                            "top_k": 40,
                            "repeat_penalty": 1.1
                        }
                    },
                    timeout=30  # Increased timeout for complex analysis
                )

                data = response.json()
                if "response" not in data:
                    continue
                
                ai_response = data["response"].strip()
                
                # Multiple JSON extraction strategies - let AI work through them
                tasks = self._extract_json_from_response(ai_response)
                
                if tasks and isinstance(tasks, list) and len(tasks) > 0:
                    # Validate and normalize task structure
                    validated_tasks = self._validate_and_normalize_tasks(tasks)
                    if validated_tasks:
                        return validated_tasks
                
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"AI extraction attempt {attempt + 1} failed: {e}")
                continue
        
        return None
    
    def _extract_json_from_response(self, response: str) -> Optional[List[Dict]]:
        """Extract JSON from AI response using multiple strategies"""
        # Strategy 1: Direct JSON array match
        json_match = re.search(r'\[[\s\S]*?\]', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Strategy 2: Find JSON between code blocks
        code_block_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', response, re.DOTALL | re.IGNORECASE)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Strategy 3: Find JSON after common prefixes
        prefixes = ['tasks:', 'result:', 'output:', 'json:']
        for prefix in prefixes:
            pattern = rf'{re.escape(prefix)}\s*(\[[\s\S]*?\])'
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        
        # Strategy 4: Try to fix common JSON issues and retry
        # Remove markdown formatting
        cleaned = re.sub(r'```[a-z]*\s*', '', response, flags=re.IGNORECASE)
        cleaned = re.sub(r'```', '', cleaned)
        
        # Try to find and fix unquoted keys
        json_match = re.search(r'\{[\s\S]*?\}', cleaned)
        if json_match:
            try:
                # Try to fix common issues
                fixed_json = json_match.group(0)
                fixed_json = re.sub(r'(\w+):', r'"\1":', fixed_json)  # Quote unquoted keys
                return json.loads(f'[{fixed_json}]')
            except:
                pass
        
        # Strategy 5: Extract array content and reconstruct
        array_content = re.search(r'\[([\s\S]*)\]', response)
        if array_content:
            content = array_content.group(1)
            # Try to extract individual objects
            objects = re.findall(r'\{[^{}]*\}', content)
            if objects:
                tasks = []
                for obj_str in objects:
                    try:
                        # Fix common issues
                        obj_str = re.sub(r'(\w+):', r'"\1":', obj_str)
                        task = json.loads(obj_str)
                        tasks.append(task)
                    except:
                        continue
                if tasks:
                    return tasks
        
        return None
    
    def _validate_and_normalize_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """Validate and normalize AI-extracted tasks"""
        validated = []
        
        for task in tasks:
            if not isinstance(task, dict):
                continue
            
            # Ensure required fields with AI-provided or sensible defaults
            normalized_task = {
                'title': str(task.get('title', 'Untitled Task')).strip()[:100],
                'difficulty': self._clamp_value(task.get('difficulty', 5), 1, 10),
                'energy': self._clamp_value(task.get('energy', 5), 1, 10),
                'ideal_time': self._normalize_time(task.get('ideal_time', 'afternoon')),
            }
            
            # Add optional fields if AI provided them
            if 'category' in task:
                normalized_task['category'] = str(task['category']).lower()
            if 'priority' in task:
                normalized_task['priority'] = str(task['priority']).lower()
            if 'estimated_duration' in task:
                normalized_task['estimated_duration'] = max(5, int(task.get('estimated_duration', 60)))
            
            # Only add if title is meaningful
            if len(normalized_task['title']) >= 3:
                validated.append(normalized_task)
        
        return validated
    
    def _clamp_value(self, value: any, min_val: int, max_val: int) -> int:
        """Clamp a value to a range"""
        try:
            val = int(float(value))
            return max(min_val, min(max_val, val))
        except:
            return (min_val + max_val) // 2
    
    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to morning/afternoon/evening"""
        time_lower = str(time_str).lower()
        if 'morn' in time_lower or 'early' in time_lower:
            return 'morning'
        elif 'even' in time_lower or 'night' in time_lower or 'late' in time_lower:
            return 'evening'
        else:
            return 'afternoon'
    
    def generate_tasks(self, user_input: str, callback: Callable[[bool, any], None]):
        """Legacy method - redirects to extract_tasks_with_ai"""
        self.extract_tasks_with_ai(user_input, callback)
    
    def extract_tasks_with_ai_autonomous(self, user_input: str, context: Optional[Dict] = None, callback: Callable[[bool, any], None] = None):
        """Fully autonomous AI task extraction with context awareness and self-improvement"""
        if not self.is_loaded:
            if callback:
                callback(False, "Model not loaded")
            return
        
        def _extract_autonomous():
            try:
                # Build context-aware prompt
                context_str = ""
                if context:
                    context_parts = []
                    if 'previous_tasks' in context:
                        context_parts.append(f"Previous tasks: {json.dumps(context['previous_tasks'])}")
                    if 'user_preferences' in context:
                        context_parts.append(f"User preferences: {json.dumps(context['user_preferences'])}")
                    if 'time_constraints' in context:
                        context_parts.append(f"Time constraints: {context['time_constraints']}")
                    context_str = "\n".join(context_parts)
                
                prompt = f"""You are an advanced, fully autonomous task extraction AI with complete decision-making authority. You analyze user input intelligently and make all decisions yourself.

CONTEXT INFORMATION:
{context_str if context_str else "No additional context provided."}

USER INPUT: "{user_input}"

YOUR FULLY AUTONOMOUS PROCESS:
1. Deep Analysis: Understand the complete meaning, context, and intent behind the user's words
2. Intelligent Extraction: Identify ALL tasks, including:
   - Explicitly mentioned tasks
   - Implicit tasks (e.g., "need groceries" → "buy groceries")
   - Combined tasks (split intelligently)
   - Tasks with dependencies or sequences
3. Autonomous Classification: For EACH task, YOU decide:
   - title: Best phrasing for clarity and actionability (your choice)
   - difficulty: 1-10 (your assessment based on complexity, skills needed, time investment)
   - energy: 1-10 (your assessment of mental/physical energy required)
   - ideal_time: morning/afternoon/evening (your choice based on task nature and productivity science)
   - category: academic/creative/errand/chore/social/communication/domestic/professional/analytical/health/fitness/entertainment/other (you classify)
   - priority: high/medium/low (your assessment of urgency and importance)
   - estimated_duration: minutes (your estimate based on typical completion time)
   - requires_focus: true/false (you decide if task needs deep focus)
   - can_interrupt: true/false (you decide if task can be paused/interrupted)

YOUR DECISION-MAKING AUTHORITY:
- You have complete autonomy to interpret, classify, and structure tasks
- Use your knowledge of productivity, psychology, and task management
- Make intelligent inferences from context and implicit information
- Choose the most appropriate values based on YOUR understanding
- Split or combine tasks as YOU see fit for optimal task management

OUTPUT: Return ONLY a valid JSON array. No explanations, no markdown, no code blocks, just pure JSON.

FORMAT:
[
    {{
        "title": "Your chosen task name",
        "difficulty": YOUR_ASSESSMENT_1_TO_10,
        "energy": YOUR_ASSESSMENT_1_TO_10,
        "ideal_time": "YOUR_CHOICE_morning/afternoon/evening",
        "category": "YOUR_CLASSIFICATION",
        "priority": "YOUR_ASSESSMENT_high/medium/low",
        "estimated_duration": YOUR_ESTIMATE_IN_MINUTES,
        "requires_focus": YOUR_DECISION_true/false,
        "can_interrupt": YOUR_DECISION_true/false
    }}
]

EXAMPLES OF YOUR AUTONOMOUS DECISIONS:

Input: "I have a big exam tomorrow so I need to study calculus and review my notes, also should probably get some sleep"
Your extraction:
[
    {{
        "title": "Study calculus for exam",
        "difficulty": 8,
        "energy": 9,
        "ideal_time": "morning",
        "category": "academic",
        "priority": "high",
        "estimated_duration": 180,
        "requires_focus": true,
        "can_interrupt": false
    }},
    {{
        "title": "Review study notes",
        "difficulty": 5,
        "energy": 6,
        "ideal_time": "afternoon",
        "category": "academic",
        "priority": "high",
        "estimated_duration": 60,
        "requires_focus": true,
        "can_interrupt": true
    }},
    {{
        "title": "Get adequate sleep",
        "difficulty": 2,
        "energy": 1,
        "ideal_time": "evening",
        "category": "health",
        "priority": "high",
        "estimated_duration": 480,
        "requires_focus": false,
        "can_interrupt": false
    }}
]

NOW ANALYZE: "{user_input}"
Use your full intelligence and autonomy to extract and classify all tasks.
"""

                # Use enhanced extraction with retry
                tasks = self._ai_extract_with_retry(prompt, max_retries=3, temperature=0.25)
                
                if tasks:
                    if callback:
                        callback(True, tasks)
                    return tasks
                else:
                    if callback:
                        callback(False, "AI extraction failed - unable to extract tasks")
                    return None
                    
            except Exception as e:
                if callback:
                    callback(False, f"Error: {str(e)}")
                return None
        
        thread = threading.Thread(target=_chat, daemon=True)
        thread.start()
    
    def _simple_reorder(self, tasks: List[Dict], persona: str) -> List[Dict]:
        """Simple task reordering based on keywords"""
        persona_lower = persona.lower()
        
        if 'morning' in persona_lower:
            return sorted(tasks, key=lambda x: (x.get('ideal_time') != 'morning', x.get('difficulty', 5)))
        elif 'tired' in persona_lower or 'exhausted' in persona_lower:
            return sorted(tasks, key=lambda x: (x.get('energy', 5), x.get('difficulty', 5)))
        else:
            return sorted(tasks, key=lambda x: -x.get('difficulty', 5))
        return None
    
    def generate_personalized_questions(self, context: str, already_asked: List[str], callback: Callable[[bool, str], None]):
        """Generate personalized questions using AI based on context"""
        if not self.is_loaded:
            callback(False, "Model not loaded")
            return
        
        def _generate():
            try:
                asked_str = ", ".join(already_asked) if already_asked else "none"
                
                prompt = f"""You are a helpful AI assistant creating a personalized task schedule. Based on the conversation context, generate ONE relevant personal question to help customize the user's schedule.

Context: {context}
Already asked: {asked_str}

Generate ONE natural, conversational question about:
- Sleep patterns (night owl vs morning person)
- Energy levels throughout the day
- Fixed time commitments (classes, work, meetings)
- Work style preferences
- Break preferences
- Any other relevant scheduling preferences

Make it feel natural and conversational, not robotic. Return ONLY the question, no explanation.

Example good questions:
- "Are you more of a night owl or an early bird?"
- "When during the day do you feel most focused and energetic?"
- "Do you have any fixed commitments I should work around, like classes or work hours?"
- "What's your ideal work style - do you prefer tackling difficult tasks in the morning or afternoon?"

Generate your question:"""

                response = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_ctx": 2048,
                            "temperature": 0.7,
                            "num_predict": 150
                        }
                    },
                    timeout=15
                )

                data = response.json()
                if "response" not in data:
                    callback(False, "Could not generate question")
                    return
                
                question = data["response"].strip()
                # Clean up the question (remove quotes if present)
                question = question.strip('"\'')
                callback(True, question)
                    
            except Exception as e:
                callback(False, f"Error: {str(e)}")
        
        thread = threading.Thread(target=_generate, daemon=True)
        thread.start()
    
    def create_personalized_schedule(self, tasks: List[Dict], personal_info: Dict, callback: Callable[[bool, any], None]):
        """Create a fully personalized schedule using AI with all collected information"""
        if not self.is_loaded:
            callback(False, "Model not loaded")
            return
        
        def _create():
            try:
                # Build comprehensive persona description
                persona_parts = []
                if 'sleep_preference' in personal_info:
                    persona_parts.append(f"Sleep preference: {personal_info['sleep_preference']}")
                if 'energy_levels' in personal_info:
                    persona_parts.append(f"Peak energy time: {personal_info['energy_levels']}")
                if 'time_blocks' in personal_info and personal_info['time_blocks'].lower() not in ['none', 'no', 'n/a']:
                    persona_parts.append(f"Fixed time commitments: {personal_info['time_blocks']}")
                if 'work_style' in personal_info:
                    persona_parts.append(f"Work style: {personal_info['work_style']}")
                if 'break_preferences' in personal_info:
                    persona_parts.append(f"Break preferences: {personal_info['break_preferences']}")
                
                persona = "; ".join(persona_parts) if persona_parts else "No specific preferences provided"
                
                prompt = f"""You are an expert scheduling assistant. Create an optimized, personalized schedule for the user based on their tasks and preferences.

Tasks to schedule:
{json.dumps(tasks, indent=2)}

User's personal preferences and constraints:
{persona}

Create an optimized schedule that:
1. Respects their sleep preferences and energy levels
2. Avoids their fixed time commitments
3. Matches their work style
4. Includes appropriate breaks
5. Schedules difficult tasks during peak energy times
6. Ensures tasks don't overlap with fixed commitments

Return ONLY a JSON array with the same tasks, but with updated ideal_time values that reflect the optimal scheduling based on their preferences. Also add a "scheduled_time" field with the actual time slot (e.g., "9:00 AM - 11:00 AM").

Example format:
[
    {{"title": "Study mathematics", "difficulty": 7, "energy": 8, "ideal_time": "morning", "scheduled_time": "9:00 AM - 11:00 AM"}},
    {{"title": "Make a cake", "difficulty": 4, "energy": 5, "ideal_time": "afternoon", "scheduled_time": "2:00 PM - 4:00 PM"}}
]

Generate the optimized schedule:"""

                response = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_ctx": 2048,
                            "temperature": 0.5,
                            "num_predict": 1000
                        }
                    },
                    timeout=20
                )

                data = response.json()
                if "response" not in data:
                    callback(True, self._simple_reorder(tasks, persona))
                    return
                
                ai_response = data["response"].strip()
                
                json_match = re.search(r'\[[\s\S]*\]', ai_response)
                if json_match:
                    try:
                        optimized_tasks = json.loads(json_match.group(0))
                        callback(True, optimized_tasks)
                    except json.JSONDecodeError:
                        callback(True, self._simple_reorder(tasks, persona))
                else:
                    callback(True, self._simple_reorder(tasks, persona))
                    
            except Exception as e:
                callback(True, self._simple_reorder(tasks, persona))
        
        thread = threading.Thread(target=_create, daemon=True)
        thread.start()
    
    def personalize_schedule(self, tasks: List[Dict], persona: str, callback: Callable[[bool, any], None]):
        """Reorder tasks based on user's personality/energy state using Ollama"""
        if not self.is_loaded:
            callback(False, "Model not loaded")
            return
        
        def _personalize():
            try:
                prompt = f"""You are a scheduling assistant. Given these tasks and the user's current state, reorder them optimally.

Tasks: {json.dumps(tasks)}
User state: "{persona}"

Consider: energy levels, time preferences, and difficulty.
Return ONLY a JSON array with tasks in optimal order:"""

                response = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_ctx": 2048,
                            "temperature": 0.5,
                            "num_predict": 600
                        }
                    },
                    timeout=15
                )

                data = response.json()
                if "response" not in data:
                    callback(True, self._simple_reorder(tasks, persona))
                    return
                
                ai_response = data["response"].strip()
                
                json_match = re.search(r'\[[\s\S]*\]', ai_response)
                if json_match:
                    reordered = json.loads(json_match.group(0))
                    callback(True, reordered)
                else:
                    # Simple fallback reordering
                    callback(True, self._simple_reorder(tasks, persona))
                    
            except Exception as e:
                callback(True, self._simple_reorder(tasks, persona))
        
        thread = threading.Thread(target=_personalize, daemon=True)
        thread.start()
    
    def determine_intent(self, user_input: str) -> Dict[str, Any]:
        """Determine user intent - planning or conversation"""
        input_lower = user_input.lower()
        
        # Planning-related intents
        planning_keywords = ['task', 'todo', 'plan', 'schedule', 'remind', 'add', 'create', 'need to', 'want to', 'study', 'make', 'do', 'read', 'write', 'buy', 'cook', 'bake']
        if any(word in input_lower for word in planning_keywords):
            return {'intent': 'planning', 'confidence': 0.8}
        
        # Question intents
        question_indicators = ['?', 'are you', 'do you', 'can you', 'will you', 'what', 'how', 'why', 'when', 'where', 'who']
        if any(indicator in input_lower for indicator in question_indicators):
            return {'intent': 'conversation', 'confidence': 0.9}
        
        # Default to conversation
        return {'intent': 'conversation', 'confidence': 0.5}
    
    def chat_response(self, user_input: str, conversation_history: List[Dict] = None, callback: Callable[[bool, str], None] = None):
        """Get general chat response from AI with context awareness"""
        if not self.is_loaded:
            if callback:
                callback(False, "Model not loaded")
            return
        
        def _chat():
            try:
                # Build context from conversation history
                context = ""
                if conversation_history:
                    context = "\n".join([
                        f"{msg.get('role', 'user')}: {msg.get('content', '')}" 
                        for msg in conversation_history[-5:]  # Last 5 messages
                    ])
                
                # Enhanced system prompt for contextual responses
                system_prompt = """You are a helpful AI assistant that can both help with task planning and have natural conversations. 
Be contextual, empathetic, and appropriate in your responses. Don't use generic responses like "great" for everything.
If the user says "no" to a question, acknowledge their answer appropriately, don't just say "great"."""
                
                prompt = f"""{system_prompt}

{context if context else ""}

User: {user_input}
Assistant:"""
                
                response = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_ctx": 2048,
                            "temperature": 0.7,  # Higher for more varied responses
                            "num_predict": 200
                        }
                    },
                    timeout=15
                )

                data = response.json()
                if "response" not in data:
                    if callback:
                        callback(False, "Response format error")
                    return None
                
                response_text = data["response"].strip()
                if callback:
                    callback(True, response_text)
                return response_text
                
            except requests.exceptions.Timeout:
                if callback:
                    callback(False, "Response timeout")
                return None
            except requests.exceptions.ConnectionError:
                if callback:
                    callback(False, "Connection failed")
                return None
            except Exception as e:
                if callback:
                    callback(False, f"Error: {str(e)}")
                return None
        
        thread = threading.Thread(target=_chat, daemon=True)
        thread.start()
    
    def _simple_reorder(self, tasks: List[Dict], persona: str) -> List[Dict]:
        """Simple task reordering based on keywords"""
        persona_lower = persona.lower()
        
        if 'morning' in persona_lower:
            return sorted(tasks, key=lambda x: (x.get('ideal_time') != 'morning', x.get('difficulty', 5)))
        elif 'tired' in persona_lower or 'exhausted' in persona_lower:
            return sorted(tasks, key=lambda x: (x.get('energy', 5), x.get('difficulty', 5)))
        else:
            return sorted(tasks, key=lambda x: -x.get('difficulty', 5))


class TaskDetectionSystem:
    """
    Task Detection System with Hardcoded Rules
    Asks general questions, detects tasks, creates final reader/maker configuration
    Based on the AI Planner structure
    """
    
    def __init__(self):
        # Hardcoded question templates
        self.general_questions = [
            "What would you like to accomplish today?",
            "What tasks do you need to complete?",
            "What are your main goals for this period?",
            "What activities do you have planned?",
            "Are there any deadlines or priorities to consider?"
        ]
        
        # Hardcoded task detection patterns
        self.task_separators = [
            r'\band\b',
            r'\bthen\b',
            r'\bafter\b',
            r'\bnext\b',
            r',',
            r';',
            r'\band then\b',
        ]
        
        # Hardcoded action verbs for task detection
        self.action_verbs = [
            'study', 'make', 'do', 'read', 'write', 'create', 'build', 
            'learn', 'practice', 'cook', 'bake', 'work', 'complete',
            'finish', 'start', 'prepare', 'organize', 'clean', 'fix',
            'buy', 'shop', 'attend', 'meet', 'call', 'email', 'send',
            'analyze', 'review', 'update', 'modify', 'delete', 'remove'
        ]
        
        # Hardcoded task classification rules
        self.task_classification = {
            'study': {'difficulty': 7, 'energy': 8, 'ideal_time': 'morning', 'category': 'academic'},
            'learn': {'difficulty': 7, 'energy': 8, 'ideal_time': 'morning', 'category': 'academic'},
            'read': {'difficulty': 5, 'energy': 6, 'ideal_time': 'morning', 'category': 'academic'},
            'write': {'difficulty': 6, 'energy': 7, 'ideal_time': 'morning', 'category': 'academic'},
            'create': {'difficulty': 6, 'energy': 7, 'ideal_time': 'morning', 'category': 'creative'},
            'build': {'difficulty': 7, 'energy': 8, 'ideal_time': 'morning', 'category': 'creative'},
            'buy': {'difficulty': 3, 'energy': 4, 'ideal_time': 'afternoon', 'category': 'errand'},
            'shop': {'difficulty': 3, 'energy': 4, 'ideal_time': 'afternoon', 'category': 'errand'},
            'grocery': {'difficulty': 3, 'energy': 4, 'ideal_time': 'afternoon', 'category': 'errand'},
            'clean': {'difficulty': 4, 'energy': 5, 'ideal_time': 'afternoon', 'category': 'chore'},
            'organize': {'difficulty': 4, 'energy': 5, 'ideal_time': 'afternoon', 'category': 'chore'},
            'meeting': {'difficulty': 5, 'energy': 6, 'ideal_time': 'morning', 'category': 'social'},
            'call': {'difficulty': 4, 'energy': 5, 'ideal_time': 'morning', 'category': 'social'},
            'email': {'difficulty': 4, 'energy': 5, 'ideal_time': 'morning', 'category': 'communication'},
            'attend': {'difficulty': 5, 'energy': 6, 'ideal_time': 'morning', 'category': 'social'},
            'cook': {'difficulty': 4, 'energy': 5, 'ideal_time': 'evening', 'category': 'domestic'},
            'bake': {'difficulty': 5, 'energy': 6, 'ideal_time': 'evening', 'category': 'domestic'},
            'make': {'difficulty': 4, 'energy': 5, 'ideal_time': 'afternoon', 'category': 'creative'},
            'work': {'difficulty': 6, 'energy': 7, 'ideal_time': 'morning', 'category': 'professional'},
            'complete': {'difficulty': 6, 'energy': 7, 'ideal_time': 'morning', 'category': 'professional'},
            'analyze': {'difficulty': 7, 'energy': 8, 'ideal_time': 'morning', 'category': 'analytical'},
            'review': {'difficulty': 5, 'energy': 6, 'ideal_time': 'afternoon', 'category': 'analytical'},
        }
        
        # Hardcoded maker configurations
        self.maker_configs = {
            'academic': {
                'action': 'read_study',
                'priority': 'high',
                'duration_estimate': 120,  # minutes
                'requires_focus': True
            },
            'creative': {
                'action': 'create_build',
                'priority': 'medium',
                'duration_estimate': 90,
                'requires_focus': True
            },
            'errand': {
                'action': 'execute_errand',
                'priority': 'low',
                'duration_estimate': 60,
                'requires_focus': False
            },
            'chore': {
                'action': 'complete_chore',
                'priority': 'low',
                'duration_estimate': 45,
                'requires_focus': False
            },
            'social': {
                'action': 'attend_meeting',
                'priority': 'medium',
                'duration_estimate': 60,
                'requires_focus': True
            },
            'communication': {
                'action': 'send_message',
                'priority': 'medium',
                'duration_estimate': 30,
                'requires_focus': False
            },
            'domestic': {
                'action': 'prepare_food',
                'priority': 'medium',
                'duration_estimate': 90,
                'requires_focus': False
            },
            'professional': {
                'action': 'work_task',
                'priority': 'high',
                'duration_estimate': 120,
                'requires_focus': True
            },
            'analytical': {
                'action': 'analyze_data',
                'priority': 'high',
                'duration_estimate': 150,
                'requires_focus': True
            },
            'default': {
                'action': 'generic_task',
                'priority': 'medium',
                'duration_estimate': 60,
                'requires_focus': False
            }
        }
        
        # Hardcoded processing rules
        self.processing_rules = {
            'max_tasks_per_batch': 10,
            'min_task_length': 3,
            'max_task_length': 100,
            'default_difficulty': 5,
            'default_energy': 5,
            'default_ideal_time': 'afternoon',
            'confidence_threshold': 0.6
        }
    
    def ask_general_questions(self) -> List[str]:
        """Returns hardcoded general questions"""
        return self.general_questions.copy()
    
    def ask_contextual_question(self, context: str) -> str:
        """Asks contextual question based on detected context - hardcoded rules"""
        context_lower = context.lower()
        
        if any(word in context_lower for word in ['study', 'learn', 'read', 'homework']):
            return "What subjects or topics do you need to focus on?"
        elif any(word in context_lower for word in ['work', 'project', 'meeting', 'deadline']):
            return "What are your work priorities or deadlines?"
        elif any(word in context_lower for word in ['buy', 'shop', 'grocery', 'errand']):
            return "What items or places do you need to visit?"
        elif any(word in context_lower for word in ['cook', 'bake', 'make', 'prepare']):
            return "What would you like to prepare or create?"
        else:
            return "Can you provide more details about your tasks?"
    
    def detect_tasks(self, user_input: str) -> List[Dict]:
        """Detect tasks from user input using hardcoded patterns"""
        # Split by separators first
        potential_tasks = [user_input]
        for sep in self.task_separators:
            new_tasks = []
            for task in potential_tasks:
                parts = re.split(sep, task, flags=re.IGNORECASE)
                new_tasks.extend([p.strip() for p in parts if p.strip()])
            potential_tasks = new_tasks
        
        # If no separators found, try to detect multiple activities by action verbs
        if len(potential_tasks) == 1:
            words = potential_tasks[0].split()
            if len(words) >= 4:
                split_points = []
                for i, word in enumerate(words):
                    word_lower = word.lower().rstrip('.,!?')
                    if word_lower in self.action_verbs and i > 0:
                        prev_word = words[i-1].lower().rstrip('.,!?')
                        if prev_word not in ['to', 'the', 'a', 'an', 'for']:
                            split_points.append(i)
                
                if len(split_points) > 0:
                    new_tasks = []
                    start = 0
                    for point in split_points:
                        task_text = ' '.join(words[start:point]).strip()
                        if task_text:
                            new_tasks.append(task_text)
                        start = point
                    last_task = ' '.join(words[start:]).strip()
                    if last_task:
                        new_tasks.append(last_task)
                    potential_tasks = new_tasks
        
        # Clean and create task objects with hardcoded classification
        tasks = []
        for task_text in potential_tasks:
            task_text = task_text.strip()
            task_text = re.sub(r'^(also|then|and|next|after|please|can you|will you|i need to|i want to)\s+', '', task_text, flags=re.IGNORECASE)
            task_text = task_text.rstrip('.,!?')
            
            if len(task_text) > self.processing_rules['min_task_length']:
                task_lower = task_text.lower()
                
                # Find matching classification
                classification = self.processing_rules['default_ideal_time']
                difficulty = self.processing_rules['default_difficulty']
                energy = self.processing_rules['default_energy']
                category = 'default'
                
                for keyword, config in self.task_classification.items():
                    if keyword in task_lower:
                        difficulty = config['difficulty']
                        energy = config['energy']
                        classification = config['ideal_time']
                        category = config['category']
                        break
                
                tasks.append({
                    'title': task_text[:self.processing_rules['max_task_length']],
                    'difficulty': difficulty,
                    'energy': energy,
                    'ideal_time': classification,
                    'category': category
                })
        
        # If still no tasks, create one from the whole input
        if not tasks:
            tasks.append({
                'title': user_input[:self.processing_rules['max_task_length']],
                'difficulty': self.processing_rules['default_difficulty'],
                'energy': self.processing_rules['default_energy'],
                'ideal_time': self.processing_rules['default_ideal_time'],
                'category': 'default'
            })
        
        return tasks[:self.processing_rules['max_tasks_per_batch']]
    
    def create_reader(self, task: Dict) -> Dict:
        """Create a reader configuration for a task - hardcoded mapping"""
        category = task.get('category', 'default')
        config = self.maker_configs.get(category, self.maker_configs['default'])
        
        return {
            'task_id': f"task_{hash(task['title']) % 10000}",
            'title': task['title'],
            'task_type': category,
            'action': config['action'],
            'priority': config['priority'],
            'difficulty': task.get('difficulty', 5),
            'energy': task.get('energy', 5),
            'ideal_time': task.get('ideal_time', 'afternoon'),
            'duration_estimate': config['duration_estimate'],
            'requires_focus': config['requires_focus'],
            'confidence': self._calculate_confidence(task)
        }
    
    def create_maker(self, tasks: List[Dict]) -> Dict:
        """Create final maker configuration with hardcoded processing"""
        if not tasks:
            return {
                'status': 'no_tasks_detected',
                'questions': self.ask_general_questions()
            }
        
        # Create reader configs for all tasks
        reader_configs = [self.create_reader(task) for task in tasks]
        
        # Hardcoded prioritization
        sorted_tasks = sorted(reader_configs, key=lambda x: (
            x['priority'] == 'high',
            -x['difficulty'],
            x['ideal_time'] == 'morning'
        ), reverse=True)
        
        return {
            'status': 'success',
            'total_tasks': len(tasks),
            'primary_task': sorted_tasks[0] if sorted_tasks else None,
            'all_tasks': sorted_tasks,
            'processing_rules': self.processing_rules,
            'maker_configs': self.maker_configs,
            'recommended_schedule': self._generate_schedule(sorted_tasks)
        }
    
    def _calculate_confidence(self, task: Dict) -> float:
        """Calculate confidence score for detected task - hardcoded rules"""
        base_confidence = 0.7
        
        # Increase confidence if task has clear action verb
        task_lower = task['title'].lower()
        matching_verbs = sum(1 for verb in self.action_verbs if verb in task_lower)
        confidence = base_confidence + (matching_verbs * 0.1)
        
        # Increase if category is not default
        if task.get('category') != 'default':
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _generate_schedule(self, tasks: List[Dict]) -> List[Dict]:
        """Generate recommended schedule - hardcoded scheduling logic"""
        schedule = []
        time_slots = {
            'morning': {'start': '9:00 AM', 'end': '12:00 PM'},
            'afternoon': {'start': '1:00 PM', 'end': '5:00 PM'},
            'evening': {'start': '6:00 PM', 'end': '9:00 PM'}
        }
        
        # Group tasks by ideal_time
        by_time = {'morning': [], 'afternoon': [], 'evening': []}
        for task in tasks:
            ideal = task.get('ideal_time', 'afternoon')
            if ideal in by_time:
                by_time[ideal].append(task)
        
        # Create schedule entries
        current_time = {'morning': 0, 'afternoon': 0, 'evening': 0}
        for time_period, task_list in by_time.items():
            slot = time_slots[time_period]
            for task in task_list:
                duration = task.get('duration_estimate', 60)
                start_minutes = current_time[time_period]
                start_hour = 9 if time_period == 'morning' else (13 if time_period == 'afternoon' else 18)
                start_time = f"{start_hour + (start_minutes // 60)}:{(start_minutes % 60):02d} {'AM' if time_period == 'morning' else 'PM'}"
                end_minutes = start_minutes + duration
                end_time = f"{start_hour + (end_minutes // 60)}:{(end_minutes % 60):02d} {'AM' if time_period == 'morning' else 'PM'}"
                
                schedule.append({
                    'task': task['title'],
                    'time_period': time_period,
                    'scheduled_time': f"{start_time} - {end_time}",
                    'duration': duration
                })
                current_time[time_period] = end_minutes
        
        return schedule
    
    def process(self, user_input: Optional[str] = None) -> Dict:
        """Main processing pipeline: ask questions -> detect tasks -> create maker"""
        # Step 1: Ask general questions
        questions = self.ask_general_questions()
        
        # Step 2: Detect tasks (if user input provided)
        tasks = []
        if user_input:
            tasks = self.detect_tasks(user_input)
        
        # Step 3: Create final maker
        maker_config = self.create_maker(tasks) if tasks else {}
        
        # Step 4: Apply hardcoded processing
        if maker_config and 'status' in maker_config and maker_config['status'] == 'success':
            final_result = maker_config
            final_result['hardcoded_processing'] = True
            final_result['questions_asked'] = questions
        else:
            final_result = {
                'status': 'awaiting_input',
                'questions': questions,
                'contextual_question': self.ask_contextual_question(user_input) if user_input else None
            }
        
        return final_result
    
    def chat_response(self, user_input: str, conversation_history: List[Dict] = None, callback: Callable[[bool, str], None] = None):
        """Get general chat response from AI with context awareness"""
        if not self.is_loaded:
            if callback:
                callback(False, "Model not loaded")
            return
        
        def _chat():
            try:
                # Build context from conversation history
                context = ""
                if conversation_history:
                    context = "\n".join([
                        f"{msg.get('role', 'user')}: {msg.get('content', '')}" 
                        for msg in conversation_history[-5:]  # Last 5 messages
                    ])
                
                # Enhanced system prompt for contextual responses
                system_prompt = """You are a helpful AI assistant that can both help with task planning and have natural conversations. 
Be contextual, empathetic, and appropriate in your responses. Don't use generic responses like "great" for everything.
If the user says "no" to a question, acknowledge their answer appropriately, don't just say "great"."""
                
                prompt = f"""{system_prompt}

{context if context else ""}

User: {user_input}
Assistant:"""
                
                response = requests.post(
                    self.ollama_url,
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_ctx": 2048,
                            "temperature": 0.7,  # Higher for more varied responses
                            "num_predict": 200
                        }
                    },
                    timeout=15
                )

                data = response.json()
                if "response" not in data:
                    if callback:
                        callback(False, "Response format error")
                    return None
                
                response_text = data["response"].strip()
                if callback:
                    callback(True, response_text)
                return response_text
                
            except requests.exceptions.Timeout:
                if callback:
                    callback(False, "Response timeout")
                return None
            except requests.exceptions.ConnectionError:
                if callback:
                    callback(False, "Connection failed")
                return None
            except Exception as e:
                if callback:
                    callback(False, f"Error: {str(e)}")
                return None
        
        thread = threading.Thread(target=_chat, daemon=True)
        thread.start()
    
    def _fallback_parse(self, user_input: str) -> List[Dict]:
        """Intelligent fallback task extraction - handles multiple tasks"""
        # Common task separators
        separators = [
            r'\band\b',
            r'\bthen\b',
            r'\bafter\b',
            r'\bnext\b',
            r',',
            r';',
            r'\band then\b',
        ]
        
        # Split by separators first
        potential_tasks = [user_input]
        for sep in separators:
            new_tasks = []
            for task in potential_tasks:
                parts = re.split(sep, task, flags=re.IGNORECASE)
                new_tasks.extend([p.strip() for p in parts if p.strip()])
            potential_tasks = new_tasks
        
        # If no separators found, try to detect multiple activities by action verbs
        if len(potential_tasks) == 1:
            words = potential_tasks[0].split()
            if len(words) >= 4:
                # Action verbs that typically start new tasks
                action_verbs = [
                    'study', 'make', 'do', 'read', 'write', 'create', 'build', 
                    'learn', 'practice', 'cook', 'bake', 'work', 'complete',
                    'finish', 'start', 'prepare', 'organize', 'clean', 'fix',
                    'buy', 'shop', 'attend', 'meet', 'call', 'email', 'send'
                ]
                
                # Find split points (action verbs that aren't at the start)
                split_points = []
                for i, word in enumerate(words):
                    word_lower = word.lower().rstrip('.,!?')
                    if word_lower in action_verbs and i > 0:
                        # Check if previous word could be end of a task
                        prev_word = words[i-1].lower().rstrip('.,!?')
                        if prev_word not in ['to', 'the', 'a', 'an', 'for']:
                            split_points.append(i)
                
                # Split at action verbs
                if len(split_points) > 0:
                    new_tasks = []
                    start = 0
                    for point in split_points:
                        task_text = ' '.join(words[start:point]).strip()
                        if task_text:
                            new_tasks.append(task_text)
                        start = point
                    # Add the last task
                    last_task = ' '.join(words[start:]).strip()
                    if last_task:
                        new_tasks.append(last_task)
                    potential_tasks = new_tasks
        
        # Clean and create task objects
        tasks = []
        for task_text in potential_tasks:
            task_text = task_text.strip()
            # Remove common filler words at start
            task_text = re.sub(r'^(also|then|and|next|after|please|can you|will you|i need to|i want to)\s+', '', task_text, flags=re.IGNORECASE)
            task_text = task_text.rstrip('.,!?')
            
            # Only add if it's substantial
            if len(task_text) > 3:
                # Determine difficulty and energy based on keywords
                task_lower = task_text.lower()
                difficulty = 5
                energy = 5
                ideal_time = 'afternoon'
                
                if any(word in task_lower for word in ['study', 'learn', 'read', 'write', 'create', 'build']):
                    difficulty = 7
                    energy = 8
                    ideal_time = 'morning'
                elif any(word in task_lower for word in ['buy', 'shop', 'grocery', 'clean', 'organize']):
                    difficulty = 3
                    energy = 4
                    ideal_time = 'afternoon'
                elif any(word in task_lower for word in ['meeting', 'call', 'email', 'attend']):
                    difficulty = 5
                    energy = 6
                    ideal_time = 'morning'
                elif any(word in task_lower for word in ['cook', 'bake', 'make']):
                    difficulty = 4
                    energy = 5
                    ideal_time = 'evening'
                
            tasks.append({
                    'title': task_text[:50],
                    'difficulty': difficulty,
                    'energy': energy,
                    'ideal_time': ideal_time
                })
        
        # If still no tasks, create one from the whole input
        if not tasks:
            tasks.append({
                'title': user_input[:50],
                'difficulty': 5,
                'energy': 5,
                'ideal_time': 'afternoon'
            })
        
        return tasks
    
    def _simple_reorder(self, tasks: List[Dict], persona: str) -> List[Dict]:
        """Simple task reordering based on keywords"""
        persona_lower = persona.lower()
        
        if 'morning' in persona_lower:
            return sorted(tasks, key=lambda x: (x.get('ideal_time') != 'morning', x.get('difficulty', 5)))
        elif 'tired' in persona_lower or 'exhausted' in persona_lower:
            return sorted(tasks, key=lambda x: (x.get('energy', 5), x.get('difficulty', 5)))
        else:
            return sorted(tasks, key=lambda x: -x.get('difficulty', 5))

class PlannerUI:
    """
    Premium Planner Application UI with AI Assistant
    A modern, beautifully designed interface for task management
    """
    
    def __init__(
        self,
        root: ctk.CTk,
        on_day_select: Optional[Callable] = None,
        on_add_task: Optional[Callable] = None,
        on_edit_task: Optional[Callable] = None,
        on_delete_task: Optional[Callable] = None,
        on_ai_schedule: Optional[Callable] = None,
        on_task_toggle: Optional[Callable] = None
    ):
        self.root = root
        
        # Load custom Persian font
        load_custom_font()
        
        # Callbacks
        self.on_day_select = on_day_select or (lambda date: None)
        self.on_add_task = on_add_task or (lambda: None)
        self.on_edit_task = on_edit_task or (lambda task: None)
        self.on_delete_task = on_delete_task or (lambda task: None)
        self.on_ai_schedule = on_ai_schedule or (lambda: None)
        self.on_task_toggle = on_task_toggle or (lambda task: None)
        
        # State
        self.current_date = datetime.now().replace(day=1)
        self.selected_date = datetime.now()
        self.tasks_by_date: Dict[str, List[Dict]] = {}
        self.day_buttons = {}
        self.task_cards = []
        self.selected_task = None
        self.main_container = None 
        
        # View State
        self.current_view = "Month"
        self.view_container = None 
        self.week_header_frame = None
        self.week_time_grid = None
        self.day_header_frame = None
        self.day_time_grid = None
        self.cal_grid_container = None
        self.view_buttons = {}
        
        # AI Assistant State
        self.ai_assistant = AIAssistant()
        self.ai_window = None
        self.ai_window_visible = False
        self.ai_chat_display = None
        self.ai_input = None
        self.ai_conversation_history = []  # Store conversation history for context
        self.ai_collecting_info = False  # Flag to track if we're collecting personal info
        self.ai_personal_info = {}  # Store collected personal information
        self.ai_pending_tasks = []  # Store tasks while collecting info
        
        # Settings State
        self.settings_panel = None
        self.settings_panel_visible = False
        self.settings = {
            'notifications_enabled': True,
            'notification_sound': True,
            'auto_save': True,
            'save_interval': 30,  # seconds
            'startup_view': 'Month',
            'default_duration': '1 hour',
            'reminder_before': 15,  # minutes
            'theme': 'Midnight Dev',
            'compact_mode': False,
            'show_completed_tasks': True
        }
        
        # Save/Load paths
        self.data_dir = Path.home() / '.planner_app'
        self.data_dir.mkdir(exist_ok=True)
        self.tasks_file = self.data_dir / 'tasks.json'
        self.settings_file = self.data_dir / 'settings.json'
        
        # Load saved data first (before applying theme)
        self._load_settings()
        self._load_tasks()
        
        # Initialize Theme (use saved theme if available)
        self.current_theme_key = self.settings.get('theme', "Midnight Dev")
        if self.current_theme_key not in THEMES:
            self.current_theme_key = "Midnight Dev"
        self.colors = THEMES[self.current_theme_key]
        
        # Apply startup view
        if 'startup_view' in self.settings:
            self.current_view = self.settings['startup_view']
        
        # Configure CustomTkinter default
        ctk.set_default_color_theme("blue")
        self._apply_theme_settings()
        
        # Setup UI
        self._setup_window()
        self._create_layout()
        
        # Start auto-save
        if self.settings.get('auto_save', True):
            interval = self.settings.get('save_interval', 30) * 1000
            self.root.after(interval, self._auto_save_tasks)
        
    def _apply_theme_settings(self):
        """Apply the global appearance mode based on current theme"""
        ctk.set_appearance_mode(self.colors['mode'])
        if self.main_container:
            self.main_container.configure(fg_color=self.colors['bg_primary'])
        self.root.configure(fg_color=self.colors['bg_primary'])

    def _change_theme(self, new_theme_name):
        """Callback to switch theme and rebuild UI"""
        if new_theme_name in THEMES:
            view_to_restore = self.current_view
            
            self.current_theme_key = new_theme_name
            self.colors = THEMES[new_theme_name]
            self._apply_theme_settings()
            
            if self.main_container:
                self.main_container.destroy()
            
            self.day_buttons = {}
            self.task_cards = []
            self.selected_task = None
            
            self._create_layout()
            
            self.current_view = view_to_restore
            self._change_view(self.current_view) 
            self._update_header()
            self._refresh_tasks()
            
            # Recreate AI window if it was visible
            if self.ai_window_visible:
                self.ai_window_visible = False
                self._toggle_ai_window()

    def _setup_window(self):
        """Configure main window properties"""
        self.root.title("برنامه‌ریز - مدیریت وظایف با هوش مصنوعی")
        self.root.geometry("1400x900")
        self.root.configure(fg_color=self.colors['bg_primary'])
        
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
    def _create_layout(self):
        """Create the main application layout"""
        self.main_container = ctk.CTkFrame(
            self.root,
            fg_color=self.colors['bg_primary'],
            corner_radius=0
        )
        self.main_container.pack(fill='both', expand=True, padx=30, pady=30)
        
        self._create_header(self.main_container)
        
        content_frame = ctk.CTkFrame(
            self.main_container,
            fg_color='transparent'
        )
        content_frame.pack(fill='both', expand=True, pady=(20, 0))
        
        self.view_container = ctk.CTkFrame(
            content_frame,
            fg_color=self.colors['bg_secondary'],
            corner_radius=20,
            border_width=1,
            border_color=self.colors['border']
        )
        self.view_container.pack(side='left', fill='both', expand=True, padx=(0, 15))
        
        self._create_tasks_panel(content_frame)
        
        self._create_action_bar(self.main_container)
        
        self._change_view(self.current_view)
        
    def _create_header(self, parent):
        """Create elegant header with date display"""
        header_frame = ctk.CTkFrame(parent, fg_color='transparent', height=80)
        header_frame.pack(fill='x', pady=(0, 10))
        header_frame.pack_propagate(False)
        
        date_str = self.selected_date.strftime("%A, %B %d, %Y")
        self.header_label = ctk.CTkLabel(
            header_frame, text=date_str,
            font=ctk.CTkFont(family="Gulzar", size=36, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        )
        self.header_label.pack(side='left', fill='x', expand=True)
        
        tagline = ctk.CTkLabel(
            header_frame, text="روز خود را با ظرافت سازماندهی کنید",
            font=ctk.CTkFont(family="Gulzar", size=14),
            text_color=self.colors['text_tertiary'], anchor='w'
        )
        tagline.pack(side='left', padx=(20, 0))
        
    def _create_tasks_panel(self, parent):
        """Create elegant tasks panel"""
        tasks_container = ctk.CTkFrame(
            parent, fg_color=self.colors['bg_secondary'], corner_radius=20,
            border_width=1, border_color=self.colors['border'], width=500
        )
        tasks_container.pack(side='right', fill='both', expand=True)
        tasks_container.pack_propagate(False)
        
        tasks_header = ctk.CTkFrame(tasks_container, fg_color='transparent', height=70)
        tasks_header.pack(fill='x', padx=25, pady=(25, 15))
        tasks_header.pack_propagate(False)
        
        tasks_title = ctk.CTkLabel(
            tasks_header, text="وظایف",
            font=ctk.CTkFont(family="Gulzar", size=22, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        )
        tasks_title.pack(side='left', fill='x', expand=True)
        
        self.task_count_label = ctk.CTkLabel(
            tasks_header, text="0",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            text_color='#FFFFFF', fg_color=self.colors['accent_primary'],
            corner_radius=12, width=50, height=30
        )
        self.task_count_label.pack(side='right')
        
        self.tasks_scroll = ctk.CTkScrollableFrame(
            tasks_container, fg_color='transparent',
            scrollbar_button_color=self.colors['border'],
            scrollbar_button_hover_color=self.colors['text_tertiary']
        )
        self.tasks_scroll.pack(fill='both', expand=True, padx=25, pady=(0, 25))
        
    def _create_action_bar(self, parent):
        """Create bottom action bar with premium buttons and AI assistant"""
        action_frame = ctk.CTkFrame(parent, fg_color='transparent', height=70)
        action_frame.pack(fill='x', pady=(20, 0))
        action_frame.pack_propagate(False)
        
        left_buttons = ctk.CTkFrame(action_frame, fg_color='transparent')
        left_buttons.pack(side='left', fill='y')
        
        add_btn = self._create_primary_button(left_buttons, "＋  افزودن وظیفه", self.on_add_task)
        add_btn.pack(side='left', padx=(0, 10))
        
        self.edit_btn = self._create_secondary_button(left_buttons, "✎  ویرایش", self._handle_edit_task)
        self.edit_btn.pack(side='left', padx=(0, 10))
        self.edit_btn.configure(state='disabled')
        
        self.delete_btn = self._create_secondary_button(
            left_buttons, "🗑  حذف", self._handle_delete_task,
            fg_color=self.colors['error'], hover_color=self.colors['accent_tertiary'], text_color='#FFFFFF'
        )
        self.delete_btn.pack(side='left')
        self.delete_btn.configure(state='disabled')
        
        right_frame = ctk.CTkFrame(action_frame, fg_color='transparent')
        right_frame.pack(side='right', fill='y')

        view_button_frame = ctk.CTkFrame(right_frame, fg_color=self.colors['bg_hover'], corner_radius=14)
        view_button_frame.pack(side='left', padx=(0, 15), pady=12)
        
        view_map = {"Month": "ماه", "Week": "هفته", "Day": "روز"}
        for view in ["Month", "Week", "Day"]:
            btn = ctk.CTkButton(
                view_button_frame,
                text=view_map[view],
                command=lambda v=view: self._change_view(v),
                font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
                corner_radius=12,
                height=35,
                width=80
            )
            btn.pack(side='left', padx=3, pady=3)
            self.view_buttons[view] = btn

        theme_var = ctk.StringVar(value=self.current_theme_key)
        theme_switch = ctk.CTkOptionMenu(
            right_frame, values=list(THEMES.keys()), command=self._change_theme,
            variable=theme_var, width=140, fg_color=self.colors['bg_secondary'],
            text_color=self.colors['text_primary'], button_color=self.colors['bg_hover'],
            button_hover_color=self.colors['border'], dropdown_fg_color=self.colors['bg_secondary'],
            dropdown_text_color=self.colors['text_primary'], dropdown_hover_color=self.colors['bg_hover']
        )
        theme_switch.pack(side='left', padx=(0, 15), pady=12)

        ai_btn = self._create_ai_button(right_frame, "🤖  دستیار هوشمند", self._toggle_ai_window)
        ai_btn.pack(side='left', padx=(0, 10))
        
        game_btn = self._create_ai_button(right_frame, "🎮  بازی MK48", self._launch_mk48_game)
        game_btn.pack(side='left', padx=(0, 10))
        
        settings_btn = ctk.CTkButton(
            right_frame, text="⚙️ تنظیمات", width=140, height=50,
            font=ctk.CTkFont(family="Gulzar", size=15, weight="bold"),
            fg_color=self.colors['bg_secondary'],
            hover_color=self.colors['bg_hover'],
            text_color=self.colors['text_primary'],
            corner_radius=14,
            border_width=1,
            border_color=self.colors['border'],
            command=self._toggle_settings_panel
        )
        settings_btn.pack(side='left', padx=(0, 0))
        
        self._update_view_selector_style()

    def _update_view_selector_style(self):
        """Highlights the currently active view button."""
        for view, btn in self.view_buttons.items():
            if view == self.current_view:
                btn.configure(
                    fg_color=self.colors['accent_primary'],
                    text_color='#FFFFFF',
                    hover_color=self.colors['accent_secondary']
                )
            else:
                btn.configure(
                    fg_color=self.colors['bg_hover'],
                    text_color=self.colors['text_primary'],
                    hover_color=self.colors['border']
                )

    def _change_view(self, view_name):
        """Switches between Month, Week, and Day views."""
        self.current_view = view_name
        self._update_view_selector_style()
        
        for widget in self.view_container.winfo_children():
            widget.destroy()
        
        if view_name == "Month":
            self._create_month_view(self.view_container)
        elif view_name == "Week":
            self._create_week_view(self.view_container)
        elif view_name == "Day":
            self._create_day_view(self.view_container)
        
        self._refresh_tasks()
        
    # --- AI Assistant Panel ---
    
    def _toggle_ai_window(self):
        """Toggle the AI assistant window"""
        if self.ai_window_visible:
            self._hide_ai_window()
        else:
            self._show_ai_window()
    
    def _show_ai_window(self):
        """Show the AI assistant as a separate window"""
        if self.ai_window:
            self.ai_window.destroy()
        
        # Create new window
        self.ai_window = ctk.CTkToplevel(self.root)
        self.ai_window.title("🤖 دستیار هوشمند")
        self.ai_window.geometry("700x600")
        self.ai_window.configure(fg_color=self.colors['bg_primary'])
        
        # Make window resizable
        self.ai_window.resizable(True, True)
        self.ai_window.minsize(500, 400)
        
        # Center the window
        self.ai_window.update_idletasks()
        x = (self.ai_window.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.ai_window.winfo_screenheight() // 2) - (600 // 2)
        self.ai_window.geometry(f"700x600+{x}+{y}")
        
        self.ai_window_visible = True
        
        # Create window content
        self._create_ai_window_content()
        
        # Load AI model if not loaded
        if not self.ai_assistant.is_loaded and not self.ai_assistant.loading:
            self._add_ai_message("🔄 در حال اتصال به مدل هوش مصنوعی...\n\n"
                               "⏳ لطفاً مطمئن شوید که Ollama در localhost:11434 در حال اجرا است", "system")
            self.ai_assistant.load_model(self._on_model_loaded)
        else:
            welcome_msg = "👋 سلام! اینجا هستم تا به شما در برنامه‌ریزی وظایف کمک کنم یا فقط صحبت کنیم. چه کاری می‌خواهید انجام دهید؟"
            self._add_ai_message(welcome_msg, "assistant")
            self.ai_conversation_history.append({'role': 'assistant', 'content': welcome_msg})
        
        # Handle window close
        self.ai_window.protocol("WM_DELETE_WINDOW", self._hide_ai_window)
    
    def _hide_ai_window(self):
        """Hide the AI assistant window"""
        if self.ai_window:
            self.ai_window.destroy()
            self.ai_window = None
        self.ai_window_visible = False
    
    def _create_ai_window_content(self):
        """Create the content for AI assistant window"""
        # Header
        header = ctk.CTkFrame(self.ai_window, fg_color='transparent', height=80)
        header.pack(fill='x', padx=20, pady=(20, 10))
        header.pack_propagate(False)
        
        ctk.CTkLabel(
            header, text="🤖 دستیار هوشمند",
            font=ctk.CTkFont(family="Gulzar", size=24, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(side='left')
        
        close_btn = ctk.CTkButton(
            header, text="✕", width=40, height=40,
            font=ctk.CTkFont(size=20),
            fg_color='transparent',
            hover_color=self.colors['error'],
            text_color=self.colors['text_secondary'],
            command=self._hide_ai_window
        )
        close_btn.pack(side='right')
        
        # Chat display
        self.ai_chat_display = ctk.CTkScrollableFrame(
            self.ai_window,
            fg_color=self.colors['bg_primary'],
            corner_radius=15,
            scrollbar_button_color=self.colors['border']
        )
        self.ai_chat_display.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Input area
        input_frame = ctk.CTkFrame(self.ai_window, fg_color='transparent', height=120)
        input_frame.pack(fill='x', padx=20, pady=(0, 20))
        input_frame.pack_propagate(False)
        
        self.ai_input = ctk.CTkTextbox(
            input_frame,
            height=80,
            fg_color=self.colors['bg_hover'],
            text_color=self.colors['text_primary'],
            border_width=2,
            border_color=self.colors['border'],
            corner_radius=12
        )
        self.ai_input.pack(fill='both', padx=(0, 10), side='left', expand=True)
        
        send_btn = ctk.CTkButton(
            input_frame, text="➤", width=60, height=80,
            font=ctk.CTkFont(size=24),
            fg_color=self.colors['accent_primary'],
            hover_color=self.colors['accent_secondary'],
            corner_radius=12,
            command=self._send_ai_message
        )
        send_btn.pack(side='right')
        
        # Reset conversation button
        reset_btn = ctk.CTkButton(
            self.ai_window, text="🔄 گفتگوی جدید",
            font=ctk.CTkFont(size=13),
            fg_color=self.colors['bg_hover'],
            hover_color=self.colors['border'],
            text_color=self.colors['text_secondary'],
            height=35,
            corner_radius=10,
            command=self._reset_ai_conversation
        )
        reset_btn.pack(fill='x', padx=20, pady=(0, 15))
    
    def _add_ai_message(self, text, role="assistant"):
        """Add a message to the AI chat display"""
        if not self.ai_chat_display:
            return
        
        msg_frame = ctk.CTkFrame(
            self.ai_chat_display,
            fg_color=self.colors['bg_secondary'] if role == "assistant" else self.colors['bg_hover'],
            corner_radius=12
        )
        msg_frame.pack(fill='x', pady=5, padx=10)
        
        label = ctk.CTkLabel(
            msg_frame,
            text=text,
            font=ctk.CTkFont(family="Gulzar", size=14),
            text_color=self.colors['text_primary'],
            anchor='w',
            justify='left',
            wraplength=380
        )
        label.pack(fill='x', padx=15, pady=12)
        
        # Auto-scroll to bottom
        self.root.after(100, lambda: self.ai_chat_display._parent_canvas.yview_moveto(1.0))
    
    def _send_ai_message(self):
        """Handle sending a message to AI - intelligently determines intent"""
        if not self.ai_input:
            return
        
        user_text = self.ai_input.get("1.0", "end-1c").strip()
        if not user_text:
            return
        
        self.ai_input.delete("1.0", "end")
        self._add_ai_message(user_text, "user")
        
        # Add to conversation history
        self.ai_conversation_history.append({'role': 'user', 'content': user_text})
        
        # If we're collecting personal info, handle that first
        if self.ai_collecting_info:
            self._handle_personal_info_response(user_text)
            return
        
        # Determine intent
        intent_info = self.ai_assistant.determine_intent(user_text)
        
        if intent_info['intent'] == 'planning':
            # Planning mode - first collect personal info, then generate tasks
            self._start_personalization_flow(user_text)
        else:
            # Conversation mode - use LLM for contextual response
            self._add_ai_message("💭 در حال فکر کردن...", "system")
            self.ai_assistant.chat_response(user_text, self.ai_conversation_history, self._on_chat_response)
    
    def _start_personalization_flow(self, user_input: str):
        """Start collecting personal information for customized planning"""
        # Store the user input for fallback
        self._last_user_input = user_input
        # Extract tasks from input using AI
        self._add_ai_message("🤔 در حال تحلیل پیام شما و استخراج وظایف...", "system")
        self.ai_assistant.extract_tasks_with_ai(user_input, self._on_tasks_extracted_for_personalization)
    
    def _on_tasks_extracted_for_personalization(self, success, tasks):
        """Callback when tasks are extracted - then start asking personal questions"""
        def update_ui():
            if success and tasks and len(tasks) > 0:
                # Store tasks properly
                self.ai_pending_tasks = tasks
                print(f"Extracted {len(tasks)} tasks: {[t.get('title', '') for t in tasks]}")
                
                self.ai_collecting_info = True
                self.ai_personal_info = {}
                self._current_question_key = None
                
                # Show what tasks were found
                task_list = "\n".join([f"• {t.get('title', 'Untitled')}" for t in tasks])
                self._add_ai_message(f"📋 I found {len(tasks)} task{'s' if len(tasks) != 1 else ''}:\n{task_list}", "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': f"Found {len(tasks)} tasks"})
                
                # Start asking personal questions
                self.root.after(500, self._ask_next_personal_question)
            else:
                # If extraction failed, try fallback
                print("Task extraction failed, using fallback")
                # Try fallback parsing
                if hasattr(self, '_last_user_input'):
                    fallback_tasks = self.ai_assistant._fallback_parse(self._last_user_input)
                    if fallback_tasks:
                        self.ai_pending_tasks = fallback_tasks
                        self.ai_collecting_info = True
                        self.ai_personal_info = {}
                        self._current_question_key = None
                        self.root.after(500, self._ask_next_personal_question)
                    else:
                        self._add_ai_message("❌ Couldn't extract tasks. Please try rephrasing.", "system")
                        self.ai_collecting_info = False
                else:
                    self._add_ai_message("❌ Couldn't extract tasks. Please try rephrasing.", "system")
                    self.ai_collecting_info = False
        
        self.root.after(0, update_ui)
    
    def _ask_next_personal_question(self):
        """Ask the next personal question - generated dynamically by AI"""
        # Build context from conversation
        context = "User wants to plan tasks. "
        if self.ai_pending_tasks:
            task_titles = [t.get('title', '') for t in self.ai_pending_tasks]
            context += f"Tasks to schedule: {', '.join(task_titles)}. "
        
        context += "Conversation so far: " + " ".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}" 
            for msg in self.ai_conversation_history[-3:]
        ])
        
        # Get list of already asked questions
        already_asked = list(self.ai_personal_info.keys())
        
        # Generate question using AI
        self._add_ai_message("💭 Thinking of the best question to ask...", "system")
        self.ai_assistant.generate_personalized_questions(
            context, 
            already_asked, 
            lambda success, question: self._on_question_generated(success, question, already_asked)
        )
    
    def _on_question_generated(self, success, question, already_asked):
        """Handle generated question from AI"""
        def update_ui():
            if success and question:
                # Determine which category this question belongs to
                question_lower = question.lower()
                
                # Map question to info key
                if any(word in question_lower for word in ['night', 'owl', 'morning', 'person', 'sleep', 'wake']):
                    key = 'sleep_preference'
                elif any(word in question_lower for word in ['energetic', 'energy', 'focus', 'productive', 'peak']):
                    key = 'energy_levels'
                elif any(word in question_lower for word in ['commitment', 'class', 'work', 'meeting', 'fixed', 'schedule']):
                    key = 'time_blocks'
                elif any(word in question_lower for word in ['work style', 'workstyle', 'prefer', 'style', 'approach']):
                    key = 'work_style'
                elif any(word in question_lower for word in ['break', 'rest', 'pause']):
                    key = 'break_preferences'
                else:
                    # Use a generic key if we can't determine
                    key = f'question_{len(already_asked)}'
                
                # Store the question key for later - track which question we're asking
                self._current_question_key = key
                # Also store the question text for context
                self._current_question_text = question
                
                # Ask the question
                self._add_ai_message(question, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': question})
            else:
                # If AI fails to generate, ask a fallback question
                if 'sleep_preference' not in self.ai_personal_info:
                    self._add_ai_message("🌙 Are you a night owl or a morning person?", "assistant")
                    self._current_question_key = 'sleep_preference'
                elif 'energy_levels' not in self.ai_personal_info:
                    self._add_ai_message("⚡ When do you feel most energetic during the day?", "assistant")
                    self._current_question_key = 'energy_levels'
                elif 'time_blocks' not in self.ai_personal_info:
                    self._add_ai_message("📚 Do you have any fixed time commitments I should work around?", "assistant")
                    self._current_question_key = 'time_blocks'
                else:
                    # Enough info collected, proceed
                    self._create_personalized_plan()
        
        self.root.after(0, update_ui)
    
    def _handle_personal_info_response(self, user_input: str):
        """Handle user's response to personal questions - properly track which question was answered"""
        # Use the stored question key - this tells us exactly which question was answered
        if hasattr(self, '_current_question_key') and self._current_question_key:
            current_question_key = self._current_question_key
            # Store the answer with the correct key
            self.ai_personal_info[current_question_key] = user_input.strip()
            
            # Debug: print what we're storing
            print(f"Storing answer '{user_input}' for question key: {current_question_key}")
            
            # Clear the current question key
            self._current_question_key = None
            if hasattr(self, '_current_question_text'):
                self._current_question_text = None
            
            # Simple acknowledgment - don't use AI here to avoid confusion
            self._add_ai_message("✅ Got it!", "assistant")
            self.ai_conversation_history.append({'role': 'assistant', 'content': "✅ Got it!"})
            
            # Check if we have enough info, then ask next question or create plan
            key_info = ['sleep_preference', 'energy_levels', 'time_blocks']
            collected_key_info = sum(1 for key in key_info if key in self.ai_personal_info)
            
            if collected_key_info >= 2 or len(self.ai_personal_info) >= 3:
                # Enough info, proceed to create plan
                self.root.after(1000, self._create_personalized_plan)
            else:
                # Ask next question
                self.root.after(500, self._ask_next_personal_question)
        else:
            # Fallback: determine which question we should be answering based on what's missing
            if 'sleep_preference' not in self.ai_personal_info:
                self.ai_personal_info['sleep_preference'] = user_input.strip()
                print(f"Fallback: Storing '{user_input}' as sleep_preference")
            elif 'energy_levels' not in self.ai_personal_info:
                self.ai_personal_info['energy_levels'] = user_input.strip()
                print(f"Fallback: Storing '{user_input}' as energy_levels")
            elif 'time_blocks' not in self.ai_personal_info:
                self.ai_personal_info['time_blocks'] = user_input.strip()
                print(f"Fallback: Storing '{user_input}' as time_blocks")
            else:
                self.ai_personal_info['work_style'] = user_input.strip()
                print(f"Fallback: Storing '{user_input}' as work_style")
            
            self._add_ai_message("✅ Got it!", "assistant")
            self.root.after(500, self._ask_next_personal_question)
    
    def _on_acknowledgment_received(self, success, response):
        """Handle AI-generated acknowledgment"""
        def update_ui():
            if success:
                self._add_ai_message(response, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': response})
            
            # Check if we have enough info (at least 3 key pieces)
            key_info = ['sleep_preference', 'energy_levels', 'time_blocks']
            collected_key_info = sum(1 for key in key_info if key in self.ai_personal_info)
            
            if collected_key_info >= 2 or len(self.ai_personal_info) >= 3:
                # Enough info, proceed to create plan
                self.root.after(1000, self._create_personalized_plan)
            else:
                # Ask next question
                self.root.after(500, self._ask_next_personal_question)
        
        self.root.after(0, update_ui)
    
    def _create_personalized_plan(self):
        """Create a personalized plan based on collected information using AI"""
        self._add_ai_message("✨ Creating your personalized schedule based on your preferences...", "system")
        
        # Use AI to create the fully personalized schedule
        if self.ai_pending_tasks:
            self.ai_assistant.create_personalized_schedule(
                self.ai_pending_tasks, 
                self.ai_personal_info, 
                self._on_personalized_plan_ready
            )
        else:
            # If no tasks, just acknowledge
            self._add_ai_message("✅ I've noted your preferences! Tell me what tasks you'd like to plan.", "assistant")
            self.ai_collecting_info = False
            self.ai_personal_info = {}
    
    def _on_personalized_plan_ready(self, success, tasks):
        """Callback when personalized plan is ready - add tasks to planner"""
        def update_ui():
            if success and tasks and len(tasks) > 0:
                date_str = self.selected_date.strftime("%Y-%m-%d")
                tasks_added_count = 0
                
                print(f"Adding {len(tasks)} tasks to planner")
                
                # Add tasks - AI should have provided scheduled_time in the response
                for i, task in enumerate(tasks):
                    # Use scheduled_time if AI provided it, otherwise parse from ideal_time
                    if 'scheduled_time' in task:
                        duration = task['scheduled_time']
                    elif 'duration' in task:
                        duration = task['duration']
                    else:
                        # Fallback: parse ideal_time and create time slots
                        ideal = task.get('ideal_time', 'afternoon')
                        # Adjust based on user's energy preference
                        if 'energy_levels' in self.ai_personal_info:
                            energy = self.ai_personal_info['energy_levels'].lower()
                            if 'morning' in energy:
                                ideal = 'morning'
                            elif 'afternoon' in energy:
                                ideal = 'afternoon'
                            elif 'evening' in energy:
                                ideal = 'evening'
                        
                        time_map = {
                            'morning': '9:00 AM - 11:00 AM',
                            'afternoon': '2:00 PM - 4:00 PM',
                            'evening': '6:00 PM - 8:00 PM'
                        }
                        duration = time_map.get(ideal, time_map['afternoon'])
                        
                        # Adjust time to avoid overlap
                        if i > 0:
                            # Add offset to avoid conflicts
                            base_hour = 9 if ideal == 'morning' else (14 if ideal == 'afternoon' else 18)
                            new_hour = (base_hour + (i * 2)) % 24
                            if new_hour < 12:
                                duration = f"{new_hour}:00 AM - {new_hour + 2}:00 AM"
                            else:
                                display_hour = new_hour if new_hour <= 12 else new_hour - 12
                                duration = f"{display_hour}:00 PM - {display_hour + 2}:00 PM"
                    
                    # Determine tag based on difficulty
                    difficulty = task.get('difficulty', 5)
                    if difficulty >= 8:
                        tags = ['urgent']
                    elif difficulty >= 6:
                        tags = ['important']
                    else:
                        tags = ['medium']
                    
                    planner_task = {
                        'title': task.get('title', 'Untitled Task'),
                        'duration': duration,
                        'tags': tags,
                        'completed': False,
                        'date_str': date_str
                    }
                    
                    print(f"Adding task: {planner_task['title']} at {planner_task['duration']}")
                    self.add_task(date_str, planner_task)
                    tasks_added_count += 1
                
                # Generate summary - make sure we show correct information (not tasks in personal info fields)
                summary_parts = [
                    f"✅ Perfect! I've created a personalized schedule for {self.selected_date.strftime('%B %d')} with {tasks_added_count} task{'s' if tasks_added_count != 1 else ''}.",
                    "\n📋 Your schedule is optimized based on:"
                ]
                
                # Only show actual personal info, not tasks
                if 'sleep_preference' in self.ai_personal_info and self.ai_personal_info['sleep_preference']:
                    # Make sure it's not accidentally storing tasks
                    sleep_val = self.ai_personal_info['sleep_preference']
                    if not any(task.get('title', '').lower() in sleep_val.lower() for task in (self.ai_pending_tasks or [])):
                        summary_parts.append(f"• Sleep preference: {sleep_val}")
                
                if 'energy_levels' in self.ai_personal_info and self.ai_personal_info['energy_levels']:
                    energy_val = self.ai_personal_info['energy_levels']
                    if not any(task.get('title', '').lower() in energy_val.lower() for task in (self.ai_pending_tasks or [])):
                        summary_parts.append(f"• Peak energy: {energy_val}")
                
                if 'time_blocks' in self.ai_personal_info and self.ai_personal_info['time_blocks']:
                    time_val = self.ai_personal_info['time_blocks']
                    if time_val.lower() not in ['none', 'no', 'n/a']:
                        if not any(task.get('title', '').lower() in time_val.lower() for task in (self.ai_pending_tasks or [])):
                            summary_parts.append(f"• Fixed commitments: {time_val}")
                
                if 'work_style' in self.ai_personal_info and self.ai_personal_info['work_style']:
                    work_val = self.ai_personal_info['work_style']
                    if not any(task.get('title', '').lower() in work_val.lower() for task in (self.ai_pending_tasks or [])):
                        summary_parts.append(f"• Work style: {work_val}")
                
                summary = "\n".join(summary_parts)
                
                self._add_ai_message(summary, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': summary})
                
                # Reset for next conversation
                self.ai_collecting_info = False
                self.ai_personal_info = {}
                self.ai_pending_tasks = []
                if hasattr(self, '_current_question_key'):
                    self._current_question_key = None
                if hasattr(self, '_current_question_text'):
                    self._current_question_text = None
            else:
                error_msg = "❌ Couldn't create personalized schedule. Adding tasks with default times."
                self._add_ai_message(error_msg, "system")
                # Fallback: add tasks anyway
                if self.ai_pending_tasks:
                    date_str = self.selected_date.strftime("%Y-%m-%d")
                    for task in self.ai_pending_tasks:
                        planner_task = {
                            'title': task.get('title', 'Untitled Task'),
                            'duration': '2:00 PM - 4:00 PM',
                            'tags': ['medium'],
                            'completed': False,
                            'date_str': date_str
                        }
                        self.add_task(date_str, planner_task)
                
                self.ai_collecting_info = False
                self.ai_personal_info = {}
                self.ai_pending_tasks = []
                if hasattr(self, '_current_question_key'):
                    self._current_question_key = None
        
        self.root.after(0, update_ui)
    
    def _on_model_loaded(self, success, message):
        """Callback when AI model is loaded"""
        self.root.after(0, lambda: self._add_ai_message(
            f"✅ {message}" if success else f"❌ {message}",
            "system"
        ))
        if success:
            welcome_msg = "👋 Hello! I'm ready to help you plan tasks or just have a conversation. What would you like to do?"
            self.root.after(500, lambda: (
                self._add_ai_message(welcome_msg, "assistant"),
                self.ai_conversation_history.append({'role': 'assistant', 'content': welcome_msg})
            ))
    
    def _on_tasks_generated(self, success, tasks):
        """Callback when tasks are generated - automatically adds them to planner"""
        def update_ui():
            if success and tasks:
                # Automatically add tasks to the planner
                date_str = self.selected_date.strftime("%Y-%m-%d")
                tasks_added_count = 0
                
                for i, task in enumerate(tasks):
                    # Map ideal_time to actual time slots
                    time_map = {
                        'morning': ('9:00 AM', '11:00 AM'),
                        'afternoon': ('2:00 PM', '4:00 PM'),
                        'evening': ('6:00 PM', '8:00 PM')
                    }
                    
                    ideal = task.get('ideal_time', 'afternoon')
                    start_time, end_time = time_map.get(ideal, time_map['afternoon'])
                    
                    # Adjust times based on task order to avoid overlap
                    if i > 0:
                        hour_offset = i * 2
                        base_hour = int(start_time.split(':')[0].split()[0])
                        if 'PM' in start_time and base_hour != 12:
                            base_hour += 12
                        elif 'AM' in start_time and base_hour == 12:
                            base_hour = 0
                        new_hour = (base_hour + hour_offset) % 24
                        if new_hour >= 12:
                            start_time = f"{new_hour if new_hour <= 12 else new_hour-12}:00 PM"
                            end_time = f"{(new_hour + 2) % 24 if (new_hour + 2) % 24 <= 12 else (new_hour + 2) % 24 - 12}:00 PM"
                        else:
                            start_time = f"{new_hour}:00 AM"
                            end_time = f"{(new_hour + 2) % 24}:00 AM"
                    
                    # Determine tag based on difficulty
                    difficulty = task.get('difficulty', 5)
                    if difficulty >= 8:
                        tags = ['urgent']
                    elif difficulty >= 6:
                        tags = ['important']
                    else:
                        tags = ['medium']
                    
                    planner_task = {
                        'title': task['title'],
                        'duration': f"{start_time} - {end_time}",
                        'tags': tags,
                        'completed': False,
                        'date_str': date_str
                    }
                    
                    self.add_task(date_str, planner_task)
                    tasks_added_count += 1
                
                # Generate contextual response using LLM
                response_text = f"I've added {tasks_added_count} task{'s' if tasks_added_count != 1 else ''} to your schedule for {self.selected_date.strftime('%B %d')}:\n"
                response_text += "\n".join([f"• {t['title']}" for t in tasks])
                
                self._add_ai_message(response_text, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': response_text})
                
                # Ask if they want to personalize or add more
                follow_up = "Would you like me to help personalize your schedule, or is there anything else you'd like to add?"
                self._add_ai_message(follow_up, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': follow_up})
            else:
                error_msg = "❌ Couldn't parse tasks. Please try rephrasing or describing your tasks more clearly."
                self._add_ai_message(error_msg, "system")
                self.ai_conversation_history.append({'role': 'assistant', 'content': error_msg})
        
        self.root.after(0, update_ui)
    
    def _on_schedule_personalized(self, success, tasks):
        """Callback when schedule is personalized - can be called if user requests personalization"""
        def update_ui():
            if success and tasks:
                # Update existing tasks or add new ones
                date_str = self.selected_date.strftime("%Y-%m-%d")
                
                # Clear existing tasks for this date if personalizing
                if date_str in self.tasks_by_date:
                    self.tasks_by_date[date_str] = []
                
                for i, task in enumerate(tasks):
                    # Map ideal_time to actual time slots
                    time_map = {
                        'morning': ('9:00 AM', '11:00 AM'),
                        'afternoon': ('2:00 PM', '4:00 PM'),
                        'evening': ('6:00 PM', '8:00 PM')
                    }
                    
                    ideal = task.get('ideal_time', 'afternoon')
                    start_time, end_time = time_map.get(ideal, time_map['afternoon'])
                    
                    # Adjust times based on task order
                    if i > 0:
                        hour_offset = i * 2
                        base_hour = int(start_time.split(':')[0].split()[0])
                        if 'PM' in start_time and base_hour != 12:
                            base_hour += 12
                        elif 'AM' in start_time and base_hour == 12:
                            base_hour = 0
                        new_hour = (base_hour + hour_offset) % 24
                        if new_hour >= 12:
                            start_time = f"{new_hour if new_hour <= 12 else new_hour-12}:00 PM"
                            end_time = f"{(new_hour + 2) % 24 if (new_hour + 2) % 24 <= 12 else (new_hour + 2) % 24 - 12}:00 PM"
                        else:
                            start_time = f"{new_hour}:00 AM"
                            end_time = f"{(new_hour + 2) % 24}:00 AM"
                    
                    # Determine tag based on difficulty
                    difficulty = task.get('difficulty', 5)
                    if difficulty >= 8:
                        tags = ['urgent']
                    elif difficulty >= 6:
                        tags = ['important']
                    else:
                        tags = ['medium']
                    
                    planner_task = {
                        'title': task['title'],
                        'duration': f"{start_time} - {end_time}",
                        'tags': tags,
                        'completed': False,
                        'date_str': date_str
                    }
                    
                    self.add_task(date_str, planner_task)
                
                response_msg = f"✅ Perfect! I've personalized your schedule for {self.selected_date.strftime('%B %d')} with {len(tasks)} optimized tasks."
                self._add_ai_message(response_msg, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': response_msg})
            else:
                error_msg = "❌ Couldn't personalize schedule. Please try again or describe your preferences."
                self._add_ai_message(error_msg, "system")
                self.ai_conversation_history.append({'role': 'assistant', 'content': error_msg})
        
        self.root.after(0, update_ui)
    
    def _reset_ai_conversation(self):
        """Reset AI conversation state"""
        self.ai_conversation_history = []
        self.ai_collecting_info = False
        self.ai_personal_info = {}
        self.ai_pending_tasks = []
        
        # Clear chat display
        if self.ai_chat_display:
            for widget in self.ai_chat_display.winfo_children():
                widget.destroy()
        
        reset_msg = "🔄 گفتگو بازنشانی شد. آماده کمک به برنامه‌ریزی وظایف یا فقط گفتگو هستم! چه کاری می‌خواهید انجام دهید؟"
        self._add_ai_message(reset_msg, "assistant")
        self.ai_conversation_history.append({'role': 'assistant', 'content': reset_msg})
    
    def _on_chat_response(self, success, response):
        """Callback for general chat responses - uses LLM for contextual responses"""
        def update_ui():
            if success:
                self._add_ai_message(response, "assistant")
                self.ai_conversation_history.append({'role': 'assistant', 'content': response})
                
                # Check if user wants to personalize schedule
                response_lower = response.lower()
                if any(word in response_lower for word in ['personalize', 'optimize', 'reorder', 'schedule']):
                    # User might want to personalize - check if we have tasks
                    date_str = self.selected_date.strftime("%Y-%m-%d")
                    if date_str in self.tasks_by_date and len(self.tasks_by_date[date_str]) > 0:
                        # Convert existing tasks to AI format
                        ai_tasks = []
                        for task in self.tasks_by_date[date_str]:
                            ai_tasks.append({
                                'title': task.get('title', ''),
                                'difficulty': 5,
                                'energy': 5,
                                'ideal_time': 'afternoon'
                            })
                        self.ai_assistant.personalize_schedule(ai_tasks, response, self._on_schedule_personalized)
            else:
                error_msg = f"❌ {response}"
                self._add_ai_message(error_msg, "system")
                self.ai_conversation_history.append({'role': 'assistant', 'content': error_msg})
        
        self.root.after(0, update_ui)

    # --- Settings Panel ---
    
    def _toggle_settings_panel(self):
        """Toggle the settings panel sliding from right"""
        if self.settings_panel_visible:
            self._hide_settings_panel()
        else:
            self._show_settings_panel()
    
    def _show_settings_panel(self):
        """Show the settings panel with sliding animation from right"""
        if self.settings_panel:
            self.settings_panel.destroy()
        
        # Get dimensions
        panel_width = 450
        self.root.update_idletasks()
        screen_width = self.root.winfo_width()
        screen_height = self.root.winfo_height()
        
        # Create settings panel with width and height in constructor
        self.settings_panel = ctk.CTkFrame(
            self.root,
            fg_color=self.colors['bg_secondary'],
            corner_radius=0,
            border_width=2,
            border_color=self.colors['border'],
            width=panel_width,
            height=screen_height
        )
        
        # Position off-screen to the right
        self.settings_panel.place(x=screen_width, y=0)
        self.settings_panel_visible = True
        
        # Create panel content
        self._create_settings_panel_content()
        
        # Animate sliding in from right
        self._animate_settings_panel(screen_width, screen_width - panel_width, -10)
    
    def _hide_settings_panel(self):
        """Hide the settings panel with sliding animation"""
        if not self.settings_panel:
            return
        
        screen_width = self.root.winfo_width()
        current_x = self.settings_panel.winfo_x()
        
        # Animate sliding out to the right
        self._animate_settings_panel(current_x, screen_width, 10, destroy_after=True)
        self.settings_panel_visible = False
    
    def _animate_settings_panel(self, start_x, end_x, step, destroy_after=False):
        """Smooth animation for settings panel sliding"""
        current_x = start_x
        
        def animate():
            nonlocal current_x
            if (step > 0 and current_x < end_x) or (step < 0 and current_x > end_x):
                current_x += step
                self.settings_panel.place(x=current_x)
                self.root.after(5, animate)
            else:
                self.settings_panel.place(x=end_x)
                if destroy_after:
                    self.settings_panel.destroy()
                    self.settings_panel = None
        
        animate()
    
    def _create_settings_panel_content(self):
        """Create the content for settings panel"""
        # Header
        header = ctk.CTkFrame(self.settings_panel, fg_color='transparent', height=80)
        header.pack(fill='x', padx=20, pady=(20, 10))
        header.pack_propagate(False)
        
        ctk.CTkLabel(
            header, text="⚙️ تنظیمات",
            font=ctk.CTkFont(family="Gulzar", size=24, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(side='left')
        
        close_btn = ctk.CTkButton(
            header, text="✕", width=40, height=40,
            font=ctk.CTkFont(size=20),
            fg_color='transparent',
            hover_color=self.colors['error'],
            text_color=self.colors['text_secondary'],
            command=self._hide_settings_panel
        )
        close_btn.pack(side='right')
        
        # Scrollable content
        content_scroll = ctk.CTkScrollableFrame(
            self.settings_panel,
            fg_color='transparent',
            scrollbar_button_color=self.colors['border']
        )
        content_scroll.pack(fill='both', expand=True, padx=20, pady=10)
        
        # --- Notifications Section ---
        notif_section = ctk.CTkFrame(content_scroll, fg_color=self.colors['bg_primary'], corner_radius=15)
        notif_section.pack(fill='x', pady=(0, 15))
        
        ctk.CTkLabel(
            notif_section, text="🔔 اعلان‌ها",
            font=ctk.CTkFont(family="Gulzar", size=18, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(anchor='w', padx=20, pady=(20, 15))
        
        # Enable notifications
        notif_frame = ctk.CTkFrame(notif_section, fg_color='transparent')
        notif_frame.pack(fill='x', padx=20, pady=(0, 10))
        
        notif_var = ctk.BooleanVar(value=self.settings['notifications_enabled'])
        notif_switch = ctk.CTkSwitch(
            notif_frame,
            text="فعال‌سازی اعلان‌ها",
            font=ctk.CTkFont(family="Gulzar", size=14),
            variable=notif_var,
            command=lambda: self._update_setting('notifications_enabled', notif_var.get())
        )
        notif_switch.pack(side='left')
        
        # Notification sound
        sound_frame = ctk.CTkFrame(notif_section, fg_color='transparent')
        sound_frame.pack(fill='x', padx=20, pady=(0, 10))
        
        sound_var = ctk.BooleanVar(value=self.settings['notification_sound'])
        sound_switch = ctk.CTkSwitch(
            sound_frame,
            text="صدای اعلان",
            font=ctk.CTkFont(family="Gulzar", size=14),
            variable=sound_var,
            command=lambda: self._update_setting('notification_sound', sound_var.get())
        )
        sound_switch.pack(side='left')
        
        # Reminder before (minutes)
        reminder_frame = ctk.CTkFrame(notif_section, fg_color='transparent')
        reminder_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        ctk.CTkLabel(
            reminder_frame, text="یادآوری قبل از (دقیقه):",
            font=ctk.CTkFont(family="Gulzar", size=13),
            text_color=self.colors['text_secondary']
        ).pack(side='left', padx=(0, 10))
        
        reminder_var = ctk.StringVar(value=str(self.settings['reminder_before']))
        reminder_entry = ctk.CTkEntry(
            reminder_frame, width=80, height=35,
            textvariable=reminder_var,
            font=ctk.CTkFont(size=13),
            fg_color=self.colors['bg_hover'],
            border_color=self.colors['border']
        )
        reminder_entry.pack(side='right')
        reminder_entry.bind('<KeyRelease>', lambda e: self._update_setting('reminder_before', int(reminder_var.get()) if reminder_var.get().isdigit() else 15))
        
        # --- Auto-Save Section ---
        save_section = ctk.CTkFrame(content_scroll, fg_color=self.colors['bg_primary'], corner_radius=15)
        save_section.pack(fill='x', pady=(0, 15))
        
        ctk.CTkLabel(
            save_section, text="💾 ذخیره خودکار",
            font=ctk.CTkFont(family="Gulzar", size=18, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(anchor='w', padx=20, pady=(20, 15))
        
        # Auto-save toggle
        autosave_frame = ctk.CTkFrame(save_section, fg_color='transparent')
        autosave_frame.pack(fill='x', padx=20, pady=(0, 10))
        
        autosave_var = ctk.BooleanVar(value=self.settings['auto_save'])
        autosave_switch = ctk.CTkSwitch(
            autosave_frame,
            text="ذخیره خودکار وظایف",
            font=ctk.CTkFont(family="Gulzar", size=14),
            variable=autosave_var,
            command=lambda: self._update_setting('auto_save', autosave_var.get())
        )
        autosave_switch.pack(side='left')
        
        # Save interval
        interval_frame = ctk.CTkFrame(save_section, fg_color='transparent')
        interval_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        ctk.CTkLabel(
            interval_frame, text="فاصله ذخیره (ثانیه):",
            font=ctk.CTkFont(family="Gulzar", size=13),
            text_color=self.colors['text_secondary']
        ).pack(side='left', padx=(0, 10))
        
        interval_var = ctk.StringVar(value=str(self.settings['save_interval']))
        interval_entry = ctk.CTkEntry(
            interval_frame, width=80, height=35,
            textvariable=interval_var,
            font=ctk.CTkFont(size=13),
            fg_color=self.colors['bg_hover'],
            border_color=self.colors['border']
        )
        interval_entry.pack(side='right')
        interval_entry.bind('<KeyRelease>', lambda e: self._update_setting('save_interval', int(interval_var.get()) if interval_var.get().isdigit() else 30))
        
        # Manual save/load buttons
        manual_frame = ctk.CTkFrame(save_section, fg_color='transparent')
        manual_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        save_btn = ctk.CTkButton(
            manual_frame, text="💾 ذخیره کن",
            font=ctk.CTkFont(family="Gulzar", size=13, weight="bold"),
            fg_color=self.colors['accent_primary'],
            hover_color=self.colors['accent_secondary'],
            text_color='#FFFFFF',
            height=35,
            corner_radius=10,
            command=self._manual_save
        )
        save_btn.pack(side='left', padx=(0, 10), fill='x', expand=True)
        
        load_btn = ctk.CTkButton(
            manual_frame, text="📂 بارگذاری",
            font=ctk.CTkFont(family="Gulzar", size=13, weight="bold"),
            fg_color=self.colors['bg_hover'],
            hover_color=self.colors['border'],
            text_color=self.colors['text_primary'],
            height=35,
            corner_radius=10,
            command=self._manual_load
        )
        load_btn.pack(side='right', fill='x', expand=True)
        
        # --- Display Section ---
        display_section = ctk.CTkFrame(content_scroll, fg_color=self.colors['bg_primary'], corner_radius=15)
        display_section.pack(fill='x', pady=(0, 15))
        
        ctk.CTkLabel(
            display_section, text="🖥️ نمایش",
            font=ctk.CTkFont(family="Gulzar", size=18, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(anchor='w', padx=20, pady=(20, 15))
        
        # Startup view
        startup_frame = ctk.CTkFrame(display_section, fg_color='transparent')
        startup_frame.pack(fill='x', padx=20, pady=(0, 10))
        
        ctk.CTkLabel(
            startup_frame, text="نمایش اولیه:",
            font=ctk.CTkFont(family="Gulzar", size=13),
            text_color=self.colors['text_secondary']
        ).pack(side='left')
        
        startup_view_map = {'Month': 'ماه', 'Week': 'هفته', 'Day': 'روز'}
        startup_var = ctk.StringVar(value=startup_view_map.get(self.settings.get('startup_view', 'Month'), 'ماه'))
        startup_menu = ctk.CTkOptionMenu(
            startup_frame,
            values=['ماه', 'هفته', 'روز'],
            variable=startup_var,
            command=lambda v: self._update_setting('startup_view', {'ماه': 'Month', 'هفته': 'Week', 'روز': 'Day'}.get(v, v)),
            width=120,
            fg_color=self.colors['bg_hover'],
            button_color=self.colors['border']
        )
        startup_menu.pack(side='right')
        
        # Show completed tasks
        completed_frame = ctk.CTkFrame(display_section, fg_color='transparent')
        completed_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        completed_var = ctk.BooleanVar(value=self.settings['show_completed_tasks'])
        completed_switch = ctk.CTkSwitch(
            completed_frame,
            text="نمایش وظایف تکمیل شده",
            font=ctk.CTkFont(family="Gulzar", size=14),
            variable=completed_var,
            command=lambda: self._update_setting('show_completed_tasks', completed_var.get())
        )
        completed_switch.pack(side='left')
        
        # Compact mode
        compact_frame = ctk.CTkFrame(display_section, fg_color='transparent')
        compact_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        compact_var = ctk.BooleanVar(value=self.settings['compact_mode'])
        compact_switch = ctk.CTkSwitch(
            compact_frame,
            text="حالت فشرده",
            font=ctk.CTkFont(family="Gulzar", size=14),
            variable=compact_var,
            command=lambda: self._update_setting('compact_mode', compact_var.get())
        )
        compact_switch.pack(side='left')
        
        # --- General Section ---
        general_section = ctk.CTkFrame(content_scroll, fg_color=self.colors['bg_primary'], corner_radius=15)
        general_section.pack(fill='x', pady=(0, 15))
        
        ctk.CTkLabel(
            general_section, text="⚙️ عمومی",
            font=ctk.CTkFont(family="Gulzar", size=18, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(anchor='w', padx=20, pady=(20, 15))
        
        # Default duration
        duration_frame = ctk.CTkFrame(general_section, fg_color='transparent')
        duration_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        ctk.CTkLabel(
            duration_frame, text="مدت پیش‌فرض:",
            font=ctk.CTkFont(family="Gulzar", size=13),
            text_color=self.colors['text_secondary']
        ).pack(side='left')
        
        duration_var = ctk.StringVar(value=self.settings['default_duration'])
        duration_menu = ctk.CTkOptionMenu(
            duration_frame,
            values=['30 min', '1 hour', '2 hours', '3 hours', '4 hours'],
            variable=duration_var,
            command=lambda v: self._update_setting('default_duration', v),
            width=120,
            fg_color=self.colors['bg_hover'],
            button_color=self.colors['border']
        )
        duration_menu.pack(side='right')
        
        # Data location info
        info_frame = ctk.CTkFrame(general_section, fg_color=self.colors['bg_hover'], corner_radius=10)
        info_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        ctk.CTkLabel(
            info_frame, text=f"📁 Data Location:\n{self.data_dir}",
            font=ctk.CTkFont(family="Gulzar", size=11),
            text_color=self.colors['text_secondary'],
            justify='left'
        ).pack(padx=15, pady=15)
    
    def _update_setting(self, key, value):
        """Update a setting and save"""
        self.settings[key] = value
        self._save_settings()
    
    def _manual_save(self):
        """Manually save tasks"""
        self._save_tasks()
        # Show confirmation
        if hasattr(self, 'settings_panel'):
            # Could add a toast notification here
            pass
    
    def _manual_load(self):
        """Manually load tasks"""
        self._load_tasks()
        self._refresh_tasks()
        if self.current_view == "Month" and self.cal_grid_container:
            self._populate_calendar(self.cal_grid_container)
        elif self.current_view == "Week" and self.week_time_grid:
            self._populate_week_view(self.view_container)
        elif self.current_view == "Day" and self.day_time_grid:
            self._populate_day_view(self.view_container)
    
    def _save_settings(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def _load_settings(self):
        """Load settings from file"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
                    
                    # Apply loaded settings
                    if 'theme' in self.settings and self.settings['theme'] in THEMES:
                        self.current_theme_key = self.settings['theme']
                        self.colors = THEMES[self.current_theme_key]
                    if 'startup_view' in self.settings:
                        self.current_view = self.settings['startup_view']
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def _save_tasks(self):
        """Save tasks to file"""
        try:
            # Convert datetime objects to strings for JSON
            tasks_to_save = {}
            for date_str, tasks in self.tasks_by_date.items():
                tasks_to_save[date_str] = tasks
            
            with open(self.tasks_file, 'w') as f:
                json.dump(tasks_to_save, f, indent=2)
        except Exception as e:
            print(f"Error saving tasks: {e}")
    
    def _load_tasks(self):
        """Load tasks from file"""
        try:
            if self.tasks_file.exists():
                with open(self.tasks_file, 'r') as f:
                    loaded = json.load(f)
                    self.tasks_by_date = loaded
        except Exception as e:
            print(f"Error loading tasks: {e}")
    
    def _auto_save_tasks(self):
        """Auto-save tasks if enabled"""
        if self.settings.get('auto_save', True):
            self._save_tasks()
        
        # Schedule next auto-save
        interval = self.settings.get('save_interval', 30) * 1000  # Convert to milliseconds
        self.root.after(interval, self._auto_save_tasks)

    # --- Month View ---

    def _create_month_view(self, parent):
        """Builds the Month View UI elements."""
        cal_header = ctk.CTkFrame(parent, fg_color='transparent', height=70)
        cal_header.pack(fill='x', padx=25, pady=(25, 15))
        cal_header.pack_propagate(False)

        prev_btn = self._create_icon_button(cal_header, "◀", lambda: self._change_month(-1), width=40)
        prev_btn.pack(side='left')

        month_year = self.current_date.strftime("%B %Y")
        self.month_label = ctk.CTkLabel(
            cal_header, text=month_year,
            font=ctk.CTkFont(family="Gulzar", size=22, weight="bold"),
            text_color=self.colors['text_primary']
        )
        self.month_label.pack(side='left', expand=True)

        next_btn = self._create_icon_button(cal_header, "▶", lambda: self._change_month(1), width=40)
        next_btn.pack(side='right')

        self.cal_grid_container = ctk.CTkFrame(parent, fg_color='transparent')
        self.cal_grid_container.pack(fill='both', expand=True, padx=25, pady=(0, 25))

        weekdays = ['دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه', 'شنبه', 'یکشنبه']
        for i, day in enumerate(weekdays):
            ctk.CTkLabel(
                self.cal_grid_container, text=day,
                font=ctk.CTkFont(family="Gulzar", size=12, weight="bold"),
                text_color=self.colors['text_tertiary'], height=30
            ).grid(row=0, column=i, sticky='ew', padx=5, pady=(0, 10))

        for i in range(7): self.cal_grid_container.columnconfigure(i, weight=1)
        for i in range(7): self.cal_grid_container.rowconfigure(i+1, weight=1)

        self._populate_calendar(self.cal_grid_container)

    def _populate_calendar(self, grid_frame):
        """Fills the month grid with date buttons."""
        for btn in self.day_buttons.values(): btn.destroy()
        self.day_buttons.clear()
        
        year = self.current_date.year
        month = self.current_date.month
        cal = calendar.monthcalendar(year, month)
        
        today = datetime.now().date()
        selected = self.selected_date.date()
        
        for week_idx, week in enumerate(cal, start=1):
            for day_idx, day in enumerate(week):
                if day == 0: continue
                
                date_obj = datetime(year, month, day).date()
                date_key = date_obj.strftime("%Y-%m-%d")
                has_tasks = date_key in self.tasks_by_date and len(self.tasks_by_date[date_key]) > 0
                
                btn = self._create_day_button(
                    grid_frame, day, date_obj, 
                    (date_obj == today), (date_obj == selected), has_tasks
                )
                btn.grid(row=week_idx, column=day_idx, sticky='nsew', padx=4, pady=4)
                self.day_buttons[date_key] = btn

    # --- Week View ---

    def _create_week_view(self, parent):
        """Sets up the Week View containers."""
        week_header_frame = ctk.CTkFrame(parent, fg_color='transparent', height=70)
        week_header_frame.pack(fill='x', padx=10, pady=(10, 0))
        week_header_frame.columnconfigure((0, 8), weight=0)
        for i in range(7): week_header_frame.columnconfigure(i+1, weight=1)
        
        self.week_header_frame = week_header_frame

        self.week_scroll = ctk.CTkScrollableFrame(
            parent, fg_color='transparent', scrollbar_button_color=self.colors['border'], 
            scrollbar_button_hover_color=self.colors['text_tertiary']
        )
        self.week_scroll.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self.week_time_grid = ctk.CTkFrame(self.week_scroll, fg_color='transparent')
        self.week_time_grid.pack(fill='both', expand=True)
        self.week_time_grid.columnconfigure(0, weight=0, minsize=50) 
        for i in range(7): self.week_time_grid.columnconfigure(i+1, weight=1)

        self._populate_week_view(parent)

    def _populate_week_view(self, parent):
        """Fills the Week View grid with tasks and dates."""
        if not self.week_header_frame or not self.week_time_grid: return
        
        start_of_week = self.selected_date - timedelta(days=self.selected_date.weekday())
        
        for w in self.week_header_frame.winfo_children(): w.destroy()
        
        self._create_icon_button(self.week_header_frame, "◀", lambda: self._change_week(-1), width=40).grid(row=0, column=0, padx=(5, 0))
        self._create_icon_button(self.week_header_frame, "▶", lambda: self._change_week(1), width=40).grid(row=0, column=8, padx=(0, 5))

        for i in range(7):
            day_date = start_of_week + timedelta(days=i)
            is_sel = (day_date.date() == self.selected_date.date())
            is_today = (day_date.date() == datetime.now().date())
            fg = self.colors['selected'] if is_sel else (self.colors['today'] if is_today else self.colors['bg_secondary'])
            tc = '#FFFFFF' if is_sel else (self.colors['accent_primary'] if is_today else self.colors['text_primary'])
            
            ctk.CTkButton(
                self.week_header_frame, text=day_date.strftime("%a\n%d"),
                fg_color=fg, text_color=tc, hover_color=self.colors['bg_hover'],
                height=50, corner_radius=10, command=lambda d=day_date.date(): self._on_day_click(d)
            ).grid(row=0, column=i+1, sticky='nsew', padx=5, pady=10)

        for w in self.week_time_grid.winfo_children(): w.destroy()
        
        for h in range(24):
            ctk.CTkLabel(self.week_time_grid, text=f"{h:02}:00", text_color=self.colors['text_secondary'], width=50, anchor='ne').grid(row=h, column=0, sticky='ne', padx=5)
            ctk.CTkFrame(self.week_time_grid, height=1, fg_color=self.colors['border']).grid(row=h, column=1, columnspan=7, sticky='ew')
            self.week_time_grid.rowconfigure(h, minsize=50)
            
        for i in range(7):
            day_date = start_of_week + timedelta(days=i)
            date_key = day_date.strftime("%Y-%m-%d")
            col = i + 1
            tasks = self.tasks_by_date.get(date_key, [])
            
            for task in tasks:
                if 'duration' in task and '-' in task['duration']:
                    try:
                        time_from_str, time_to_str = [t.strip().replace(' AM', '').replace(' PM', '') for t in task['duration'].split('-')]
                        
                        sh = int(datetime.strptime(time_from_str.strip(), "%I:%M").strftime("%H"))
                        eh = int(datetime.strptime(time_to_str.strip(), "%I:%M").strftime("%H"))
                        span = max(1, eh - sh)
                        
                        task_frame = ctk.CTkFrame(
                            self.week_time_grid, fg_color=self._get_tag_color(task['tags'][0] if task['tags'] else 'medium'), 
                            corner_radius=8
                        )
                        task_frame.grid(row=sh, column=col, rowspan=span, sticky='nsew', padx=2, pady=2)
                        ctk.CTkLabel(task_frame, text=f"{task['title']}", text_color='white', font=ctk.CTkFont(size=11, weight="bold")).pack(padx=5, pady=2)
                        task_frame.task_data = task
                        task_frame.bind('<Button-1>', lambda e, t=task_frame: self._on_task_click_in_view(t))
                        task_frame.bind('<Double-Button-1>', lambda e, t=task: self._open_edit_dialog(t))
                    except ValueError: 
                        pass

    # --- Day View ---

    def _create_day_view(self, parent):
        """Sets up the Day View containers."""
        day_header_frame = ctk.CTkFrame(parent, fg_color='transparent', height=70)
        day_header_frame.pack(fill='x', padx=10, pady=(10, 0))
        day_header_frame.columnconfigure(1, weight=1)
        self.day_header_frame = day_header_frame

        self.day_scroll = ctk.CTkScrollableFrame(
            parent, fg_color='transparent', scrollbar_button_color=self.colors['border'], 
            scrollbar_button_hover_color=self.colors['text_tertiary']
        )
        self.day_scroll.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self.day_time_grid = ctk.CTkFrame(self.day_scroll, fg_color='transparent')
        self.day_time_grid.pack(fill='both', expand=True)
        self.day_time_grid.columnconfigure(0, weight=0, minsize=50)
        self.day_time_grid.columnconfigure(1, weight=1)

        self._populate_day_view(parent)

    def _populate_day_view(self, parent):
        """Fills the Day View grid with tasks."""
        if not self.day_header_frame or not self.day_time_grid: return
        
        for w in self.day_header_frame.winfo_children(): w.destroy()
        d_str = self.selected_date.strftime("%A, %B %d, %Y")
        
        self._create_icon_button(self.day_header_frame, "◀", lambda: self._change_day(-1), 40).grid(row=0, column=0, padx=5)
        ctk.CTkLabel(self.day_header_frame, text=d_str, font=ctk.CTkFont(size=20, weight="bold"), text_color=self.colors['text_primary']).grid(row=0, column=1)
        self._create_icon_button(self.day_header_frame, "▶", lambda: self._change_day(1), 40).grid(row=0, column=2, padx=5)

        for w in self.day_time_grid.winfo_children(): w.destroy()
        date_key = self.selected_date.strftime("%Y-%m-%d")
        tasks = self.tasks_by_date.get(date_key, [])

        for h in range(24):
            ctk.CTkLabel(self.day_time_grid, text=f"{h:02}:00", text_color=self.colors['text_secondary'], width=50, anchor='ne').grid(row=h, column=0, sticky='ne', padx=5)
            ctk.CTkFrame(self.day_time_grid, height=1, fg_color=self.colors['border']).grid(row=h, column=1, sticky='ew')
            self.day_time_grid.rowconfigure(h, minsize=50)
            
        for task in tasks:
            if 'duration' in task and '-' in task['duration']:
                try:
                    time_from_str, time_to_str = [t.strip().replace(' AM', '').replace(' PM', '') for t in task['duration'].split('-')]
                    
                    sh = int(datetime.strptime(time_from_str.strip(), "%I:%M").strftime("%H"))
                    eh = int(datetime.strptime(time_to_str.strip(), "%I:%M").strftime("%H"))
                    span = max(1, eh - sh)
                    
                    task_frame = ctk.CTkFrame(
                        self.day_time_grid, fg_color=self._get_tag_color(task['tags'][0] if task['tags'] else 'medium'), 
                        corner_radius=8
                    )
                    task_frame.grid(row=sh, column=1, rowspan=span, sticky='nsew', padx=5, pady=2)
                    ctk.CTkLabel(task_frame, text=f"{task['title']} ({time_from_str})", text_color='white', font=ctk.CTkFont(size=13, weight="bold")).pack(padx=10, pady=5)
                    task_frame.task_data = task
                    task_frame.bind('<Button-1>', lambda e, t=task_frame: self._on_task_click_in_view(t))
                    task_frame.bind('<Double-Button-1>', lambda e, t=task: self._open_edit_dialog(t))
                except ValueError: 
                    pass

    # --- Navigation Helpers ---

    def _change_month(self, delta):
        month = self.current_date.month + delta
        year = self.current_date.year
        
        if month > 12: month = 1; year += 1
        elif month < 1: month = 12; year -= 1
        
        self.current_date = self.current_date.replace(year=year, month=month, day=1)
        self._update_month_label()
        
        if self.current_view == "Month":
            self._populate_calendar(self.cal_grid_container)

    def _change_week(self, delta):
        new_date = self.selected_date + timedelta(weeks=delta)
        self.selected_date = new_date
        self._update_header()
        if self.current_view == "Week":
            self._populate_week_view(self.view_container)

    def _change_day(self, delta):
        new_date = self.selected_date + timedelta(days=delta)
        self.selected_date = new_date
        self._update_header()
        if self.current_view == "Day":
            self._populate_day_view(self.view_container)

    def _on_day_click(self, date_obj):
        """Handle day selection, refreshes views."""
        self.selected_date = datetime.combine(date_obj, datetime.min.time())
        self._update_header()
        
        if self.current_view == "Week":
            self._populate_week_view(self.view_container)
        elif self.current_view == "Day":
            self._populate_day_view(self.view_container)
        elif self.current_view == "Month":
            if self.selected_date.month != self.current_date.month:
                self.current_date = self.selected_date.replace(day=1)
                self._update_month_label()
            self._populate_calendar(self.cal_grid_container)
        
        self._refresh_tasks()
        self.on_day_select(date_obj)

    def _on_task_click_in_view(self, frame):
        """Handles clicking a task block in Week/Day view to select the corresponding date and task card."""
        target_task = frame.task_data
        
        task_date_str = target_task['date_str'] if 'date_str' in target_task else self.selected_date.strftime("%Y-%m-%d")
        task_date = datetime.strptime(task_date_str, "%Y-%m-%d").date()
        self._on_day_click(task_date)

        self.root.after(100, lambda: self._select_task_card(target_task))

    def _select_task_card(self, target_task):
        """Helper to select a task card after tasks panel refresh."""
        for card in self.task_cards:
            if card.task_data['title'] == target_task['title'] and card.task_data.get('duration') == target_task.get('duration'):
                self._on_card_click(card)
                self.tasks_scroll.yview_moveto(card.winfo_y() / self.tasks_scroll.winfo_height())
                break
                
    # --- UI Helper Methods ---

    def _create_day_button(self, parent, day, date_obj, is_today, is_selected, has_tasks):
        """Create a single day button with premium styling"""
        if is_selected:
            fg_color = self.colors['selected']
            text_color = '#FFFFFF'
            hover_color = self.colors['accent_secondary']
            border_color = self.colors['selected'] 
        elif is_today:
            fg_color = self.colors['today']
            text_color = self.colors['accent_primary']
            hover_color = self.colors['bg_hover']
            border_color = self.colors['accent_primary']
        else:
            fg_color = self.colors['transparent']
            text_color = self.colors['text_primary']
            hover_color = self.colors['bg_hover']
            border_color = self.colors['transparent']
        
        container = ctk.CTkFrame(parent, fg_color='transparent')
        btn = ctk.CTkButton(
            container, text=str(day),
            font=ctk.CTkFont(family="Gulzar", size=15, weight="bold" if is_selected else "normal"),
            fg_color=fg_color, text_color=text_color, hover_color=hover_color,
            corner_radius=12, border_width=2 if is_today else 0, border_color=border_color,
            command=lambda d=date_obj: self._on_day_click(d)
        )
        btn.pack(fill='both', expand=True, padx=2, pady=2)
        
        if has_tasks and not is_selected:
            ctk.CTkLabel(container, text="●", font=ctk.CTkFont(size=8), text_color=self.colors['task_dot']).place(relx=0.5, rely=0.85, anchor='center')
        
        return container
    
    def _create_primary_button(self, parent, text, command):
        return ctk.CTkButton(parent, text=text, font=ctk.CTkFont(family="Gulzar", size=15, weight="bold"), fg_color=self.colors['accent_primary'], hover_color=self.colors['accent_secondary'], text_color='#FFFFFF', corner_radius=14, height=50, width=160, command=command)

    def _create_secondary_button(self, parent, text, command, fg_color=None, text_color=None, hover_color=None):
        return ctk.CTkButton(
            parent, text=text, font=ctk.CTkFont(family="Gulzar", size=15), 
            fg_color=fg_color or self.colors['bg_hover'], 
            hover_color=hover_color or self.colors['border'], 
            text_color=text_color or self.colors['text_primary'], 
            corner_radius=14, height=50, width=130, border_width=1, border_color=self.colors['border'], command=command
        )

    def _create_ai_button(self, parent, text, command):
        return ctk.CTkButton(parent, text=text, font=ctk.CTkFont(family="Gulzar", size=15, weight="bold"), fg_color=self.colors['accent_tertiary'], hover_color=self.colors['accent_secondary'], text_color='#FFFFFF', corner_radius=14, height=50, width=180, command=command)

    def _create_icon_button(self, parent, text, command, width=50):
        return ctk.CTkButton(parent, text=text, font=ctk.CTkFont(size=16), fg_color='transparent', hover_color=self.colors['bg_hover'], text_color=self.colors['text_secondary'], corner_radius=10, width=width, height=40, command=command, border_width=0)

    def _launch_mk48_game(self):
        """Launch the MK48.io naval combat game"""
        try:
            game_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mk48_game', 'index.html')
            game_path = os.path.abspath(game_path)
            
            if os.path.exists(game_path):
                # Convert file path to file URL
                file_url = f"file:///{game_path.replace(os.sep, '/')}"
                webbrowser.open(file_url)
            else:
                # Fallback to online version if local file doesn't exist
                webbrowser.open("https://mk48.io")
        except Exception as e:
            # Fallback to online version if anything goes wrong
            webbrowser.open("https://mk48.io")

    def _get_tag_color(self, tag):
        """Get color for task tag"""
        tag_colors = {
            'urgent': self.colors['error'],
            'important': self.colors['warning'],
            'high': self.colors['accent_tertiary'],
            'medium': self.colors['accent_primary'],
            'low': self.colors['success'],
            'work': self.colors['accent_primary'],
            'personal': self.colors['accent_secondary'],
            'dev': self.colors['success']
        }
        return tag_colors.get(tag.lower(), self.colors['text_tertiary'])
        
    def _on_card_hover(self, card, is_hover):
        if is_hover:
            card.configure(fg_color=self.colors['bg_secondary'], border_color=self.colors['accent_primary'])
        else:
            border_color = self.colors['accent_primary'] if card == self.selected_task else self.colors['transparent']
            fg_color = self.colors['bg_hover'] if card != self.selected_task else self.colors['bg_secondary']
            card.configure(fg_color=fg_color, border_color=border_color)
    
    def _on_card_click(self, card, event=None):
        if self.selected_task: self.selected_task.configure(border_color=self.colors['transparent'], fg_color=self.colors['bg_hover'])
        self.selected_task = card
        card.configure(border_color=self.colors['accent_primary'], fg_color=self.colors['bg_secondary'])
        self.edit_btn.configure(state='normal')
        self.delete_btn.configure(state='normal')
    
    def _on_card_double_click(self, card, event):
        """Open edit dialog on double-click (Google Calendar style)"""
        self._open_edit_dialog(card.task_data)

    def _on_task_toggle(self, card):
        card.task_data['completed'] = not card.task_data.get('completed', False)
        if card.task_data['completed']:
            card.winfo_children()[0].winfo_children()[1].configure(text_color=self.colors['text_secondary'])
        else:
            card.winfo_children()[0].winfo_children()[1].configure(text_color=self.colors['text_primary'])
        
        # Update task in tasks_by_date
        date_str = card.task_data.get('date_str', self.selected_date.strftime("%Y-%m-%d"))
        if date_str in self.tasks_by_date:
            for task in self.tasks_by_date[date_str]:
                if (task.get('title') == card.task_data.get('title') and 
                    task.get('duration') == card.task_data.get('duration')):
                    task['completed'] = card.task_data['completed']
                    break
        
        self.on_task_toggle(card.task_data)
        self._refresh_tasks()
        
        # Auto-save
        if self.settings.get('auto_save', True):
            self.root.after(1000, self._save_tasks)

    def _handle_edit_task(self):
        """Open edit dialog when Edit button is clicked"""
        if self.selected_task:
            self._open_edit_dialog(self.selected_task.task_data)
    
    def _open_edit_dialog(self, task_data):
        """Open Google Calendar-style edit dialog"""
        # Create modal dialog window
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("ویرایش وظیفه")
        dialog.geometry("500x600")
        dialog.configure(fg_color=self.colors['bg_primary'])
        dialog.transient(self.root)
        dialog.grab_set()  # Make it modal
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (600 // 2)
        dialog.geometry(f"500x600+{x}+{y}")
        
        # Main container
        main_frame = ctk.CTkFrame(dialog, fg_color=self.colors['bg_secondary'], corner_radius=20)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Header
        header = ctk.CTkFrame(main_frame, fg_color='transparent', height=60)
        header.pack(fill='x', padx=25, pady=(25, 15))
        header.pack_propagate(False)
        
        ctk.CTkLabel(
            header, text="ویرایش وظیفه",
            font=ctk.CTkFont(family="Gulzar", size=24, weight="bold"),
            text_color=self.colors['text_primary']
        ).pack(side='left')
        
        close_btn = ctk.CTkButton(
            header, text="✕", width=35, height=35,
            font=ctk.CTkFont(size=18),
            fg_color='transparent',
            hover_color=self.colors['error'],
            text_color=self.colors['text_secondary'],
            command=dialog.destroy
        )
        close_btn.pack(side='right')
        
        # Scrollable content
        content_scroll = ctk.CTkScrollableFrame(
            main_frame, fg_color='transparent',
            scrollbar_button_color=self.colors['border']
        )
        content_scroll.pack(fill='both', expand=True, padx=25, pady=(0, 15))
        
        # Title field
        ctk.CTkLabel(
            content_scroll, text="عنوان",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        ).pack(fill='x', pady=(0, 8))
        
        title_entry = ctk.CTkEntry(
            content_scroll,
            height=45,
            fg_color=self.colors['bg_hover'],
            text_color=self.colors['text_primary'],
            border_width=2,
            border_color=self.colors['border'],
            corner_radius=12,
            font=ctk.CTkFont(family="Gulzar", size=15)
        )
        title_entry.pack(fill='x', pady=(0, 20))
        title_entry.insert(0, task_data.get('title', ''))
        
        # Date field
        ctk.CTkLabel(
            content_scroll, text="تاریخ",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        ).pack(fill='x', pady=(0, 8))
        
        current_date_str = task_data.get('date_str', self.selected_date.strftime("%Y-%m-%d"))
        current_date = datetime.strptime(current_date_str, "%Y-%m-%d")
        
        date_frame = ctk.CTkFrame(content_scroll, fg_color='transparent')
        date_frame.pack(fill='x', pady=(0, 20))
        
        date_entry = ctk.CTkEntry(
            date_frame,
            height=45,
            fg_color=self.colors['bg_hover'],
            text_color=self.colors['text_primary'],
            border_width=2,
            border_color=self.colors['border'],
            corner_radius=12,
            font=ctk.CTkFont(family="Gulzar", size=15),
            placeholder_text="YYYY-MM-DD"
        )
        date_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        date_entry.insert(0, current_date_str)
        
        today_btn = ctk.CTkButton(
            date_frame, text="امروز", width=80, height=45,
            font=ctk.CTkFont(size=13),
            fg_color=self.colors['bg_hover'],
            hover_color=self.colors['border'],
            text_color=self.colors['text_primary'],
            command=lambda: date_entry.delete(0, 'end') or date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        )
        today_btn.pack(side='right')
        
        # Time/Duration field
        ctk.CTkLabel(
            content_scroll, text="مدت زمان",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        ).pack(fill='x', pady=(0, 8))
        
        duration_entry = ctk.CTkEntry(
            content_scroll,
            height=45,
            fg_color=self.colors['bg_hover'],
            text_color=self.colors['text_primary'],
            border_width=2,
            border_color=self.colors['border'],
            corner_radius=12,
            font=ctk.CTkFont(family="Gulzar", size=15),
            placeholder_text="e.g., 10:00 AM - 11:00 AM"
        )
        duration_entry.pack(fill='x', pady=(0, 20))
        duration_entry.insert(0, task_data.get('duration', ''))
        
        # Tags field
        ctk.CTkLabel(
            content_scroll, text="برچسب‌ها (با کاما جدا کنید)",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        ).pack(fill='x', pady=(0, 8))
        
        tags_entry = ctk.CTkEntry(
            content_scroll,
            height=45,
            fg_color=self.colors['bg_hover'],
            text_color=self.colors['text_primary'],
            border_width=2,
            border_color=self.colors['border'],
            corner_radius=12,
            font=ctk.CTkFont(family="Gulzar", size=15),
            placeholder_text="e.g., urgent, work, important"
        )
        tags_entry.pack(fill='x', pady=(0, 20))
        if 'tags' in task_data and task_data['tags']:
            tags_entry.insert(0, ', '.join(task_data['tags']))
        
        # Quick tag buttons
        quick_tags_frame = ctk.CTkFrame(content_scroll, fg_color='transparent')
        quick_tags_frame.pack(fill='x', pady=(0, 20))
        
        quick_tags = ['urgent', 'important', 'work', 'personal', 'low', 'medium', 'high']
        for tag in quick_tags:
            btn = ctk.CTkButton(
                quick_tags_frame, text=tag, width=80, height=30,
                font=ctk.CTkFont(size=11),
                fg_color=self._get_tag_color(tag),
                hover_color=self.colors['border'],
                text_color='#FFFFFF',
                command=lambda t=tag: self._add_tag_to_entry(tags_entry, t)
            )
            btn.pack(side='left', padx=(0, 8))
        
        # Completed checkbox
        completed_var = ctk.BooleanVar(value=task_data.get('completed', False))
        completed_check = ctk.CTkCheckBox(
            content_scroll,
            text="علامت‌گذاری به عنوان تکمیل شده",
            font=ctk.CTkFont(family="Gulzar", size=14),
            fg_color=self.colors['success'],
            hover_color=self.colors['accent_primary'],
            variable=completed_var,
            checkmark_color='#FFFFFF'
        )
        completed_check.pack(fill='x', pady=(0, 20))
        
        # Action buttons
        button_frame = ctk.CTkFrame(main_frame, fg_color='transparent')
        button_frame.pack(fill='x', padx=25, pady=(0, 25))
        
        delete_btn = ctk.CTkButton(
            button_frame, text="🗑 Delete",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            fg_color=self.colors['error'],
            hover_color=self.colors['accent_tertiary'],
            text_color='#FFFFFF',
            height=45,
            corner_radius=12,
            command=lambda: self._delete_from_dialog(dialog, task_data)
        )
        delete_btn.pack(side='left', padx=(0, 10))
        
        cancel_btn = ctk.CTkButton(
            button_frame, text="لغو",
            font=ctk.CTkFont(family="Gulzar", size=14),
            fg_color=self.colors['bg_hover'],
            hover_color=self.colors['border'],
            text_color=self.colors['text_primary'],
            height=45,
            corner_radius=12,
            command=dialog.destroy
        )
        cancel_btn.pack(side='right', padx=(10, 0))
        
        save_btn = ctk.CTkButton(
            button_frame, text="ذخیره",
            font=ctk.CTkFont(family="Gulzar", size=14, weight="bold"),
            fg_color=self.colors['accent_primary'],
            hover_color=self.colors['accent_secondary'],
            text_color='#FFFFFF',
            height=45,
            corner_radius=12,
            command=lambda: self._save_task_from_dialog(
                dialog, task_data, title_entry, date_entry, duration_entry, tags_entry, completed_var
            )
        )
        save_btn.pack(side='right')
    
    def _add_tag_to_entry(self, entry, tag):
        """Add a tag to the tags entry field"""
        current = entry.get()
        if current:
            if tag not in current:
                entry.insert('end', f', {tag}')
        else:
            entry.insert(0, tag)
    
    def _save_task_from_dialog(self, dialog, original_task, title_entry, date_entry, duration_entry, tags_entry, completed_var):
        """Save task from edit dialog"""
        # Get values
        title = title_entry.get().strip()
        if not title:
            return  # Title is required
        
        date_str = date_entry.get().strip()
        try:
            # Validate date format
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return  # Invalid date format
        
        duration = duration_entry.get().strip()
        tags_str = tags_entry.get().strip()
        tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []
        completed = completed_var.get()
        
        # Create updated task
        updated_task = {
            'title': title,
            'duration': duration,
            'tags': tags,
            'completed': completed,
            'date_str': date_str
        }
        
        # Find task index in original date
        original_date_str = original_task.get('date_str', self.selected_date.strftime("%Y-%m-%d"))
        date_key = original_date_str
        
        # Find the task index
        task_index = -1
        if date_key in self.tasks_by_date:
            for i, task in enumerate(self.tasks_by_date[date_key]):
                if (task.get('title') == original_task.get('title') and 
                    task.get('duration') == original_task.get('duration')):
                    task_index = i
                    break
        
        # If date changed, remove from old date and add to new date
        if date_str != original_date_str:
            if task_index != -1 and date_key in self.tasks_by_date:
                self.tasks_by_date[date_key].pop(task_index)
            
            if date_str not in self.tasks_by_date:
                self.tasks_by_date[date_str] = []
            self.tasks_by_date[date_str].append(updated_task)
            
            # Update selected date if needed
            self.selected_date = datetime.strptime(date_str, "%Y-%m-%d")
            self._update_header()
        else:
            # Update in place
            if task_index != -1:
                self.update_task(date_key, task_index, updated_task)
            else:
                # Task not found, just add it
                if date_str not in self.tasks_by_date:
                    self.tasks_by_date[date_str] = []
                self.tasks_by_date[date_str].append(updated_task)
        
        # Call the callback
        self.on_edit_task(updated_task)
        
        # Refresh UI
        self.set_tasks(self.tasks_by_date)
        
        # Auto-save
        if self.settings.get('auto_save', True):
            self.root.after(1000, self._save_tasks)
        
        # Close dialog
        dialog.destroy()
    
    def _delete_from_dialog(self, dialog, task_data):
        """Delete task from edit dialog"""
        date_str = task_data.get('date_str', self.selected_date.strftime("%Y-%m-%d"))
        
        # Find and remove task
        if date_str in self.tasks_by_date:
            for i, task in enumerate(self.tasks_by_date[date_str]):
                if (task.get('title') == task_data.get('title') and 
                    task.get('duration') == task_data.get('duration')):
                    self.remove_task(date_str, i)
                    break
        
        # Call the callback
        self.on_delete_task(task_data)
        
        # Auto-save (remove_task already handles this, but ensure it's saved)
        if self.settings.get('auto_save', True):
            self.root.after(1000, self._save_tasks)
        
        # Close dialog
        dialog.destroy()
    
    def _handle_delete_task(self):
        if self.selected_task: self.on_delete_task(self.selected_task.task_data)

    def _update_header(self):
        date_str = self.selected_date.strftime("%A, %B %d, %Y")
        self.header_label.configure(text=date_str)
    
    def _update_month_label(self):
        month_year = self.current_date.strftime("%B %Y")
        self.month_label.configure(text=month_year)
    
    def _refresh_tasks(self):
        for card in self.task_cards: card.destroy()
        self.task_cards.clear()
        self.selected_task = None
        
        if hasattr(self, 'edit_btn'): self.edit_btn.configure(state='disabled')
        if hasattr(self, 'delete_btn'): self.delete_btn.configure(state='disabled')
        
        date_key = self.selected_date.strftime("%Y-%m-%d")
        tasks = self.tasks_by_date.get(date_key, [])
        
        if hasattr(self, 'task_count_label'): self.task_count_label.configure(text=str(len(tasks)))
        
        if not tasks:
            empty_label = ctk.CTkLabel(self.tasks_scroll, text="هیچ وظیفه‌ای برنامه‌ریزی نشده\nبرای شروع روی 'افزودن وظیفه' کلیک کنید", font=ctk.CTkFont(family="Gulzar", size=15), text_color=self.colors['text_tertiary'], justify='center')
            empty_label.pack(expand=True, pady=40)
            self.task_cards.append(empty_label)
        else:
            sorted_tasks = sorted(tasks, key=lambda x: (x.get('completed', False), x.get('duration', 'Z')))
            for task in sorted_tasks:
                card = self._create_task_card(self.tasks_scroll, task)
                self.task_cards.append(card)
    
    def _create_task_card(self, parent, task_data):
        card = ctk.CTkFrame(parent, fg_color=self.colors['bg_hover'], corner_radius=16, border_width=2, border_color=self.colors['transparent'])
        card.pack(fill='x', pady=(0, 12))
        card.task_data = task_data
        
        content = ctk.CTkFrame(card, fg_color='transparent')
        content.pack(fill='both', expand=True, padx=18, pady=15)
        
        top_row = ctk.CTkFrame(content, fg_color='transparent')
        top_row.pack(fill='x', pady=(0, 8))
        
        checkbox_var = ctk.BooleanVar(value=task_data.get('completed', False))
        checkbox = ctk.CTkCheckBox(top_row, text="", width=24, height=24, corner_radius=6,
            fg_color=self.colors['success'], hover_color=self.colors['accent_primary'],
            variable=checkbox_var, command=lambda: self._on_task_toggle(card), checkmark_color='#FFFFFF'
        )
        checkbox.pack(side='left', padx=(0, 12))
        
        title = ctk.CTkLabel(top_row, text=task_data.get('title', 'Untitled Task'),
            font=ctk.CTkFont(family="Gulzar", size=16, weight="bold"),
            text_color=self.colors['text_secondary'] if checkbox_var.get() else self.colors['text_primary'], anchor='w'
        )
        title.pack(side='left', fill='x', expand=True)
        
        duration_text = task_data.get('duration', '')
        if duration_text:
            ctk.CTkLabel(content, text=f"⏱ {duration_text}",
                font=ctk.CTkFont(family="Gulzar", size=13),
                text_color=self.colors['text_secondary'], anchor='w'
            ).pack(fill='x', pady=(0, 8))
        
        tags_row = ctk.CTkFrame(content, fg_color='transparent')
        tags_row.pack(fill='x')
        
        if 'tags' in task_data and task_data['tags']:
            for tag in task_data['tags'][:3]:
                ctk.CTkLabel(tags_row, text=tag,
                    font=ctk.CTkFont(family="Gulzar", size=11, weight="bold"),
                    text_color='#FFFFFF', fg_color=self._get_tag_color(tag),
                    corner_radius=8, padx=10, pady=4
                ).pack(side='left', padx=(0, 6))
        
        card.bind('<Enter>', lambda e: self._on_card_hover(card, True))
        card.bind('<Leave>', lambda e: self._on_card_hover(card, False))
        card.bind('<Button-1>', lambda e: self._on_card_click(card, e))
        card.bind('<Double-Button-1>', lambda e: self._on_card_double_click(card, e))
        for w in card.winfo_children(): 
            w.bind('<Button-1>', lambda e: self._on_card_click(card, e))
            w.bind('<Double-Button-1>', lambda e: self._on_card_double_click(card, e))
        
        return card

    # Public API methods
    def set_tasks(self, tasks_dict: Dict[str, List[Dict]]):
        self.tasks_by_date = tasks_dict
        self._refresh_tasks()
        if self.current_view == "Month" and self.cal_grid_container:
            self._populate_calendar(self.cal_grid_container)
        elif self.current_view == "Week" and self.week_time_grid:
            self._populate_week_view(self.view_container)

    def add_task(self, date_str: str, task: Dict):
        if date_str not in self.tasks_by_date: self.tasks_by_date[date_str] = []
        self.tasks_by_date[date_str].append(task)
        self.set_tasks(self.tasks_by_date)
        # Auto-save
        if self.settings.get('auto_save', True):
            self.root.after(1000, self._save_tasks)  # Save after 1 second delay
    
    def update_task(self, date_str: str, task_index: int, updated_task: Dict):
        if date_str in self.tasks_by_date and task_index < len(self.tasks_by_date[date_str]):
            self.tasks_by_date[date_str][task_index] = updated_task
            self.set_tasks(self.tasks_by_date)
            # Auto-save
            if self.settings.get('auto_save', True):
                self.root.after(1000, self._save_tasks)  # Save after 1 second delay
    
    def remove_task(self, date_str: str, task_index: int):
        if date_str in self.tasks_by_date and task_index < len(self.tasks_by_date[date_str]):
            self.tasks_by_date[date_str].pop(task_index)
            self.set_tasks(self.tasks_by_date)
            # Auto-save
            if self.settings.get('auto_save', True):
                self.root.after(1000, self._save_tasks)  # Save after 1 second delay


# Demo/Testing
if __name__ == "__main__":
    from datetime import date
    
    # --- 1. Setup Sample Data ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    sample_tasks = {
        today_str: [
            {'title': 'Team Meeting', 'duration': '10:00 AM - 11:00 AM', 'tags': ['important', 'work'], 'completed': False, 'date_str': today_str},
            {'title': 'Finish Project Proposal', 'duration': '2:00 PM - 4:00 PM', 'tags': ['urgent'], 'completed': False, 'date_str': today_str},
            {'title': 'Lunch Break', 'duration': '12:00 PM - 1:00 PM', 'tags': ['low'], 'completed': False, 'date_str': today_str},
            {'title': 'Gym Session', 'duration': '6:00 PM - 7:00 PM', 'tags': ['personal'], 'completed': True, 'date_str': today_str}
        ],
        tomorrow_str: [
            {'title': 'Client Presentation', 'duration': '9:00 AM - 10:30 AM', 'tags': ['urgent', 'important'], 'completed': False, 'date_str': tomorrow_str}
        ]
    }
    
    # --- 2. Define Callback functions ---
    def find_task_index(date_str, task):
        if date_str in sample_tasks:
            for i, t in enumerate(sample_tasks[date_str]):
                if t['title'] == task['title'] and t.get('duration') == task.get('duration'):
                    return i
        return -1

    def on_add_task():
        new_task = {'title': f'Added Task @ {datetime.now().strftime("%H:%M")}', 'duration': '11:00 AM - 12:00 PM', 'tags': ['medium'], 'completed': False, 'date_str': ui.selected_date.strftime("%Y-%m-%d")}
        ui.add_task(ui.selected_date.strftime("%Y-%m-%d"), new_task)
    
    def on_edit_task(task):
        print(f"Edit task: {task['title']}")
    
    def on_delete_task(task):
        date_str = ui.selected_date.strftime("%Y-%m-%d")
        idx = find_task_index(date_str, task)
        if idx != -1: ui.remove_task(date_str, idx)
        
    def on_ai_schedule():
        print("AI Schedule clicked")
        
    def on_task_toggle(task):
        date_str = ui.selected_date.strftime("%Y-%m-%d")
        idx = find_task_index(date_str, task)
        if idx != -1: 
            task['completed'] = not task['completed']
            ui.update_task(date_str, idx, task)

    # --- 3. Create Root Window and UI Instance ---
    root = ctk.CTk()
    
    ui = PlannerUI(
        root=root,
        on_day_select=lambda d: print(f"Selected date: {d.strftime('%Y-%m-%d')}"),
        on_add_task=on_add_task,
        on_edit_task=on_edit_task,
        on_delete_task=on_delete_task,
        on_ai_schedule=on_ai_schedule,
        on_task_toggle=on_task_toggle
    )

    # --- 4. Load Sample Data and Initial State --- 
    ui.set_tasks(sample_tasks)
   
    # --- 5. Start the Application Event Loop ---
    root.mainloop() 
print("""
Kharazmi Project - AI-Powered Task Planner
Author: LittleFoxes (Enhanced with AI Integration)
Description: A task planner UI with offline AI assistant built with CustomTkinter
Features: Month, Week, Day Views, Task CRUD, 4 Visual Themes, and GPT4All Integration
""")
print("Application closed.") 
print("Kharazmi Project - AI-Powered Task Planner")
print("LittleFoxes © 2025 All Rights Reserved")
print("--------------------------------")