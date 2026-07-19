import time
import requests
import threading
import sys
import json
import queue
import subprocess
import os

# ================= CONFIG =================
OLLAMA_MODEL = "phi3:3.8b"
OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = """
You are a helpful AI advisor. Respond concisely and thoughtfully.
"""

# ================= UNIVERSAL TTS FIX =================
class UniversalTTS:
    """Universal TTS that works with multiple backends"""
    
    def __init__(self):
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.available_engines = []
        self.current_engine = None
        self._detect_engines()
        self._start_worker()
        
    def _detect_engines(self):
        """Detect available TTS engines"""
        self.available_engines = []
        
        # Try pyttsx3 first
        try:
            import pyttsx3
            self.available_engines.append(('pyttsx3', self._speak_pyttsx3))
            print("🔊 Detected: pyttsx3")
        except:
            pass
            
        # Try Windows SAPI
        try:
            import win32com.client
            self.available_engines.append(('sapi', self._speak_sapi))
            print("🔊 Detected: Windows SAPI")
        except:
            pass
            
        # Try platform-specific
        try:
            if os.name == 'nt':  # Windows
                self.available_engines.append(('windows_cmd', self._speak_windows))
                print("🔊 Detected: Windows built-in")
        except:
            pass
            
        if not self.available_engines:
            print("⚠️ No TTS engines found! Text will display only.")
            self.available_engines.append(('dummy', self._speak_dummy))
    
    def _start_worker(self):
        """Start the TTS worker thread"""
        def worker():
            while not self.stop_event.is_set():
                try:
                    text = self.speech_queue.get(timeout=0.5)
                    if text is None:  # Shutdown signal
                        break
                        
                    self.is_speaking = True
                    
                    # Try all available engines until one works
                    success = False
                    for engine_name, engine_func in self.available_engines:
                        if success:
                            break
                        try:
                            engine_func(text)
                            success = True
                            break
                        except Exception as e:
                            continue
                    
                    if not success:
                        print(f"🤖 (Text only): {text[:80]}...")
                    
                    self.is_speaking = False
                    self.speech_queue.task_done()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    self.is_speaking = False
        
        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()
    
    # === TTS Engine Implementations ===
    
    def _speak_pyttsx3(self, text):
        """Use pyttsx3 with proper lifecycle management"""
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', 190)
        engine.setProperty('volume', 0.9)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    
    def _speak_sapi(self, text):
        """Use Windows SAPI"""
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = 1
        speaker.Volume = 100
        speaker.Speak(text)
    
    def _speak_windows(self, text):
        """Use Windows built-in TTS"""
        # Clean text for PowerShell
        clean_text = text.replace('"', '').replace("'", "").replace("`", "")
        ps_command = f'$speak = New-Object -ComObject SAPI.SpVoice; $speak.Speak("{clean_text}")'
        subprocess.run(["powershell", "-Command", ps_command], capture_output=True, shell=True)
    
    def _speak_dummy(self, text):
        """Dummy engine when no TTS is available"""
        print(f"🔇 [TTS Disabled]: {text[:100]}...")
    
    def speak(self, text):
        """Add text to speech queue"""
        if text and text.strip():
            self.speech_queue.put(text[:500])  # Limit length for safety
    
    def wait_for_completion(self, timeout=30):
        """Wait for all speech to complete"""
        try:
            self.speech_queue.join()
        except:
            pass
    
    def shutdown(self):
        """Clean shutdown"""
        self.stop_event.set()
        self.speech_queue.put(None)  # Signal shutdown
        if self.worker_thread:
            self.worker_thread.join(timeout=2)

# Initialize TTS
tts = UniversalTTS()

# ================= ENHANCED ANIMATIONS =================
class Animations:
    def __init__(self):
        self.colors = {
            "user": "\033[92m",      # Green
            "ai": "\033[96m",        # Cyan
            "system": "\033[93m",    # Yellow
            "error": "\033[91m",     # Red
            "warning": "\033[95m",   # Magenta
            "info": "\033[94m",      # Blue
            "reset": "\033[0m",
            "gray": "\033[90m",
            "bold": "\033[1m"
        }
    
    def print_color(self, text, color_type="info", end="\n"):
        """Print colored text with optional end parameter"""
        color = self.colors.get(color_type, self.colors["info"])
        print(f"{color}{text}{self.colors['reset']}", end=end)
        sys.stdout.flush()
    
    def animate_loading(self, duration=0.5, message="Thinking"):
        """Animated loading spinner - SHORTENED"""
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴"]
        end_time = time.time() + duration
        
        i = 0
        sys.stdout.write(f"\r{message} ")
        while time.time() < end_time:
            frame = frames[i % len(frames)]
            sys.stdout.write(f"\r{message} {frame}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
        sys.stdout.write(f"\r{message} ✓\n")
    
    def progress_rainbow(self, duration=0.8):
        """Rainbow progress bar - SHORTENED"""
        width = 30
        colors = [91, 93, 92, 96, 94, 95]
        
        for i in range(width + 1):
            progress = i / width
            color_idx = int(progress * (len(colors) - 1))
            color_code = colors[color_idx]
            
            bar = "█" * i + "░" * (width - i)
            percent = int(progress * 100)
            
            sys.stdout.write(f"\r\033[{color_code}m[{bar}] {percent}%\033[0m")
            sys.stdout.flush()
            time.sleep(duration / width)
        print()
    
    def typewriter_effect(self, text, speed=0.03, color="ai", end="\n"):
        """Typewriter effect with colors"""
        color_code = self.colors.get(color, self.colors["ai"])
        
        for i, char in enumerate(text):
            sys.stdout.write(f"{color_code}{char}{self.colors['reset']}")
            sys.stdout.flush()
            
            # Vary speed for natural typing
            if char in ".,!?;:":
                time.sleep(speed * 2)
            elif char == " ":
                time.sleep(speed * 0.3)
            else:
                time.sleep(speed)
        
        print(end, end="")
    
    def shimmer_text(self, text):
        """Make text shimmer"""
        result = ""
        for i, char in enumerate(text):
            if char != " ":
                # Cycle through colors
                color_seq = [96, 92, 93, 95, 94][i % 5]
                result += f"\033[{color_seq}m{char}\033[0m"
            else:
                result += " "
        return result
    
    def pulse_effect(self, text, pulses=2):
        """Pulse effect for important messages - SHORTENED"""
        for i in range(pulses):
            for brightness in [100, 200, 255, 200, 100]:
                sys.stdout.write(f"\r\033[38;2;{brightness};{brightness};{brightness}m{text}\033[0m")
                sys.stdout.flush()
                time.sleep(0.03)
        print()
    
    def quick_fireworks(self):
        """Quick fireworks animation"""
        print("\033[92m     .\033[0m")
        print("\033[93m    .*.\033[0m")
        print("\033[94m   .*.*.\033[0m")
        print("\033[95m  .*.*.*.\033[0m")
        print("\033[96m   .*.*.\033[0m")
        print("\033[92m    .*.\033[0m")
        print("\033[93m     .\033[0m")
        time.sleep(0.3)
        print("\033[1A" * 7)  # Move cursor up 7 lines
        print(" " * 20)  # Clear line
    
    def startup_sequence(self):
        """Quick startup sequence"""
        self.print_color("\n" + "="*50, "system")
        
        # Simple ASCII art
        logo = """
        ╔═══════════════════════════╗
        ║   🤖 AI ASSISTANT 3000   ║
        ╚═══════════════════════════╝
        """
        self.print_color(logo, "ai")
        self.print_color("="*50, "system")
        
        # Quick initialization
        self.animate_loading(0.3, "Initializing")
        self.animate_loading(0.3, "Loading AI")
        self.animate_loading(0.3, "Ready")
        
        self.print_color("\n🌟 SYSTEM READY - Type your messages 🌟", "system")
        self.print_color("Type 'stop' to exit\n", "warning")

# ================= AI FUNCTIONS =================
def ask_ai_with_effects(text, anim):
    """Get AI response with animations"""
    prompt = SYSTEM_PROMPT + "\nUser: " + text + "\nAdvisor:"
    
    # Quick thinking animation
    anim.animate_loading(0.4, "💭 Thinking")
    
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 2048,
                    "temperature": 0.4,
                    "num_predict": 120
                }
            },
            timeout=15
        )

        data = response.json()
        if "response" not in data:
            return anim.shimmer_text("⚠️ Response format error")
        
        return data["response"].strip()
        
    except requests.exceptions.Timeout:
        return anim.shimmer_text("⏳ Response timeout")
    except requests.exceptions.ConnectionError:
        return anim.shimmer_text("🔌 Connection failed")
    except Exception as e:
        return anim.shimmer_text(f"⚠️ Error")

# ================= MAIN LOOP =================
def main():
    # Initialize animations
    anim = Animations()
    anim.startup_sequence()
    
    # Track conversation
    message_count = 0
    
    while True:
        message_count += 1
        
        # Get user input
        anim.print_color(f"\n📝 Message #{message_count}", "info")
        anim.print_color("➤ Type your message: ", "info", end="")
        
        try:
            user_text = input().strip()
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        
        if not user_text:
            anim.print_color("⚠️ Please enter a message", "warning")
            continue
        
        # Check for exit
        if user_text.lower() in ['stop', 'exit', 'quit', 'bye']:
            anim.print_color("\n🎇 Thanks for chatting! Goodbye! 🎇", "system")
            anim.quick_fireworks()
            break
        
        # Display user message
        anim.print_color(f"\n👤 YOU: ", "user", end="")
        anim.typewriter_effect(user_text, speed=0.02, color="user")
        
        # Get AI response
        ai_reply = ask_ai_with_effects(user_text, anim)
        
        # Display AI response
        anim.print_color(f"\n🤖 AI: ", "ai", end="")
        
        # Start typing animation in background
        def typing_animation():
            anim.typewriter_effect(ai_reply, speed=0.03, color="ai")
        
        typing_thread = threading.Thread(target=typing_animation, daemon=True)
        typing_thread.start()
        
        # Start TTS in parallel
        tts.speak(ai_reply)
        
        # Wait for typing to finish
        typing_thread.join(timeout=10)
        
        # Add response separator
        anim.print_color("\n" + "─" * 40, "gray")
        
        # Small pause
        time.sleep(0.2)

# ================= CLEANUP =================
def cleanup():
    """Clean shutdown"""
    print("\n")
    anim = Animations()
    anim.animate_loading(0.5, "🔄 Saving session")
    
    # Wait for any remaining TTS
    tts.wait_for_completion(timeout=1)
    tts.shutdown()
    
    anim.print_color("✅ Session ended", "system")

# ================= ENTRY POINT =================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Session interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        cleanup()