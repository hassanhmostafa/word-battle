import os
import requests
import uuid
import json
import random
import logging
import sqlite3
from flask import g, Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from typing import List, Dict, Any, Tuple, Optional
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger.info("Starting application")
load_dotenv()

from utils import *
from ai import *

app = Flask(__name__)
CORS(app)

# ============================================================================
# DATABASE SETUP
# ============================================================================

DEFAULT_DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'word_battle.db')
DATABASE = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)


def ensure_database_ready():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.row_factory = sqlite3.Row
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        ensure_database_ready()

@app.cli.command('init-db')
def init_db_command():
    init_db()
    print('Initialized the database.')

# ============================================================================
# LOAD WORD DATA
# ============================================================================

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "all_words.json"), "r", encoding="utf-8") as fh:
    WORD_DATA = json.load(fh)

# ============================================================================
# SETTINGS — REFEREE PROMPT
# ============================================================================

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
REFEREE_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "referee_prompt.txt")
app.secret_key = os.getenv("SECRET_KEY", "fallback-dev-secret-key-change-me")

@app.get("/settings/referee-prompt")
def get_referee_prompt():
    """Return the current editable referee prompt body."""
    try:
        with open(REFEREE_PROMPT_FILE, "r", encoding="utf-8") as f:
            return jsonify({"prompt": f.read()})
    except FileNotFoundError:
        return jsonify({"prompt": ""}), 200

@app.post("/settings/referee-prompt")
def set_referee_prompt():
    """Update the referee prompt body. Requires admin password from .env (ADMIN_PASSWORD)."""
    data = request.get_json(force=True) or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    new_prompt = data.get("prompt", "")
    if not new_prompt.strip():
        return jsonify({"error": "Prompt cannot be empty"}), 400
    with open(REFEREE_PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(new_prompt)
    logger.info("Referee prompt updated via /settings/referee-prompt")
    return jsonify({"ok": True, "message": "Referee prompt updated successfully."})

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/")
def index():
    return jsonify({
        "status": "running",
        "ai_provider": AI_PROVIDER,
        "model": GPT_MINI_MODEL
    })

@app.post("/start")
def start_game():
    """
    Start a new round with AI describing.
    
    ✅ FIXED:
    - Handles new_game flag to create fresh game
    - Uses get_or_create_round to handle "Change Word" without UNIQUE errors
    - Always starts new games at easy difficulty
    """
    data = request.get_json(force=True) or {}
    category = data.get("category", "animal")
    participant_id = data.get("participant_id")
    username = data.get("username")
    new_game = data.get("new_game", False)

    db = get_db()

    # Get or create user
    user = None
    if participant_id:
        user = db.execute('SELECT * FROM Users WHERE participant_id = ?', (participant_id,)).fetchone()
    
    if user is None:
        new_participant_id = str(uuid.uuid4())
        db.execute(
            'INSERT INTO Users (participant_id, username) VALUES (?, ?)', 
            (new_participant_id, username)
        )
        db.commit()
        user = db.execute('SELECT * FROM Users WHERE participant_id = ?', (new_participant_id,)).fetchone()
        logger.info(f"Created new user: {user['user_id']} with username '{username}'")
    else:
        if username and username != user['username']:
            logger.info(f"User {user['user_id']} updating username from '{user['username']}' to '{username}'")
            db.execute('UPDATE Users SET username = ? WHERE user_id = ?', (username, user['user_id']))
            db.commit()
            user = db.execute('SELECT * FROM Users WHERE participant_id = ?', (participant_id,)).fetchone()

    game_id = get_or_create_game(db, user['user_id'], user['username'], "easy1", new_game=new_game)
    round_number = get_next_round_number(db, game_id)
    
    current_difficulty = get_current_difficulty(db, game_id)
    
    logger.info(f"Game {game_id}, Round {round_number}/12, Difficulty: {current_difficulty}, new_game={new_game}")

    secret_word = select_word_for_round(db, game_id, category, current_difficulty, WORD_DATA)
    
    if not secret_word:
        return jsonify({"error": "No words available for this combination"}), 400
    
    # Generate AI description
    prompt = forbidden_words_prompt(secret_word, category)
    forbidden_words = json.loads(llm_complete(prompt, temperature=0.7, max_tokens=50) or "[]")
    print(f"Generated forbidden words for '{secret_word}': {forbidden_words}")
    prompt = f"""You are a word game master. Describe this word so a player can guess it.

SECRET WORD: {secret_word}
CATEGORY: {category}
FORBIDDEN WORDS: {', '.join(forbidden_words)}
Rules:
1. Start directly with the description itself. Do not add any intro sentence or preamble.
2. Write 3-4 simple sentences (~50 words total)
3. DO NOT use the word "{secret_word}" or any part of it
4. DO NOT use direct synonyms
5. Give helpful clues but don't make it too obvious
6. Use simple vocabulary (B1 English level)
7. Be informative and slightly playful
8. Do not use the forbidden words (if any)

Generate the description now:""".strip()

    description = llm_complete(prompt, temperature=0.7, max_tokens=100)

    # Referee check
    ok, violations = referee_check_description(
        description,
        actor="ai",
        secret_word=secret_word,
        category=category,
        difficulty=current_difficulty,
        llm_complete_func=llm_complete
    )

    round_id = get_or_create_round(
        db, game_id, round_number, secret_word, category, current_difficulty, 'user_guesses'
    )

    cursor = db.execute(
        'INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content) VALUES (?, ?, ?, ?, ?)',
        (round_id, 1, 'ai', 'description', description)
    )
    action_id = cursor.lastrowid
    db.commit()

    db.execute(
        'INSERT INTO Referee_Checks (round_id, action_id, check_type, text_checked, secret_word, is_valid, violation_type, violation_details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (round_id, action_id, 'description', description, secret_word, ok, 
         None if ok else (violations[0]['code'] if violations else 'UNKNOWN'),
         None if ok else json.dumps(violations))
    )
    db.commit()

    return jsonify({
        "description": description,
        "answer": secret_word,
        "referee_ok": ok,
        "violations": violations,
        "round_id": round_id,
        "game_id": game_id,
        "round_number": round_number,
        "current_difficulty": current_difficulty,
        "participant_id": user['participant_id'],
        "username": user['username'],
        "ai_provider": AI_PROVIDER
    })


@app.post("/get-forbidden-words")
def get_forbidden_words():
    data = request.get_json(force=True) or {}
    secret_word = data.get("word", "")
    category = data.get("category", "")
    round_id = data.get("round_id")

    if not secret_word:
        return jsonify({"error": "No word provided"}), 400

    prompt = forbidden_words_prompt(secret_word, category)

    try:
        response = llm_complete(prompt, temperature=0.7, max_tokens=50)

        # Clean response
        response = (response or "").strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        forbidden_words = json.loads(response)

        if not isinstance(forbidden_words, list) or len(forbidden_words) != 5:
            logger.warning(f"Invalid forbidden words: {response}")
            forbidden_words = []

        forbidden_words = [str(w).lower() for w in forbidden_words]
        logger.info(f"Generated forbidden words for '{secret_word}': {forbidden_words}")

        if round_id:
            db = get_db()

            round_data = db.execute(
                "SELECT round_id FROM Rounds WHERE round_id = ?",
                (round_id,)
            ).fetchone()
            if not round_data:
                return jsonify({"error": "Invalid round_id"}), 404

            action_number = next_action_number(db, round_id)
            cursor = db.execute(
                "INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content) VALUES (?, ?, ?, ?, ?)",
                (round_id, action_number, "ai", "forbidden_words", json.dumps(forbidden_words))
            )
            action_id = cursor.lastrowid
            db.commit()

        return jsonify({
            "forbidden_words": forbidden_words,
            "word": secret_word
        })

    except Exception as e:
        logger.error(f"Error generating forbidden words: {e}")
        return jsonify({"error": "Failed to generate forbidden words"}), 500



@app.post("/validate-description")
def validate_description():
    """
    Phase 1: Validate the user's description via the referee.
    Returns 200 {valid: true} if approved, or 400 {violations: [...]} if rejected.
    This is intentionally separate from /guess so the frontend can start the AI
    timer only AFTER approval, excluding referee latency from the AI's clock.
    """
    data = request.get_json(force=True) or {}
    user_description = data.get("description", "")
    secret_word = data.get("secret_word")
    category = data.get("category")
    difficulty = data.get("difficulty", "medium")
    forbidden_words = data.get("forbidden_words", [])
    round_id = data.get("round_id")
    duration_ms = data.get("duration_ms")
    if not round_id:
        return jsonify({"error": "round_id is required"}), 400
    db = get_db()
    # Log user submission
    user_action_number = next_action_number(db, round_id)
    cursor = db.execute(
        'INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content, duration_ms) VALUES (?, ?, ?, ?, ?, ?)',
        (round_id, user_action_number, 'user', 'description', user_description, duration_ms)
    )
    action_id = cursor.lastrowid
    db.commit()
    print("Running referee check on description...")
    ok, violations = referee_check_description(
        user_description,
        actor="user",
        secret_word=secret_word,
        category=category,
        difficulty=difficulty,
        llm_complete_func=llm_complete,
        forbidden_words=forbidden_words
    )
    db.execute(
        'INSERT INTO Referee_Checks (round_id, action_id, check_type, text_checked, secret_word, is_valid, violation_type, violation_details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (round_id, action_id, 'description', user_description, secret_word, ok,
         None if ok else (violations[0]['code'] if violations else 'UNKNOWN'),
         None if ok else json.dumps(violations))
    )
    db.commit()
    if not ok:
        print(f"Referee rejected description for round {round_id}.")
        return jsonify({"error": "Your description violates the rules.", "violations": violations}), 400
    print(f"Referee approved description for round {round_id}.")
    return jsonify({"valid": True})


@app.post("/guess")
def ask_llm_to_guess():
    """
    User describes, AI guesses.

    ✅ FIXED: Skips re-validating the description if it was already approved.
    ✅ FIXED: Validates the HINT separately for rule violations and forbidden words.
    ✅ NEW:   AI returns a confidence score (0.0–1.0) which drives a dynamic
              thinking delay — low confidence = longer wait, high = shorter.
    """
    data = request.get_json(force=True) or {}
    user_description = data.get("description", "")
    secret_word = data.get("secret_word")
    category = data.get("category")
    difficulty = data.get("difficulty", "medium")
    forbidden_words = data.get("forbidden_words", [])
    round_id = data.get("round_id")
    duration_ms = data.get("duration_ms")
    ai_thinking_ms = data.get("ai_thinking_ms")
    description_approved = data.get("description_approved", False)

    if not round_id:
        return jsonify({"error": "round_id is required"}), 400

    db = get_db()

    # ── Log user submission (description or hint) ──
    user_action_number = next_action_number(db, round_id)
    cursor = db.execute(
        'INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content, duration_ms) VALUES (?, ?, ?, ?, ?, ?)',
        (round_id, user_action_number, 'user', 'description', user_description, duration_ms)
    )
    action_id = cursor.lastrowid
    db.commit()

    # ── Conditional Validation Logic ──
    if not description_approved:
        print("🕵️‍♂️ Description not yet approved. Running full referee check...")
        ok, violations = referee_check_description(
            user_description,
            actor="user",
            secret_word=secret_word,
            category=category,
            difficulty=difficulty,
            llm_complete_func=llm_complete,
            forbidden_words=forbidden_words
        )
        db.execute(
            'INSERT INTO Referee_Checks (round_id, action_id, check_type, text_checked, secret_word, is_valid, violation_type, violation_details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (round_id, action_id, 'description', user_description, secret_word, ok,
             None if ok else (violations[0]['code'] if violations else 'UNKNOWN'),
             None if ok else json.dumps(violations))
        )
        db.commit()

        if not ok:
            print(f"❌ Referee rejected description for round {round_id}.")
            return jsonify({
                "error": "Your description violates the rules.",
                "violations": violations
            }), 400
        else:
            print(f"✅ Referee approved description for round {round_id}.")

    else:
        # Description already approved — only validate the HINT part if present
        print("🕵️‍♂️ Description previously approved. Checking for hint...")
        from utils import _split_desc_hint, _is_obviously_generic_text
        desc_part, hint_part = _split_desc_hint(user_description)
        if hint_part:
            print(f"💡 Hint found: {hint_part}. Validating hint...")
            # 1) Reject clearly generic hints deterministically
            if _is_obviously_generic_text(hint_part):
                violations = [{
                    "code": "MEANINGLESS",
                    "message": f'Hint is too generic or vague: "{hint_part}". Add at least one new concrete detail.',
                    "severity": "high"
                }]
                print(f"❌ Hint is generic: {violations}")
                return jsonify({
                    "error": "Your hint violates the rules.",
                    "violations": violations
                }), 400
            # 2) WORD_LEAK check on the hint (secret word / morphological variants)
            hint_ok, hint_violations = rule_based_referee_check(hint_part, secret_word)
            if not hint_ok:
                print(f"❌ Hint contains word leak: {hint_violations}")
                return jsonify({
                    "error": "Your hint violates the rules.",
                    "violations": hint_violations
                }), 400
            # 3) Forbidden words check (allow 1)
            if forbidden_words:
                violated, found = check_forbidden_words(hint_part, forbidden_words, max_words=1)
                if violated:
                    print(f"❌ Hint uses too many forbidden words: {found}")
                    return jsonify({
                        "error": "Your hint uses too many forbidden words.",
                        "violations": [{"code": "FORBIDDEN_WORD_USED", "message": f"Hint uses too many forbidden words: {found}", "severity": "high"}]
                    }), 400
            print("✅ Hint passed validation.")

    # ── Ask AI to guess with confidence score ──
    ai_guess_started_at = time.perf_counter()
    prompt = f"""You are playing a word guessing game. Based on this description, guess the secret word.

DESCRIPTION: {user_description}
CATEGORY: {category}

Think carefully like a human would. Consider all the clues before deciding.

Return ONLY this JSON (no extra text):
<json>{{"guess": "yourguess", "confidence": 0.85, "reasoning": "one short sentence explaining why"}}</json>

- "guess": a single word (your best guess)
- "confidence": float from 0.0 (very unsure) to 1.0 (completely certain)
- "reasoning": one sentence max""".strip()

    raw = llm_complete_fastest(prompt, temperature=0.3, max_tokens=150)
    
    from utils import _extract_json
    parsed = _extract_json(raw)
    if parsed and "guess" in parsed:
        guess = str(parsed.get("guess", "")).strip().lower()
        confidence = float(parsed.get("confidence", 0.5))
        reasoning = str(parsed.get("reasoning", "")).strip()
    else:
        guess = (raw or "").strip().split()[0] if (raw or "").strip() else ""
        confidence = 0.5
        reasoning = ""
        print(f"⚠️ Could not parse structured AI response. Raw: {raw!r}. Falling back to: {guess!r}")

    print(f"🤖 AI guess: '{guess}' | Confidence: {confidence:.2f} | Reasoning: {reasoning}")

    # ── Dynamic thinking delay based on AI's own confidence ──
    MIN_DELAY = 1.0
    MAX_DELAY = 30.0
    think_seconds = MIN_DELAY + (1.0 - confidence) * (MAX_DELAY - MIN_DELAY)
    think_seconds += random.uniform(-0.5, 0.5)
    think_seconds = max(MIN_DELAY, think_seconds)

    print(f"⏳ AI thinking delay: {think_seconds:.1f}s (confidence={confidence:.2f})")
    time.sleep(think_seconds)

    ai_thinking_ms = int((time.perf_counter() - ai_guess_started_at) * 1000)

    # ── Log AI guess action ──
    ai_action_number = next_action_number(db, round_id)
    cursor = db.execute(
        'INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content, duration_ms) VALUES (?, ?, ?, ?, ?, ?)',
        (round_id, ai_action_number, 'ai', 'guess', guess, ai_thinking_ms)
    )
    ai_action_id = cursor.lastrowid
    db.commit()

    # ── Check if guess is correct ──
    is_correct = words_are_equivalent(guess, secret_word, llm_complete)

    if is_correct:
        db.execute(
            'UPDATE Rounds SET outcome = ?, ended_at = CURRENT_TIMESTAMP WHERE round_id = ?',
            ('win', round_id)
        )
        db.commit()

    return jsonify({
        "guess": guess,
        "is_correct": is_correct,
        "confidence": confidence,
        "reasoning": reasoning
    })


@app.post("/generate-description")
def generate_description():
    """
    Called when the user submits 3 violated descriptions in a row.
    The AI generates a valid description for the current word so the round can continue.
    """
    try:
        data = request.get_json(force=True) or {}
        round_id = data.get("round_id")
        forbidden_words = data.get("forbidden_words", [])

        if not round_id:
            return jsonify({"error": "round_id is required"}), 400

        db = get_db()

        round_data = db.execute(
            "SELECT secret_word, category, difficulty FROM Rounds WHERE round_id = ?",
            (round_id,)
        ).fetchone()

        if not round_data:
            return jsonify({"error": "Invalid round_id"}), 404

        secret_word = round_data["secret_word"]
        category = round_data["category"]

        logger.info(f"Generating AI description override for round {round_id}, word '{secret_word}', forbidden: {forbidden_words}")

        if not isinstance(forbidden_words, list):
            forbidden_words = []
        forbidden_words = [str(w).lower() for w in forbidden_words]

        forbidden_str = ', '.join(forbidden_words) if forbidden_words else 'none'

        prompt = f"""You are a word game master. Describe this word so a player can guess it.

SECRET WORD: {secret_word}
CATEGORY: {category}
FORBIDDEN WORDS: {forbidden_str}

Rules:
1. Start directly with the description itself. Do not add any intro sentence or preamble.
2. Write 3-4 simple sentences (~50 words total)
3. DO NOT use the word "{secret_word}" or any part of it
4. DO NOT use direct synonyms
5. Give helpful clues but don't make it too obvious
6. Use simple vocabulary (B1 English level)
7. Be informative and slightly playful
8. Do not use any of the forbidden words listed above

Generate the description now:""".strip()

        description = llm_complete(prompt, temperature=0.7, max_tokens=100)

        if not description:
            logger.error(f"llm_complete returned empty for generate-description, round {round_id}")
            return jsonify({"error": "AI failed to generate a description. Please try again."}), 500

        description = description.strip()

        action_number = next_action_number(db, round_id)
        cursor = db.execute(
            "INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content) VALUES (?, ?, ?, ?, ?)",
            (round_id, action_number, "ai", "description_override", description)
        )
        action_id = cursor.lastrowid
        db.commit()

        db.execute(
            "INSERT INTO Referee_Checks (round_id, action_id, check_type, text_checked, secret_word, is_valid, violation_type, violation_details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (round_id, action_id, "description", description, secret_word, True, None, None)
        )
        db.commit()

        logger.info(f"✅ AI description override generated for round {round_id}: '{description[:60]}...'")

        return jsonify({"description": description})

    except Exception as e:
        logger.error(f"❌ /generate-description failed: {e}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.post("/check-guess")
def check_guess():
    """Check if user's guess is correct."""
    data = request.get_json(force=True) or {}
    round_id = data.get("round_id")
    guess = (data.get("guess") or "").strip()
    duration_ms = data.get("duration_ms")

    if not round_id or not guess:
        return jsonify({"error": "round_id and guess are required"}), 400

    db = get_db()
    round_data = db.execute(
        "SELECT secret_word FROM Rounds WHERE round_id = ?",
        (round_id,)
    ).fetchone()

    if not round_data:
        return jsonify({"error": "Invalid round_id"}), 404

    answer = round_data["secret_word"]
    is_correct = words_are_equivalent(guess, answer, llm_complete)

    action_number = next_action_number(db, round_id)
    db.execute(
        'INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content, duration_ms) VALUES (?, ?, ?, ?, ?, ?)',
        (round_id, action_number, 'user', 'guess', guess, duration_ms)
    )
    db.commit()

    return jsonify({"is_correct": bool(is_correct)})



@app.post("/get-word")
def get_word():
    """
    Get a word for the user to describe (AI will guess).
    """
    data = request.get_json(force=True) or {}
    category = data.get("category", "animal")
    difficulty = data.get("difficulty", "easy")
    participant_id = data.get("participant_id")
    username = data.get("username")
    new_game = data.get("new_game", False)

    db = get_db()

    user = None
    if participant_id:
        user = db.execute('SELECT * FROM Users WHERE participant_id = ?', (participant_id,)).fetchone()
    
    if user is None:
        new_participant_id = str(uuid.uuid4())
        db.execute(
            'INSERT INTO Users (participant_id, username) VALUES (?, ?)', 
            (new_participant_id, username)
        )
        db.commit()
        user = db.execute('SELECT * FROM Users WHERE participant_id = ?', (new_participant_id,)).fetchone()
    else:
        if username and username != user['username']:
            db.execute('UPDATE Users SET username = ? WHERE user_id = ?', (username, user['user_id']))
            db.commit()
            user = db.execute('SELECT * FROM Users WHERE participant_id = ?', (participant_id,)).fetchone()

    game_id = get_or_create_game(db, user['user_id'], user['username'], "easy1", new_game=new_game)
    round_number = get_next_round_number(db, game_id)
    
    current_difficulty = get_current_difficulty(db, game_id)
    
    logger.info(f"Game {game_id}, Round {round_number}/12, Difficulty: {current_difficulty} (get-word), new_game={new_game}")

    secret_word = select_word_for_round(db, game_id, category, current_difficulty, WORD_DATA)
    
    if not secret_word:
        return jsonify({"error": "No words available for this combination"}), 400

    round_id = get_or_create_round(
        db, game_id, round_number, secret_word, category, current_difficulty, 'ai_guesses'
    )

    return jsonify({
        "word": secret_word,
        "category": category,
        "current_difficulty": current_difficulty,
        "round_id": round_id,
        "game_id": game_id,
        "round_number": round_number,
        "participant_id": user['participant_id']
    })

@app.post("/hint")
def get_hint():
    data = request.get_json(force=True) or {}
    round_id = data.get("round_id")

    if not round_id:
        return jsonify({"error": "round_id is required"}), 400

    db = get_db()

    round_data = db.execute(
        "SELECT secret_word, category, difficulty FROM Rounds WHERE round_id = ?",
        (round_id,)
    ).fetchone()

    if not round_data:
        return jsonify({"error": "Invalid round_id"}), 404

    word = round_data["secret_word"]

    prompt = f"""Give a subtle hint to help guess the word '{word}'.

Rules:
- DO NOT use the word itself or obvious synonyms
- Use simple vocabulary (B1 English)
- Only 1-2 short sentences
- No questions, lists, or sound effects
- May reveal starting/ending letter or mention function/context

Generate hint:""".strip()

    hint = llm_complete(prompt, temperature=0.6, max_tokens=30).strip()

    hint_action_number = next_action_number(db, round_id)
    cursor = db.execute(
        "INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content) VALUES (?, ?, ?, ?, ?)",
        (round_id, hint_action_number, "ai", "hint", hint)
    )
    action_id = cursor.lastrowid
    db.commit()

    return jsonify({"hint": hint})



@app.post("/commentary")
def get_commentary():
    """Generate a short, funny AI commentary message for a game event."""
    data = request.get_json(force=True) or {}
    event = data.get("event", "")
    context = data.get("context", {})

    context_parts = []
    if context.get("word"):
        context_parts.append(f"The word was \"{context['word']}\"")
    if context.get("category"):
        context_parts.append(f"Category: {context['category']}")
    if context.get("guess"):
        context_parts.append(f"The guess was \"{context['guess']}\"")
    if context.get("attempt"):
        context_parts.append(f"Attempt #{context['attempt']}")
    if context.get("round"):
        context_parts.append(f"Round {context['round']} of 12")
    if context.get("seconds_left"):
        context_parts.append(f"{context['seconds_left']} seconds remaining")

    context_str = ". ".join(context_parts) if context_parts else "No extra context"

    prompt = f"""You are a funny, witty game show host commentating on a word-guessing game between a human and an AI.

EVENT: {event}
CONTEXT: {context_str}

Generate ONE short funny reaction. 1-4 words max. Be playful, creative, and vary your style every time. Use humor, puns, pop culture references, or dramatic flair. Add funny emojis if you want. Only provide the reaction line, nothing else.""".strip()

    try:
        message = llm_complete_fastest(prompt)
        print(f"🎤 Commentary for event '{event}': {message}")
        return jsonify({"message": message})
    except Exception as e:
        logger.error(f"Commentary generation failed: {e}")
        return jsonify({"message": ""}), 200



@app.post("/end-game")
def end_game():
    """
    End a round or full game.

    ✅ UPDATED: Stores winner, user_final_time, ai_final_time in Games table.
    ✅ UPDATED: 9-level difficulty, adjusts after EVERY even round.
    """
    data = request.get_json(force=True) or {}
    round_id = data.get("round_id")
    game_id = data.get("game_id")
    outcome = data.get("outcome")
    user_time_left = data.get("user_time_left")
    ai_time_left = data.get("ai_time_left")
    winner = data.get("winner")

    print(f"\n{'='*80}")
    print(f"🎮 /END-GAME ENDPOINT CALLED")
    print(f"{'='*80}")
    print(f"  round_id:       {round_id}")
    print(f"  game_id:        {game_id}")
    print(f"  outcome:        {outcome}")
    print(f"  user_time_left: {user_time_left}")
    print(f"  ai_time_left:   {ai_time_left}")
    print(f"  winner:         {winner}")
    print(f"{'='*80}\n")

    db = get_db()

    # ── End a specific round ──
    if round_id:
        db.execute(
            'UPDATE Rounds SET outcome = ?, ended_at = CURRENT_TIMESTAMP WHERE round_id = ?',
            (outcome, round_id)
        )
        db.commit()

        db.execute(
            'INSERT OR REPLACE INTO Actions (round_id, action_number, actor, action_type, content) VALUES (?, ?, ?, ?, ?)',
            (round_id, next_action_number(db, round_id), 'system', 'end_round', outcome)
        )
        db.commit()

        round_data = db.execute(
            'SELECT game_id, round_number, game_mode, secret_word FROM Rounds WHERE round_id = ?',
            (round_id,)
        ).fetchone()

        if not round_data:
            return jsonify({"error": "Round not found"}), 404

        game_id = round_data['game_id']
        current_round_number = round_data['round_number']
        game_mode = round_data['game_mode']

        print(f"✅ Round data: game_id={game_id}, round={current_round_number}, mode={game_mode}, outcome={outcome}")

        # ✅ Adjust difficulty after EVERY even round
        if current_round_number % 2 == 0:
            print(f"\n🎯 Even round {current_round_number} — checking difficulty adjustment...")

            current_diff = get_current_difficulty(db, game_id)
            next_difficulty = calculate_next_difficulty(db, game_id, current_round_number)

            if next_difficulty != current_diff:
                print(f"🔄 DIFFICULTY CHANGE: {current_diff} → {next_difficulty}")
                update_game_difficulty(db, game_id, next_difficulty)
                logger.info(f"🎯 Difficulty adjusted: {current_diff} → {next_difficulty} after round {current_round_number}")
            else:
                print(f"➡️ Difficulty unchanged: {current_diff}")
        else:
            print(f"⏭️ Odd round {current_round_number} — no difficulty check")

        db.execute('''
            UPDATE Games
            SET total_rounds = (
                SELECT COUNT(*) FROM Rounds WHERE game_id = ? AND outcome IS NOT NULL
            )
            WHERE game_id = ?
        ''', (game_id, game_id))
        db.commit()

        game_data = db.execute(
            'SELECT total_rounds, current_difficulty FROM Games WHERE game_id = ?',
            (game_id,)
        ).fetchone()

        print(f"📈 Progress: {game_data['total_rounds']}/12 rounds, difficulty: {game_data['current_difficulty']}")

        # ── Check if this is the last round (12) or if user quit ──
        if current_round_number == 12 or outcome == 'quit':
            final_outcome = 'completed' if current_round_number == 12 else 'quit'

            if not winner and user_time_left is not None and ai_time_left is not None:
                if user_time_left > ai_time_left:
                    winner = 'user'
                elif ai_time_left > user_time_left:
                    winner = 'ai'
                else:
                    winner = 'tie'

            print(f"🏆 Game ending — winner: {winner}, user_time: {user_time_left}, ai_time: {ai_time_left}")

            db.execute('''
                UPDATE Games
                SET ended_at = CURRENT_TIMESTAMP,
                    outcome = ?,
                    winner = ?,
                    user_final_time = ?,
                    ai_final_time = ?
                WHERE game_id = ?
            ''', (final_outcome, winner, user_time_left, ai_time_left, game_id))
            db.commit()

            return jsonify({
                "status": "ok",
                "game_ended": True,
                "game_outcome": final_outcome,
                "winner": winner,
                "user_final_time": user_time_left,
                "ai_final_time": ai_time_left,
                "total_rounds": current_round_number
            })

        next_diff = get_current_difficulty(db, game_id)

        return jsonify({
            "status": "ok",
            "game_ended": False,
            "rounds_completed": current_round_number,
            "rounds_remaining": 12 - current_round_number,
            "next_difficulty": next_diff
        })

    # ── End the full game directly ──
    elif game_id:
        if not winner and user_time_left is not None and ai_time_left is not None:
            if user_time_left > ai_time_left:
                winner = 'user'
            elif ai_time_left > user_time_left:
                winner = 'ai'
            else:
                winner = 'tie'

        db.execute(
            '''UPDATE Games
               SET outcome = ?, ended_at = CURRENT_TIMESTAMP,
                   winner = ?, user_final_time = ?, ai_final_time = ?
               WHERE game_id = ?''',
            (outcome, winner, user_time_left, ai_time_left, game_id)
        )
        db.commit()

        return jsonify({
            "status": "ok",
            "game_ended": True,
            "winner": winner,
            "user_final_time": user_time_left,
            "ai_final_time": ai_time_left
        })

    else:
        return jsonify({"error": "round_id or game_id required"}), 400


@app.post("/log")
@app.post("/api/log")
def log_event():
    return {"status": "success"}, 201


@app.get("/analytics")
def analytics_dashboard():
    """Serve the analytics dashboard — requires session auth."""
    from flask import session, render_template
    if not session.get('analytics_auth'):
        return render_template('analytics_login.html')
    return render_template('analytics.html')


@app.post("/analytics/login")
def analytics_login():
    """Validate the analytics password and set session."""
    from flask import session, redirect, url_for
    data = request.get_json(force=True) or {}
    if data.get('password') == ADMIN_PASSWORD:
        session['analytics_auth'] = True
        return jsonify({'ok': True})
    return jsonify({'error': 'Wrong password'}), 401


@app.get("/analytics/logout")
def analytics_logout():
    """Clear analytics session."""
    from flask import session
    session.pop('analytics_auth', None)
    return jsonify({'ok': True})


@app.post("/analytics/reset-db")
def analytics_reset_db():
    """Drop and recreate all tables — wipes all study data. Requires analytics auth."""
    from flask import session
    if not session.get('analytics_auth'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        db = get_db()
        # Read schema and re-run it (CREATE TABLE IF NOT EXISTS is safe)
        # First drop all data tables
        db.executescript("""
            DELETE FROM Referee_Checks;
            DELETE FROM Actions;
            DELETE FROM Rounds;
            DELETE FROM Games;
            DELETE FROM Users;
            DELETE FROM sqlite_sequence WHERE name IN ('Referee_Checks','Actions','Rounds','Games','Users');
        """)
        db.commit()
        return jsonify({'ok': True, 'message': 'All study data has been deleted. Tables are empty and ready for a fresh user study.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.get("/analytics/data")
def analytics_data():
    """Returns all key analytics metrics for the user study dashboard."""
    from flask import session
    if not session.get('analytics_auth'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()

    total_games = db.execute("SELECT COUNT(*) FROM Games WHERE winner IS NOT NULL").fetchone()[0]
    user_wins   = db.execute("SELECT COUNT(*) FROM Games WHERE winner = 'user'").fetchone()[0]
    ai_wins     = db.execute("SELECT COUNT(*) FROM Games WHERE winner = 'ai'").fetchone()[0]
    ties        = db.execute("SELECT COUNT(*) FROM Games WHERE winner = 'tie'").fetchone()[0]
    total_users = db.execute("SELECT COUNT(DISTINCT user_id) FROM Games").fetchone()[0]
    total_rounds = db.execute("SELECT COUNT(*) FROM Rounds WHERE ended_at IS NOT NULL").fetchone()[0]

    outcomes = db.execute(
        "SELECT outcome, COUNT(*) as cnt FROM Games WHERE ended_at IS NOT NULL GROUP BY outcome"
    ).fetchall()
    outcome_breakdown = {r['outcome']: r['cnt'] for r in outcomes}

    avg_user_turn_duration = db.execute("""
        SELECT AVG(round_guess_ms) / 1000.0
        FROM (
            SELECT r.round_id, SUM(a.duration_ms) AS round_guess_ms
            FROM Rounds r
            JOIN Actions a ON a.round_id = r.round_id
            WHERE r.game_mode = 'user_guesses'
              AND a.actor = 'user'
              AND a.action_type = 'guess'
              AND a.duration_ms IS NOT NULL
            GROUP BY r.round_id
        )
    """).fetchone()[0]

    user_turn_duration = db.execute("""
        SELECT ROUND(AVG(round_guess_ms) / 1000.0, 1) as avg_sec,
               COUNT(*) as cnt
        FROM (
            SELECT r.round_id, SUM(a.duration_ms) AS round_guess_ms
            FROM Rounds r
            JOIN Actions a ON a.round_id = r.round_id
            WHERE r.game_mode = 'user_guesses'
              AND a.actor = 'user'
              AND a.action_type = 'guess'
              AND a.duration_ms IS NOT NULL
            GROUP BY r.round_id
        )
    """).fetchone()

    avg_ai_turn_duration = db.execute("""
        SELECT AVG(round_thinking_ms) / 1000.0
        FROM (
            SELECT r.round_id, SUM(a.duration_ms) AS round_thinking_ms
            FROM Rounds r
            JOIN Actions a ON a.round_id = r.round_id
            WHERE r.game_mode = 'ai_guesses'
              AND a.actor = 'ai'
              AND a.action_type = 'guess'
              AND a.duration_ms IS NOT NULL
            GROUP BY r.round_id
        )
    """).fetchone()[0]

    ai_turn_duration = db.execute("""
        SELECT ROUND(AVG(round_thinking_ms) / 1000.0, 1) as avg_sec,
               COUNT(*) as cnt
        FROM (
            SELECT r.round_id, SUM(a.duration_ms) AS round_thinking_ms
            FROM Rounds r
            JOIN Actions a ON a.round_id = r.round_id
            WHERE r.game_mode = 'ai_guesses'
              AND a.actor = 'ai'
              AND a.action_type = 'guess'
              AND a.duration_ms IS NOT NULL
            GROUP BY r.round_id
        )
    """).fetchone()

    round_outcomes = db.execute(
        "SELECT outcome, COUNT(*) as cnt FROM Rounds WHERE ended_at IS NOT NULL GROUP BY outcome"
    ).fetchall()
    round_outcome_breakdown = {r['outcome']: r['cnt'] for r in round_outcomes}

    total_violations = db.execute("SELECT COUNT(*) FROM Referee_Checks WHERE is_valid = 0").fetchone()[0]
    total_checks = db.execute("SELECT COUNT(*) FROM Referee_Checks").fetchone()[0]
    violations_by_type = db.execute("""
        SELECT violation_type, COUNT(*) as cnt
        FROM Referee_Checks WHERE is_valid = 0 AND violation_type IS NOT NULL
        GROUP BY violation_type ORDER BY cnt DESC
    """).fetchall()

    avg_user_guesses = db.execute("""
        SELECT ROUND(AVG(guess_count), 2) FROM (
            SELECT r.round_id, COUNT(a.action_id) as guess_count
            FROM Rounds r JOIN Actions a ON a.round_id = r.round_id
            WHERE r.game_mode = 'user_guesses' AND a.action_type = 'guess' AND a.actor = 'user'
            GROUP BY r.round_id
        )
    """).fetchone()[0]

    ai_correct = db.execute("""
        SELECT COUNT(*) FROM Rounds
        WHERE game_mode = 'ai_guesses' AND outcome = 'win' AND ended_at IS NOT NULL
    """).fetchone()[0]
    ai_rounds_total = db.execute("""
        SELECT COUNT(*) FROM Rounds WHERE game_mode = 'ai_guesses' AND ended_at IS NOT NULL
    """).fetchone()[0]

    user_correct = db.execute("""
        SELECT COUNT(*) FROM Rounds
        WHERE game_mode = 'user_guesses' AND outcome = 'win' AND ended_at IS NOT NULL
    """).fetchone()[0]
    user_rounds_total = db.execute("""
        SELECT COUNT(*) FROM Rounds WHERE game_mode = 'user_guesses' AND ended_at IS NOT NULL
    """).fetchone()[0]

    per_user = db.execute("""
        SELECT u.username,
               COUNT(DISTINCT g.game_id) as games_played,
               SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END) as user_wins,
               SUM(CASE WHEN g.winner = 'ai' THEN 1 ELSE 0 END) as ai_wins,
               ROUND(AVG((julianday(g.ended_at) - julianday(g.started_at)) * 1440), 1) as avg_game_min
        FROM Users u JOIN Games g ON g.user_id = u.user_id
        WHERE g.ended_at IS NOT NULL
        GROUP BY u.user_id ORDER BY games_played DESC
    """).fetchall()

    difficulty_dist = db.execute("""
        SELECT difficulty, COUNT(*) as cnt FROM Rounds GROUP BY difficulty ORDER BY cnt DESC
    """).fetchall()

    category_perf = db.execute("""
        SELECT category, COUNT(*) as total,
               SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins
        FROM Rounds WHERE ended_at IS NOT NULL
        GROUP BY category ORDER BY total DESC
    """).fetchall()

    recent_games = db.execute("""
        SELECT g.game_id, g.username_at_game_time, g.started_at, g.ended_at,
               g.winner, g.outcome, g.total_rounds, g.user_final_time, g.ai_final_time
        FROM Games g WHERE g.winner IS NOT NULL
        ORDER BY g.game_id DESC LIMIT 15
    """).fetchall()

    violations_per_game = db.execute("""
        SELECT g.username_at_game_time, COUNT(rc.check_id) as violations
        FROM Games g
        JOIN Rounds r ON r.game_id = g.game_id
        JOIN Referee_Checks rc ON rc.round_id = r.round_id AND rc.is_valid = 0
        GROUP BY g.game_id ORDER BY violations DESC LIMIT 20
    """).fetchall()

    user_accuracy_pct = round(user_correct / user_rounds_total * 100, 1) if user_rounds_total else 0
    ai_accuracy_pct = round(ai_correct / ai_rounds_total * 100, 1) if ai_rounds_total else 0

    win_comparison = [
        {"side": "user", "label": "User", "value": user_wins},
        {"side": "ai", "label": "AI", "value": ai_wins},
        {"side": "tie", "label": "Tie", "value": ties},
    ]

    turn_duration_comparison = [
        {"side": "user", "label": "User", "avg_sec": user_turn_duration["avg_sec"] if user_turn_duration else None, "count": user_turn_duration["cnt"] if user_turn_duration else 0},
        {"side": "ai", "label": "AI", "avg_sec": ai_turn_duration["avg_sec"] if ai_turn_duration else None, "count": ai_turn_duration["cnt"] if ai_turn_duration else 0},
    ]

    guess_accuracy_comparison = [
        {"side": "user", "label": "User", "correct": user_correct, "total": user_rounds_total, "accuracy_pct": user_accuracy_pct},
        {"side": "ai", "label": "AI", "correct": ai_correct, "total": ai_rounds_total, "accuracy_pct": ai_accuracy_pct},
    ]

    return jsonify({
        "overview": {
            "total_games": total_games,
            "total_users": total_users,
            "total_rounds": total_rounds,
            "user_wins": user_wins,
            "ai_wins": ai_wins,
            "ties": ties,
            "total_violations": total_violations,
            "total_checks": total_checks,
            "violation_rate_pct": round(total_violations / total_checks * 100, 1) if total_checks else 0,
            "avg_user_turn_duration_sec": round(avg_user_turn_duration, 1) if avg_user_turn_duration else None,
            "avg_ai_turn_duration_sec": round(avg_ai_turn_duration, 1) if avg_ai_turn_duration else None,
            "avg_user_guesses_per_round": avg_user_guesses,
            "ai_correct_guesses": ai_correct,
            "ai_rounds_total": ai_rounds_total,
            "ai_accuracy_pct": ai_accuracy_pct,
            "user_correct_guesses": user_correct,
            "user_rounds_total": user_rounds_total,
            "user_accuracy_pct": user_accuracy_pct,
        },
        "game_outcome_breakdown": outcome_breakdown,
        "round_outcome_breakdown": round_outcome_breakdown,
        "win_comparison": win_comparison,
        "turn_duration_comparison": turn_duration_comparison,
        "guess_accuracy_comparison": guess_accuracy_comparison,
        "violations_by_type": [
            {"type": r["violation_type"], "count": r["cnt"]}
            for r in violations_by_type
        ],
        "violations_per_game": [
            {"username": r["username_at_game_time"], "violations": r["violations"]}
            for r in violations_per_game
        ],
        "per_user_summary": [
            {
                "username": r["username"],
                "games_played": r["games_played"],
                "user_wins": r["user_wins"],
                "ai_wins": r["ai_wins"],
                "avg_game_min": r["avg_game_min"]
            }
            for r in per_user
        ],
        "difficulty_distribution": [
            {"difficulty": r["difficulty"], "count": r["cnt"]}
            for r in difficulty_dist
        ],
        "category_performance": [
            {
                "category": r["category"],
                "total": r["total"],
                "wins": r["wins"],
                "win_rate_pct": round(r["wins"] / r["total"] * 100, 1) if r["total"] else 0
            }
            for r in category_perf
        ],
        "recent_games": [
            {
                "game_id": r["game_id"],
                "username": r["username_at_game_time"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "winner": r["winner"],
                "outcome": r["outcome"],
                "total_rounds": r["total_rounds"],
                "user_time_left": r["user_final_time"],
                "ai_time_left": r["ai_final_time"]
            }
            for r in recent_games
        ]
    })


if __name__ == "__main__":
    ensure_database_ready()
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
