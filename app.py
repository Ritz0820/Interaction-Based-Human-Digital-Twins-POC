import urllib.parse
import os
import sqlite3
import json
import uuid
import io
from flask import Flask, request, send_file, jsonify
from openai import OpenAI
from transformers import pipeline

os.environ["TOKENIZERS_PARALLELISM"] = "false"

app = Flask(__name__)
client = OpenAI()

print("Loading Hugging Face model...")
uncertainty_classifier = pipeline(
    "text-classification", 
    model="distilbert-base-uncased-finetuned-sst-2-english"
)

DB_FILE = "interactions.db"

# Load the scenario script
def load_script():
    with open("strategies.json", "r", encoding="utf-8") as f:
        return json.load(f)

SCRIPT_DATA = load_script()

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Create table with ALL required columns explicitly included from the start
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                user_id TEXT,
                phase TEXT,
                elapsed_seconds REAL,
                user_text TEXT,
                response_latency REAL,
                uncertainty_detected INTEGER,
                knowledge INTEGER,
                engagement INTEGER,
                support_need INTEGER,
                confidence_expression INTEGER,
                strategy_id INTEGER,
                strategy_reason TEXT,
                tutor_reply TEXT
            )
        ''')
        
        # Post-experience survey table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS survey_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                user_id TEXT,
                overall_feeling TEXT,
                preferred_phase TEXT,
                felt_understood INTEGER,
                trust_and_engagement INTEGER
            )
        ''')
        conn.commit()

init_db()

def detect_uncertainty(text):
    if not text:
        return 0
    uncertain_keywords = ["maybe", "i think", "is it", "um", "uh", "not sure", "vielleicht", "glaube ich",]
    text_lower = text.lower()
    has_keyword = any(word in text_lower for word in uncertain_keywords)
    
    try:
        result = uncertainty_classifier(text)[0]
        hf_negative = (result['label'] == 'NEGATIVE')
    except Exception:
        hf_negative = False
        
    return 1 if (has_keyword or hf_negative) else 0

def is_stuck_or_english(text):
    if not text:
        return False

    text_lower = text.lower().strip()

    stuck_phrases = [
        "i don't understand",
        "i dont understand",
        "i do not understand",
        "don't understand",
        "dont understand",
        "what?",
        "what",
        "help",
        "i don't know",
        "i dont know",
        "not sure",
        "i'm not sure",
        "im not sure",
        "huh",
        "confused",
        "in english",
        "english"
    ]

    return any(
        phrase in text_lower
        for phrase in stuck_phrases
    )


def log_interaction(session_id, user_id, phase, elapsed_seconds, user_text, response_latency, uncertainty_detected, knowledge, engagement, support_need, confidence, strategy_id, strategy_reason, tutor_reply):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO interaction_logs 
            (session_id, user_id, phase, elapsed_seconds, user_text, response_latency, uncertainty_detected, knowledge, engagement, support_need, confidence_expression, strategy_id, strategy_reason, tutor_reply)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, user_id, phase, elapsed_seconds, user_text, response_latency, uncertainty_detected, knowledge, engagement, support_need, confidence, strategy_id, strategy_reason, tutor_reply))
        conn.commit()

@app.route('/turn', methods=['POST'])
def process_turn():
    data = request.json or {}
    
    # Session metadata from Unity
    session_id = data.get('session_id', str(uuid.uuid4()))
    user_id = data.get('user_id', 'anonymous_user')
    elapsed_seconds = float(data.get('elapsed_seconds', 0.0))
    
    # User text & latency
    user_text = data.get('user_text', '').strip()
    response_latency = float(data.get('response_latency', 0.0))
    conversation_turn = int(data.get("conversation_turn", 0))

    unity_knowledge = float(data.get('knowledge', 0.5)) * 100
    unity_confidence = float(data.get('confidence', 0.5)) * 100
    unity_engagement = float(data.get('engagement', 0.5)) * 100
    unity_support_need = float(data.get('hint_dependency', 0.5)) * 100

    # DYNAMIC STEP RESOLUTION:
    steps_dict = SCRIPT_DATA.get("steps", {})
    available_step_indices = [int(k) for k in steps_dict.keys() if k.isdigit()]
    max_step_index = max(available_step_indices) if available_step_indices else 0
    
    current_step_index = min(conversation_turn, max_step_index)
    step_data = steps_dict.get(str(current_step_index), {})

    # SMART AUTOMATIC PHASE TRACKING:
    if current_step_index >= 14:
        phase = "SURVEY"
    elif "directives" in step_data and step_data["directives"]:
        phase = "ADAPTIVE"
    else:
        phase = "CONTROL"

    uncertainty = detect_uncertainty(user_text)

    # CASE 1: Step 0 / User greets first, then Greta introduces herself
    if current_step_index == 0:
        talk_style = 1
        strategy_id_val = 1
        strategy_reason = "Scripted Step 0: User Greeting & Greta Introduction"
        hint_requested = False
        confidence_detected = "high"
        reason = "none"

        user_clean = user_text.lower().strip()
        if user_text == "":
            correct = False
            tutor_reply = "Welcome! Go ahead and say hello to begin your session with Greta."
        elif any(greeting in user_clean for greeting in ["hello", "hi", "hey", "hallo", "good morning", "guten tag"]):
            correct = True
            tutor_reply = "Hi there! I'm Greta, your guide for today. We are going through a two-part German roleplay story—Part A is a café visit, and Part B is a train station scenario. Let's set the scene for Part A: Imagine you have just walked into a cozy, busy café in the heart of Berlin. You walk up to the counter and make eye contact with the barista. Let's start with a friendly greeting. Type 'Hallo' to say hello."
        else:
            correct = False
            tutor_reply = "To start our session, please say hello by typing 'hello'."

    # CASE 2: Empty audio input on later steps (Mic timeout)
    elif current_step_index > 0 and user_text == "":
        tutor_reply = "Take your time! Whenever you are ready, just speak."
        talk_style = 2
        strategy_id_val = 3
        strategy_reason = "Empty input from user."
        correct = False
        hint_requested = False
        confidence_detected = "low"
        reason = "hesitation"
    
    # CASE 3: Standard Dialogue Evaluation & Adaptation
    else:
        directives = step_data.get("directives", {})
        target_phrase = step_data.get("target_phrase", "")

        if phase == "ADAPTIVE":
            step_name = step_data.get('step_name', f'Step {current_step_index}')
            
            eval_prompt = f"""
            You are evaluating a user response for STEP {current_step_index} ({step_name}) in a German Cafe script.
            Target Phrase / Intended Answer: "{target_phrase}"
            User Input: "{user_text}"
            Latency: {response_latency:.1f}s | Hesitation Detected: {bool(uncertainty)}

            Determine which outcome branch applies:
            - "on_success": User attempted German correctly for this step or answered logically.
            - "on_stuck_or_english": User said 'hello', answered purely in English, asked for help, or hesitated heavily.
            - "on_error": User tried German but made a clear grammar or vocabulary mistake.

            Return ONLY JSON:
            {{
                "branch": "on_success | on_stuck_or_english | on_error",
                "reason": "If on_error, write exactly 1 short sentence explaining what the mistake was. Otherwise leave empty.",
                "confidence_detected": "low | high"
            }}
            """
            if is_stuck_or_english(user_text):
                branch = "on_stuck_or_english"
                eval_reason = ""
                strategy_reason = "[ADAPTIVE] Stuck/English response detected"
                confidence_detected = "low"
            else:
                try:
                    eval_res = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "system", "content": eval_prompt}],
                        response_format={"type": "json_object"},
                        max_tokens=80
                    )
                    raw_eval_content = eval_res.choices[0].message.content.strip()
                    eval_json = json.loads(raw_eval_content)
                    
                    branch = eval_json.get(
                        "branch",
                        "on_stuck_or_english"
                    )
                    eval_reason = eval_json.get("reason", "")
                    strategy_reason = (
                        f"[ADAPTIVE] "
                        f"{eval_reason if eval_reason else 'Evaluated against step script'}"
                    )
                    confidence_detected = eval_json.get(
                        "confidence_detected",
                        "high"
                    )
                except Exception:
                    branch = "on_stuck_or_english"
                    eval_reason = ""
                    strategy_reason = "[ADAPTIVE] Classification fallback"
                    confidence_detected = "low"

            
          

            default_directive = {"talk_style": 2, "tutor_reply": "Let's try that again."}
            selected_directive = directives.get(branch, directives.get("on_stuck_or_english", default_directive))
            talk_style = selected_directive.get("talk_style", 2)
            base_tutor_reply = selected_directive.get("tutor_reply", "Could you try saying that one more time?")
            
            if branch == "on_error" and eval_reason:
                tutor_reply = f"{eval_reason} {base_tutor_reply}"
            else:
                tutor_reply = base_tutor_reply
            
            branch_strategy_map = {"on_success": 2, "on_stuck_or_english": 3, "on_error": 4}
            strategy_id_val = branch_strategy_map.get(branch, 2)
            
            correct = (branch == "on_success")
            hint_requested = (branch == "on_stuck_or_english")
            reason = "none" if correct else ("hesitation" if hint_requested else "grammar")

        else:
            # CONTROL PHASE (Part B): NON-HDT / No Learner State logic
            user_clean = user_text.lower().replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
            target_clean = target_phrase.lower().replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
            
            if target_clean and (target_clean in user_clean or user_clean in target_clean):
                correct = True
                tutor_reply = step_data.get("control_reply", "Correct. Moving forward.")
                strategy_reason = "[CONTROL] Exact or fuzzy string match successful."
            else:
                correct = False
                tutor_reply = step_data.get("control_reply", f"Please type exactly: '{target_phrase}'")
                strategy_reason = "[CONTROL] String match failed."

            talk_style = 2 
            strategy_id_val = 0
            hint_requested = False
            confidence_detected = "neutral"
            reason = "none" if correct else "grammar"

    # Log interaction to SQLite
    log_interaction(
        session_id=session_id,
        user_id=user_id,
        phase=phase,
        elapsed_seconds=elapsed_seconds,
        user_text=user_text,
        response_latency=response_latency,
        uncertainty_detected=uncertainty,
        knowledge=int(unity_knowledge),
        engagement=int(unity_engagement),
        support_need=int(unity_support_need),
        confidence=int(unity_confidence),
        strategy_id=int(strategy_id_val),
        strategy_reason=strategy_reason,
        tutor_reply=tutor_reply
    )

    # Generate TTS Audio Stream
    tts_response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=tutor_reply
    )

    audio_stream = io.BytesIO(tts_response.content)
    audio_stream.seek(0)

    safe_reply = tutor_reply.replace('\n', ' ').replace('\r', '').replace('—', '-').replace('é', 'e').replace('’', "'")

    response = send_file(audio_stream, mimetype="audio/mpeg", download_name="response.mp3")
    response.headers['X-Tutor-Reply'] = urllib.parse.quote(safe_reply)
    response.headers['X-Phase'] = phase
    response.headers['X-Correct'] = str(correct).lower()
    response.headers['X-HintRequested'] = str(hint_requested).lower()
    response.headers['X-ConfidenceDetected'] = confidence_detected
    response.headers['X-Reason'] = reason
    response.headers['X-Strategy-ID'] = str(strategy_id_val)
    response.headers['X-Talk-Style'] = str(talk_style)

    return response

@app.route('/survey', methods=['POST'])
def submit_survey():
    data = request.json or {}
    session_id = data.get('session_id', 'unknown')
    user_id = data.get('user_id', 'anonymous')
    overall_feeling = data.get('overall_feeling', '')
    preferred_phase = data.get('preferred_phase', '') 
    felt_understood = int(data.get('felt_understood', 3)) 
    trust_and_engagement = int(data.get('trust_and_engagement', 3)) 

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO survey_responses 
            (session_id, user_id, overall_feeling, preferred_phase, felt_understood, trust_and_engagement)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, user_id, overall_feeling, preferred_phase, felt_understood, trust_and_engagement))
        conn.commit()

    return jsonify({"status": "success", "message": "Survey recorded successfully."}), 200

if __name__ == '__main__':
    print("Starting Script-Driven Backend on http://127.0.0.1:5001")
    app.run(host='127.0.0.1', port=5001, debug=True, use_reloader=False)