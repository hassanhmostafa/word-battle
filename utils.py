from typing import List, Dict, Any, Tuple, Optional, Callable
import re
import json
import hashlib
import threading
import unicodedata
import os
from functools import lru_cache

import spacy
from detoxify import Detoxify
from ai import *

nlp = spacy.load("en_core_web_sm")
detox = Detoxify("original")

# -----------------------------------------------------------------------------
# Simple in-memory cache to prevent "click until pass"
# same (secret_word, category, difficulty, cleaned_description) -> same verdict
# -----------------------------------------------------------------------------
_REFEREE_CACHE: Dict[str, Tuple[bool, List[Dict[str, Any]]]] = {}
_REFEREE_CACHE_LOCK = threading.Lock()

# ============================================================================
# REFEREE PROMPT LOADER
# The editable part of the referee prompt lives in referee_prompt.txt.
# The file is read fresh on every referee call — edit it on the server at any
# time and the next check will use the new version automatically.
# ============================================================================

_REFEREE_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "referee_prompt.txt")

def load_referee_prompt_body() -> str:
    """Read the editable referee prompt body from disk (fresh on every call)."""
    try:
        with open(_REFEREE_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback if the file is missing — basic rules so the game still works
        return (
            "Check that the description does not contain the secret word or any direct synonym.\n"
            "Return ONLY valid JSON wrapped in these tags:\n"
            "<json>\n{\"is_valid\": true, \"violations\": []}\n</json>"
        )


def _extract_json(s: str) -> Optional[dict]:
    """
    Robust JSON-in-tags extractor.
    Accepts:
      <json>{"same": true}</json>
    even with newlines/spaces and any casing.
    """
    s = (s or "").strip()
    m = re.search(r"<json>\s*({.*?})\s*</json>", s, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def check_toxicity(text: str, threshold: float = 0.8) -> Tuple[bool, Dict[str, float]]:
    """Check if text contains toxic content using Detoxify."""
    scores = detox.predict(text)
    scores = {k: float(v) for k, v in scores.items()}
    is_bad = (
        scores.get("toxicity", 0) >= threshold
        or scores.get("severe_toxicity", 0) >= threshold
        or scores.get("obscene", 0) >= threshold
        or scores.get("threat", 0) >= threshold
        or scores.get("insult", 0) >= threshold
        or scores.get("identity_attack", 0) >= threshold
        or scores.get("sexual_explicit", 0) >= threshold
    )
    return is_bad, scores


# ============================================================================
# RULE-BASED REFEREE (MINIMAL, as requested)
# Only checks: exact secret word present in description (word boundary)
# ============================================================================

def rule_based_referee_check(
    description: str,
    secret_word: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    violations: List[Dict[str, Any]] = []

    if not description or not description.strip():
        violations.append({
            "code": "EMPTY",
            "message": "Description is empty.",
            "severity": "high"
        })
        return False, violations

    # Remove "The word is not ..." AND everything after it
    text_clean = re.sub(r"(?is)\s*\.?\s*the word is not\b.*$", "", description).strip()
    text_lower = text_clean.lower()

    sw = (secret_word or "").strip().lower()
    if sw:
        # 1) Reject any substring appearance (whole word OR part of another word)
        if sw in text_lower:
            violations.append({
                "code": "WORD_LEAK",
                "message": f"Description contains the secret word (or part of it): '{secret_word}'.",
                "severity": "high"
            })
            return False, violations  # early exit

        # 2) Reject lemma/morphological variants via spaCy
        try:
            nlp = _get_nlp()
        except Exception as e:
            violations.append({
                "code": "LEMMA_CHECK_UNAVAILABLE",
                "message": f"Cannot run lemma checks (spaCy/model not available): {e}",
                "severity": "high"
            })
            return False, violations

        doc = nlp(text_clean)
        token_lemmas = [t.lemma_.lower() for t in doc if not t.is_space]
        token_texts  = [t.text.lower()  for t in doc if not t.is_space]

        sw_doc = nlp(sw)
        sw_lemmas = [t.lemma_.lower() for t in sw_doc if not t.is_space]

        if sw_lemmas:
            if len(sw_lemmas) == 1:
                sl = sw_lemmas[0]

                lemma_hit = any(sl in lem for lem in token_lemmas)
                text_hit  = any(sl in tok for tok in token_texts)

                if lemma_hit or text_hit:
                    violations.append({
                        "code": "WORD_LEAK",
                        "message": f"Description contains a morphological variant of '{secret_word}'.",
                        "severity": "high"
                    })
            else:
                # Multi-token secret (phrase): check contiguous lemma match
                n = len(sw_lemmas)
                for i in range(len(token_lemmas) - n + 1):
                    if token_lemmas[i:i+n] == sw_lemmas:
                        violations.append({
                            "code": "WORD_LEAK",
                            "message": f"Description contains a morphological variant of the phrase '{secret_word}'.",
                            "severity": "high"
                        })
                        break

    return (len(violations) == 0), violations


# ============================================================================
# AI-BASED REFEREE (MAIN REFEREE)
# - Cleans "The word is not X" so retries don't poison the referee
# - Deterministic: temperature=0
# - Retry once if JSON malformed
# - Fail-closed on invalid AI output (prevents click-until-pass)
# - Caches verdict for identical inputs
# ============================================================================

def _split_desc_hint(raw: str) -> Tuple[str, Optional[str]]:
    raw = (raw or "").strip()
    m = re.search(r"\bHINT\s*:\s*", raw, flags=re.IGNORECASE)
    if not m:
        return raw, None
    parts = re.split(r"\bHINT\s*:\s*", raw, maxsplit=1, flags=re.IGNORECASE)
    desc = (parts[0] or "").strip()
    hint = (parts[1] or "").strip()
    return desc, (hint or None)

LETTER_HINT_RE = re.compile(
    r"\b(starts with|begins with|ends with|first letter|last letter|has \d+ letters?)\b",
    re.IGNORECASE
)

def _content_lemmas(s: str) -> set:
    doc = nlp((s or "").lower())
    return {
        t.lemma_
        for t in doc
        if t.is_alpha and not t.is_stop and t.pos_ in {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "NUM"}
    }

def _is_redundant_hint(description: str, hint: str) -> bool:
    hint = (hint or "").strip()
    desc = (description or "").strip()

    if not hint:
        return True

    # Super short hints are almost always redundant / useless
    if len(hint.split()) < 3 and not LETTER_HINT_RE.search(hint):
        return True

    d = _content_lemmas(desc)
    h = _content_lemmas(hint)

    # If hint has no meaningful content words → redundant/useless
    if not h:
        return True

    # If hint adds zero new content words → redundant
    new = h - d
    if len(new) == 0:
        return True

    # If hint is *mostly* overlap and only adds 1 weak new token → treat as redundant
    overlap_ratio = len(h & d) / max(1, len(h))
    if overlap_ratio >= 0.8 and len(new) <= 1:
        return True

    return False


def ai_based_referee_check(
    description: str,
    secret_word: str,
    category: str,
    difficulty: str,
    llm_complete_func,
    forbidden_words: Optional[List[str]] = None,
    actor: str = "user"
) -> Tuple[bool, List[Dict[str, Any]]]:

    # ---------------- DEBUG HEADER ----------------
    print(f"\n{'='*60}")
    print("🤖 AI REFEREE CHECK")
    print(f"{'='*60}")
    print(f"Actor: {actor}")
    print(f"Secret Word: {secret_word}")
    print(f"Category: {category}")
    print(f"Difficulty: {difficulty}")
    print(f"Description: {(description or '')[:120]}...")
    print(f"{'='*60}\n")

    raw = (description or "").strip()

    # Split into description + hint
    description_raw, hint_raw = _split_desc_hint(raw)
    description_clean = re.sub(r"(?is)\s*\.?\s*the word is not\b.*$", "", description_raw).strip()
    hint_clean = (hint_raw or "").strip() if hint_raw else None

    # Normalize for stable cache key
    norm_desc = re.sub(r"\s+", " ", description_clean).strip().lower()
    norm_hint = re.sub(r"\s+", " ", hint_clean).strip().lower() if hint_clean else ""

    cache_key_raw = (
        f"{secret_word.lower()}|{category.lower()}|{difficulty.lower()}|"
        f"desc:{norm_desc}|hint:{norm_hint}"
    )
    cache_key = hashlib.sha256(cache_key_raw.encode("utf-8")).hexdigest()

    # Cache hit
    with _REFEREE_CACHE_LOCK:
        if cache_key in _REFEREE_CACHE:
            cached = _REFEREE_CACHE[cache_key]
            print("🧠 Cache hit:", "PASS" if cached[0] else "FAIL", f"({len(cached[1])} violations)")
            return cached

    # Hard gate: reject redundant hints deterministically
    if hint_clean and _is_redundant_hint(description_clean, hint_clean):
        final = (False, [{
            "code": "REDUNDANT",
            "message": "Hint repeats the description. Add a new concrete detail (appearance, behavior, habitat, function, etc.).",
            "severity": "high"
        }])
        with _REFEREE_CACHE_LOCK:
            _REFEREE_CACHE[cache_key] = final
        return final

    print(f"🧹 Cleaned description: {description_clean}")
    print(f"💡 Hint: {hint_clean}")

    # Optional: include forbidden words list in AI prompt as additional rule context
    forbidden_clause = ""
    if forbidden_words:
        forbidden_clause = (
            "\nADDITIONAL RULE: The description must NOT contain any of these forbidden words: "
            + ", ".join([f'"{w}"' for w in forbidden_words])
            + "\nIf any forbidden word appears, return a violation with code FORBIDDEN_WORD_USED, but only if the forbidden word itself is used.\n"
        )

    # ── Build prompt: fixed header + editable body from file ──────────────────
    prompt = f"""You are a referee for a word-guessing game.

SECRET WORD: {secret_word}
CATEGORY: {category}
DIFFICULTY: {difficulty}
DESCRIPTION: "{description_clean}"
HINT: {hint_clean or "None"}

The player already knows the CATEGORY, so mentioning "{category}" is allowed.
Decide if the DESCRIPTION violates any rules:

{load_referee_prompt_body()}
""".strip()

    def _extract_json_local(s: str) -> Optional[str]:
        s = (s or "").strip()

        # 1) Prefer <json>...</json>
        m = re.search(r"<json>\s*(\{.*?\})\s*</json>", s, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()

        # 2) Strip code fences if present
        s = re.sub(r"^```json\s*", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"^```\s*", "", s).strip()
        s = re.sub(r"\s*```$", "", s).strip()

        # 3) Fallback: first {...}
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        return m.group(0).strip() if m else None

    def _fail_closed() -> Tuple[bool, List[Dict[str, Any]]]:
        print("⚠️ Referee failed — failing OPEN (letting description through).")
        return True, []

    # Retry once for malformed output
    last_raw = ""
    for attempt in range(2):
        try:
            print(f"🤖 Calling LLM (attempt {attempt+1}/2)...")
            last_raw = llm_complete_func(prompt, temperature=0.0, max_tokens=220)
            print(f"🤖 Raw AI (first 250 chars): {last_raw[:250]}...")

            json_str = _extract_json_local(last_raw)
            if not json_str:
                raise ValueError("Could not extract JSON from AI output")

            result = json.loads(json_str)

            if not isinstance(result, dict) or "is_valid" not in result or "violations" not in result:
                raise ValueError("Invalid JSON structure")

            is_valid = bool(result["is_valid"])
            violations = result["violations"]

            if not isinstance(violations, list):
                raise ValueError("violations is not a list")

            cleaned_violations: List[Dict[str, Any]] = []
            for v in violations:
                if isinstance(v, dict):
                    cleaned_violations.append({
                        "code": str(v.get("code", "UNKNOWN")),
                        "message": str(v.get("message", "Rule violation.")),
                        "severity": str(v.get("severity", "high"))
                    })

            final_ok = is_valid and len(cleaned_violations) == 0
            final = (final_ok, cleaned_violations)

            print(f"✅ AI-based: {'PASS' if final_ok else 'FAIL'} ({len(cleaned_violations)} violations)")
            for v in cleaned_violations:
                print(f"  - [{v.get('code')}] {v.get('message')}")

            with _REFEREE_CACHE_LOCK:
                _REFEREE_CACHE[cache_key] = final

            return final

        except Exception as e:
            print(f"⚠️ AI referee parse failed: {e}")

    print("❌ Referee failed twice. Returning REFEREE_ERROR.")
    print(f"Last raw output (first 400 chars): {last_raw[:400]}...")

    final = _fail_closed()
    with _REFEREE_CACHE_LOCK:
        _REFEREE_CACHE[cache_key] = final
    return final


# ============================================================================
# FORBIDDEN WORDS (keep this logic in final function)
# ============================================================================

import re
from typing import List, Tuple
import spacy

# Load spaCy model once globally (recommended)
nlp = spacy.load("en_core_web_sm")

@lru_cache(maxsize=1)
def _get_nlp():
    # Keep tagger+lemmatizer, disable heavier components
    return spacy.load("en_core_web_sm", disable=["parser", "ner", "textcat"])

def check_forbidden_words(description: str, forbidden_words: List[str], max_words: int = 0) -> Tuple[bool, List[str]]:
    """
    Enforce: description may contain at most `max_words` forbidden words.
    Matches:
      1) Any substring occurrence (whole word OR part of another word)
      2) Morphological variants via spaCy lemmas (e.g., buy <-> bought, run <-> running)

    Returns: (violated, found_words)
    """
    if not forbidden_words:
        return False, []

    # Remove "The word is not ..." and EVERYTHING AFTER it
    description_clean = re.sub(r"(?is)\s*\.?\s*the word is not\b.*$", "", description or "").strip()
    description_lower = description_clean.lower()

    found: List[str] = []
    found_set = set()

    # ---- 1) Fast substring check on raw text ----
    normalized = []
    for w in forbidden_words:
        w_low = (w or "").strip().lower()
        if w_low:
            normalized.append((w, w_low))

    for original, w_low in normalized:
        if w_low in description_lower:
            if original not in found_set:
                found.append(original)
                found_set.add(original)
                if len(found) > max_words:
                    return True, found

    # ---- 2) Lemma-based check (morphological variants) ----
    nlp = _get_nlp()
    doc = nlp(description_clean)

    # Build token lemmas/texts once
    token_lemmas = [t.lemma_.lower() for t in doc if not t.is_space]
    token_texts  = [t.text.lower()  for t in doc if not t.is_space]

    for original, w_low in normalized:
        if original in found_set:
            continue

        # Lemmatize the forbidden word/phrase
        w_doc = nlp(w_low)
        w_lemmas = [t.lemma_.lower() for t in w_doc if not t.is_space]

        if not w_lemmas:
            continue

        if len(w_lemmas) == 1:
            wl = w_lemmas[0]
            lemma_hit = any(wl in lem for lem in token_lemmas)
            text_hit  = any(wl in txt for txt in token_texts)
            if lemma_hit or text_hit:
                found.append(original)
                found_set.add(original)
                if len(found) > max_words:
                    return True, found
        else:
            # Multi-token phrase: check lemma n-grams
            n = len(w_lemmas)
            for i in range(len(token_lemmas) - n + 1):
                if token_lemmas[i:i+n] == w_lemmas:
                    found.append(original)
                    found_set.add(original)
                    if len(found) > max_words:
                        return True, found
                    break

    return (len(found) > max_words), found



def check_forbidden_words_aggressive(
    text: str,
    forbidden_words: List[str],
    max_words: int = 0
) -> Tuple[bool, List[str]]:
    """
    Aggressive forbidden check. Enforces: text may contain at most `max_words` forbidden words.
    Catches: misspellings, leetspeak, spacing/punctuation splits, repeated letters, simple suffixes.
    Returns (violated, found_words).
    """

    if not forbidden_words:
        return False, []

    # --- helpers (nested) ---
    LEET_MAP: Dict[str, str] = {
        "0": "o", "1": "i", "2": "z", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
        "@": "a", "$": "s", "!": "i", "|": "i", "+": "t"
    }
    WORDLIKE_RE = re.compile(r"[a-z0-9@\$!\|]+", re.IGNORECASE)

    def strip_accents(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        return "".join(ch for ch in s if not unicodedata.combining(ch))

    def leet_normalize(s: str) -> str:
        return "".join(LEET_MAP.get(ch, ch) for ch in s)

    def collapse_repeats(s: str) -> str:
        return re.sub(r"(.)\1{2,}", r"\1\1", s)

    def normalize_for_matching(s: str) -> str:
        s = strip_accents(s or "")
        s = s.lower()
        s = leet_normalize(s)
        s = collapse_repeats(s)
        return s

    def letters_only(s: str) -> str:
        return re.sub(r"[^a-z]+", "", s)

    def max_edits(word: str) -> int:
        L = len(word)
        if L <= 4:
            return 0
        if L <= 6:
            return 1
        return 2

    def levenshtein_cutoff(a: str, b: str, max_dist: int) -> int:
        """Levenshtein distance with early-exit cutoff."""
        if a == b:
            return 0
        if abs(len(a) - len(b)) > max_dist:
            return max_dist + 1
        if len(a) > len(b):
            a, b = b, a

        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            cur = [i]
            row_min = cur[0]
            for j, cb in enumerate(b, start=1):
                ins = cur[j - 1] + 1
                dele = prev[j] + 1
                sub = prev[j - 1] + (ca != cb)
                val = ins if ins < dele else dele
                if sub < val:
                    val = sub
                cur.append(val)
                if val < row_min:
                    row_min = val
            if row_min > max_dist:
                return max_dist + 1
            prev = cur
        return prev[-1]

    def variants(word: str) -> List[str]:
        w = letters_only(normalize_for_matching(word))
        if not w:
            return []
        vars_ = {w}
        for suf in ("s", "es", "ed", "ing"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                vars_.add(w[: -len(suf)])
        return sorted(vars_, key=len, reverse=True)

    def token_hits(token_letters: str, w: str) -> bool:
        if not token_letters or not w:
            return False

        if token_letters == w or w in token_letters:
            return True

        md = max_edits(w)
        if md == 0:
            return False

        L = len(w)
        for k in (-1, 0, 1):
            L2 = L + k
            if L2 < 3 or len(token_letters) < L2:
                continue
            for i in range(0, len(token_letters) - L2 + 1):
                sub = token_letters[i:i + L2]
                if levenshtein_cutoff(w, sub, md) <= md:
                    return True

        return False

    def stream_hits(text_letters: str, w: str) -> bool:
        if not text_letters or not w:
            return False

        if w in text_letters:
            return True

        md = max_edits(w)
        if md == 0:
            return False

        L = len(w)
        for k in (-2, -1, 0, 1, 2):
            L2 = L + k
            if L2 < 3 or len(text_letters) < L2:
                continue
            for i in range(0, len(text_letters) - L2 + 1):
                sub = text_letters[i:i + L2]
                if levenshtein_cutoff(w, sub, md) <= md:
                    return True

        return False

    # --- main logic ---
    text = re.sub(r"\s*\.?\s*The word is not \w+\.?", "", text or "", flags=re.IGNORECASE)
    norm = normalize_for_matching(text)

    tokens = WORDLIKE_RE.findall(norm)
    token_letters_list = [letters_only(t) for t in tokens if t]
    stream_letters_all = letters_only(norm)

    found: List[str] = []
    for fw in forbidden_words:
        hit_fw = False
        for w in variants(fw):
            if any(token_hits(t, w) for t in token_letters_list) or stream_hits(stream_letters_all, w):
                found.append(fw)
                hit_fw = True
                break

        print("Found forbidden words:", found)
        if hit_fw and len(found) > max_words:
            return True, found

    return False, found



# ============================================================================
# FINAL REFEREE (calls rule-based minimal + AI-based main)
# ============================================================================

def referee_check_description(
    description: str,
    *,
    actor: str,
    secret_word: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = "medium",
    llm_complete_func=None,
    forbidden_words: Optional[List[str]] = None
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Main referee function:
    - keeps forbidden word check here (fast)
    - runs minimal rule-based check: exact secret word boundary
    - runs AI-based referee for everything else (main system)
    """
    print(f"\n{'#'*60}\nREFEREE CHECK DESCRIPTION\n{'#'*60}\n")
    secret_word = secret_word or ""
    category = category or "food"
    difficulty = difficulty or "medium"

    # 1) forbidden words first (fast)
    desc, hint = _split_desc_hint(description)

    desc = (desc or "").strip()
    print(f"Original description before forbidden check: {desc}")
    desc = re.sub(r"(?is)\s*\.?\s*the word is not\b.*$", "", desc).strip()
    print(f"Cleaned description for forbidden words check: {desc}")
    if forbidden_words:
        if hint is None:
            violated, found = check_forbidden_words(desc, forbidden_words, max_words=0)
            if violated:
                return False, [{
                    "code": "FORBIDDEN_WORD_USED",
                    "message": f"You used forbidden word(s): {found}",
                    "severity": "high",
                    "forbidden_word": found[0] if found else None
                }]
        else:
            violated, found = check_forbidden_words(hint, forbidden_words, max_words=1)
            if violated:
                return False, [{
                    "code": "FORBIDDEN_WORD_USED",
                    "message": "You used more than one forbidden word in your hint.",
                    "severity": "high",
                }]

    # 2) minimal rule-based: exact word leak
    rule_ok, rule_violations = rule_based_referee_check(
        description=description,
        secret_word=secret_word
    )
    if not rule_ok:
        return False, rule_violations

    # 3) AI-based referee (main)
    if llm_complete_func is None:
        return False, [{
            "code": "REFEREE_ERROR",
            "message": "AI referee is not available.",
            "severity": "high"
        }]

    return ai_based_referee_check(
        description=description,
        secret_word=secret_word,
        category=category,
        difficulty=difficulty,
        llm_complete_func=llm_complete_func,
        forbidden_words=forbidden_words
    )




# ✅ UPDATED: next_action_number instead of next_turn_number
def next_action_number(db, round_id: int) -> int:
    """Get the next action number for a round."""
    row = db.execute(
        "SELECT COALESCE(MAX(action_number), 0) + 1 AS next_num FROM Actions WHERE round_id = ?",
        (round_id,)
    ).fetchone()
    return int(row["next_num"])



# ============================================================================
# WORD EQUIVALENCE CHECKER
# ============================================================================
import inflect
_inflect = inflect.engine()

_EQ_CACHE = {}
_EQ_LOCK = threading.Lock()


def _basic_norm(s: str) -> str:
    s = (s or "").strip().lower()

    # normalize
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # remove apostrophes
    s = re.sub(r"[\u2019\u2018']", "", s)

    # separators -> space
    s = re.sub(r"[-_/]", " ", s)

    # remove other punctuation/symbols
    s = re.sub(r"[^a-z0-9\s]", " ", s)

    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _join(s: str) -> str:
    return re.sub(r"\s+", "", s)


def singularize_word(word: str) -> str:
    w = (word or "").strip()
    if not w:
        return w
    s = _inflect.singular_noun(w)
    return s if s else w


def _deterministic_equiv(guess: str, answer: str) -> bool:
    g = _basic_norm(guess)
    a = _basic_norm(answer)
    if not g or not a:
        return False

    if g == a:
        return True

    # spacing/hyphenation differences
    if _join(g) == _join(a):
        return True

    # plural/singular token-wise
    gt = [singularize_word(t) for t in g.split()]
    at = [singularize_word(t) for t in a.split()]

    if " ".join(gt) == " ".join(at):
        return True

    if _join(" ".join(gt)) == _join(" ".join(at)):
        return True

    return False


def _ai_equiv(guess_norm: str, answer_norm: str, llm_complete_func) -> bool:
    """
    AI fallback for:
    - UK/US spelling variants
    - minor typos
    - pluralization edge cases
    Strictly NOT synonyms.
    """
    prompt = f"""
You are a strict word-equivalence judge.

Decide if GUESS is the SAME WORD/PHRASE as ANSWER, written differently.

SAME only if:
- UK/US spelling variants (centre/center, realise/realize, colour/color)
- plural/singular (child/children)
- spacing/hyphenation (ice cream/ice-cream/icecream)
- very minor typo (1-2 chars)

NOT SAME:
- synonyms (sofa/couch)
- related words (duck/goose)
- categories (animal/duck)
- translations

GUESS: "{guess_norm}"
ANSWER: "{answer_norm}"

Return ONLY:
<json>{{"same": true}}</json>
or
<json>{{"same": false}}</json>
""".strip()

    raw = llm_complete_func(prompt, temperature=0.0, max_tokens=20)
    obj = _extract_json(raw)
    return bool(obj and obj.get("same") is True)


def words_are_equivalent(
    guess: str,
    answer: str,
    llm_complete_func,
    *,
    use_ai_fallback: bool = True,
) -> bool:
    # 1) deterministic first (fast)
    if _deterministic_equiv(guess, answer):
        return True

    print("GUESS, ANSWER:", guess, answer)
    g = _basic_norm(guess)
    a = _basic_norm(answer)
    if not g or not a:
        return False

    # 3) extra deterministic try: singularize whole phrase (cheap)
    g_s = " ".join(singularize_word(t) for t in g.split())
    a_s = " ".join(singularize_word(t) for t in a.split())

    # 4) AI fallback (UK/US spellings etc.)
    print("GUESS, ANSWER:", g_s, a_s)
    if use_ai_fallback:
        same = _ai_equiv(g_s, a_s, llm_complete_func)
        return same


# ============================================================================
# ADAPTIVE DIFFICULTY SYSTEM (3 LEVELS)
# ============================================================================

# ✅ UPDATED: 9 difficulty levels (was 3)
DIFFICULTY_LEVELS = [
    "easy1", "easy2", "easy3",
    "medium1", "medium2", "medium3",
    "hard1", "hard2", "hard3"
]

def get_current_difficulty(db, game_id: int) -> str:
    game = db.execute(
        'SELECT current_difficulty FROM Games WHERE game_id = ?',
        (game_id,)
    ).fetchone()

    if game and game['current_difficulty']:
        level = game['current_difficulty']
        _LEGACY_MAP = {"easy": "easy1", "medium": "medium1", "hard": "hard1"}
        return _LEGACY_MAP.get(level, level)

    return "easy1"


def calculate_next_difficulty(
    db,
    game_id: int,
    round_number: int
) -> str:
    current_level = get_current_difficulty(db, game_id)
    current_index = (
        DIFFICULTY_LEVELS.index(current_level)
        if current_level in DIFFICULTY_LEVELS
        else 0
    )

    if round_number % 2 != 0:
        return current_level

    user_guesses_round = round_number - 1
    ai_guesses_round = round_number

    print(f"\n{'='*80}")
    print(f"🔍 DIFFICULTY CALCULATION — 9-LEVEL SYSTEM")
    print(f"{'='*80}")
    print(f"Game ID:          {game_id}")
    print(f"Round Number:     {round_number}")
    print(f"Current Level:    {current_level} (index {current_index})")
    print(f"Pair being checked:")
    print(f"  Round {user_guesses_round} (AI describes → user guesses)")
    print(f"  Round {ai_guesses_round} (User describes → AI guesses)")

    player_win_row = db.execute('''
        SELECT round_number, outcome, secret_word
        FROM Rounds
        WHERE game_id = ?
          AND round_number = ?
          AND game_mode = 'user_guesses'
          AND outcome = 'win'
    ''', (game_id, user_guesses_round)).fetchone()

    player_win = 1 if player_win_row else 0

    ai_win_row = db.execute('''
        SELECT round_number, outcome, secret_word
        FROM Rounds
        WHERE game_id = ?
          AND round_number = ?
          AND game_mode = 'ai_guesses'
          AND outcome = 'win'
    ''', (game_id, ai_guesses_round)).fetchone()

    ai_win = 1 if ai_win_row else 0

    total_wins = player_win + ai_win

    print(f"\n📊 Results:")
    print(f"  Player win (round {user_guesses_round}): {'✅ YES' if player_win else '❌ NO'}")
    print(f"  AI win    (round {ai_guesses_round}): {'✅ YES' if ai_win else '❌ NO'}")
    print(f"  Total wins: {total_wins}/2")

    if total_wins == 2:
        new_index = min(current_index + 1, len(DIFFICULTY_LEVELS) - 1)
        reason = "Both correct → increase difficulty"
    elif total_wins == 1:
        new_index = current_index
        reason = "One correct → stay same"
    else:
        new_index = max(current_index - 1, 0)
        reason = "Neither correct → decrease difficulty"

    new_level = DIFFICULTY_LEVELS[new_index]

    print(f"\n🎯 DECISION: {reason}")
    print(f"  Old difficulty: {current_level}")
    print(f"  New difficulty: {new_level}")
    print(f"  Changed: {'YES ✅' if new_level != current_level else 'NO ➡️'}")
    print(f"{'='*80}\n")

    return new_level

def update_game_difficulty(db, game_id: int, new_difficulty: str):
    db.execute('''
        UPDATE Games
        SET current_difficulty = ?
        WHERE game_id = ?
    ''', (new_difficulty, game_id))
    db.commit()
    print(f"📊 Difficulty updated for game {game_id}: → {new_difficulty}")


# ============================================================================
# AI WORD SELECTION (PREVENTS REPETITION)
# ============================================================================

def select_word_for_round(
    db,
    game_id: int,
    category: str,
    difficulty: str,
    word_data: List[Dict[str, Any]]
) -> Optional[str]:
    import random

    used_words = db.execute('''
        SELECT DISTINCT secret_word 
        FROM Rounds 
        WHERE game_id = ?
    ''', (game_id,)).fetchall()

    used_word_set = {row['secret_word'].lower() for row in used_words}
    used_word_list = sorted(used_word_set)

    candidates = [
        item["word"]
        for item in word_data
        if item["difficulty"].lower() == difficulty.lower()
        and item["category"].lower() == category.lower()
        and item["word"].lower() not in used_word_set
    ]

    if not candidates:
        print(f"⚠️ No unused words found for {category}/{difficulty}. Allowing repetition.")
        candidates = [
            item["word"]
            for item in word_data
            if item["difficulty"].lower() == difficulty.lower()
            and item["category"].lower() == category.lower()
        ]

    if not candidates:
        return None

    round_number_row = db.execute(
        'SELECT COUNT(*) as count FROM Rounds WHERE game_id = ? AND outcome IS NOT NULL',
        (game_id,)
    ).fetchone()
    current_round = (round_number_row['count'] + 1) if round_number_row else 1
    prompt = f"""You are a word selection referee for a word-guessing game.

GAME STATE:
- Round: {current_round} of 18
- Category: {category}
- Difficulty: {difficulty}
- Words already used this game: {json.dumps(used_word_list) if used_word_list else "none yet"}

CANDIDATE WORDS (you MUST pick exactly one from this list):
{json.dumps(candidates)}

Pick the best word considering:
1. Semantic diversity: pick a word that is different from the words already used (avoid similar animals, similar foods, etc.)
2. Describability: pick a word with distinctive features that makes the game fun and engaging
3. Appropriate challenge: the word should be interesting to describe and guess at the "{difficulty}" difficulty level

Return ONLY the chosen word in JSON tags:
<json>{{"word": "chosen_word"}}</json>""".strip()

    '''try:
        print(f"🤖 AI word selection: asking AI to pick from {len(ai_candidates)} candidates...")
        raw = llm_complete_fastest(prompt, temperature=0.3, max_tokens=30)
        print(f"🤖 AI raw response: {raw}")

        result = _extract_json(raw)

        if result and "word" in result:
            ai_pick = result["word"].strip()

            if ai_pick.lower() in {c.lower() for c in candidates}:
                selected = next(c for c in candidates if c.lower() == ai_pick.lower())
                print(f"🎯 AI selected word: '{selected}' (category: {category}, difficulty: {difficulty})")
                return selected
            else:
                print(f"⚠️ AI picked '{ai_pick}' which is not in candidate list. Falling back to random.")
        else:
            print(f"⚠️ AI returned invalid JSON. Falling back to random.")

    except Exception as e:
        print(f"⚠️ AI word selection failed: {e}. Falling back to random.")'''

    selected = random.choice(candidates)
    return selected




def close_unfinished_games(db, user_id: int):
    db.execute(
        """UPDATE Games 
           SET outcome = 'abandoned', ended_at = CURRENT_TIMESTAMP 
           WHERE user_id = ? AND outcome IS NULL""",
        (user_id,)
    )
    db.commit()
    print(f"🧹 Closed all unfinished games for user {user_id}")


def create_new_game(db, user_id: int, username: str, difficulty: str = "easy1") -> int:
    close_unfinished_games(db, user_id)
    cursor = db.execute(
        'INSERT INTO Games (user_id, username_at_game_time, current_difficulty) VALUES (?, ?, ?)',
        (user_id, username, difficulty)
    )
    db.commit()
    new_game_id = cursor.lastrowid
    print(f"🆕 Created new game: game_id={new_game_id}, difficulty={difficulty}")
    return new_game_id


def get_active_game(db, user_id: int) -> int:
    game = db.execute(
        'SELECT game_id FROM Games WHERE user_id = ? AND outcome IS NULL ORDER BY started_at DESC LIMIT 1',
        (user_id,)
    ).fetchone()
    if game:
        return game['game_id']
    return None


def get_or_create_game(db, user_id: int, username: str, difficulty: str, new_game: bool = False) -> int:
    if new_game:
        db.execute(
            "UPDATE Games SET outcome = 'abandoned', ended_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND outcome IS NULL",
            (user_id,)
        )
        db.commit()
        print(f"🧹 Closed all unfinished games for user {user_id}")

        cursor = db.execute(
            'INSERT INTO Games (user_id, username_at_game_time, current_difficulty) VALUES (?, ?, ?)',
            (user_id, username, difficulty)
        )
        db.commit()
        new_id = cursor.lastrowid
        print(f"🆕 Created new game: game_id={new_id}, difficulty={difficulty}")
        return new_id

    game = db.execute(
        'SELECT game_id FROM Games WHERE user_id = ? AND outcome IS NULL ORDER BY started_at DESC LIMIT 1',
        (user_id,)
    ).fetchone()

    if game:
        print(f"📎 Resuming existing game: game_id={game['game_id']}")
        return game['game_id']

    cursor = db.execute(
        'INSERT INTO Games (user_id, username_at_game_time, current_difficulty) VALUES (?, ?, ?)',
        (user_id, username, difficulty)
    )
    db.commit()
    new_id = cursor.lastrowid
    print(f"🆕 Created new game (no open game found): game_id={new_id}, difficulty={difficulty}")
    return new_id


def get_next_round_number(db, game_id: int) -> int:
    result = db.execute(
        'SELECT COUNT(*) as count FROM Rounds WHERE game_id = ?',
        (game_id,)
    ).fetchone()
    return result['count'] + 1


def get_or_create_round(db, game_id: int, round_number: int, secret_word: str,
                         category: str, difficulty: str, game_mode: str) -> int:
    existing = db.execute(
        'SELECT round_id, outcome, game_mode FROM Rounds WHERE game_id = ? AND round_number = ?',
        (game_id, round_number)
    ).fetchone()

    if existing:
        if existing['outcome'] is not None:
            correct_next = db.execute(
                'SELECT COUNT(*) as count FROM Rounds WHERE game_id = ?',
                (game_id,)
            ).fetchone()['count'] + 1
            print(f"⚠️ Round {round_number} already completed, creating round {correct_next} instead")
            cursor = db.execute(
                'INSERT INTO Rounds (game_id, round_number, secret_word, category, difficulty, game_mode) VALUES (?, ?, ?, ?, ?, ?)',
                (game_id, correct_next, secret_word, category, difficulty, game_mode)
            )
            db.commit()
            return cursor.lastrowid
        elif existing['game_mode'] == game_mode:
            print(f"🔄 Updating existing round {round_number} (Change Word): {secret_word}")
            db.execute(
                'UPDATE Rounds SET secret_word = ?, category = ?, difficulty = ? WHERE round_id = ?',
                (secret_word, category, difficulty, existing['round_id'])
            )
            db.commit()
            return existing['round_id']
        else:
            correct_next = db.execute(
                'SELECT COUNT(*) as count FROM Rounds WHERE game_id = ?',
                (game_id,)
            ).fetchone()['count'] + 1
            print(f"➕ Creating new round {correct_next} (mode mismatch at {round_number}): {secret_word} ({game_mode})")
            cursor = db.execute(
                'INSERT INTO Rounds (game_id, round_number, secret_word, category, difficulty, game_mode) VALUES (?, ?, ?, ?, ?, ?)',
                (game_id, correct_next, secret_word, category, difficulty, game_mode)
            )
            db.commit()
            return cursor.lastrowid
    else:
        print(f"➕ Creating new round {round_number}: {secret_word} ({game_mode})")
        cursor = db.execute(
            'INSERT INTO Rounds (game_id, round_number, secret_word, category, difficulty, game_mode) VALUES (?, ?, ?, ?, ?, ?)',
            (game_id, round_number, secret_word, category, difficulty, game_mode)
        )
        db.commit()
        return cursor.lastrowid


def forbidden_words_prompt(secret_word: str, category: str) -> str:
    prompt = f"""Generate exactly 5 words closely related to "{secret_word}" (category: {category}).

        Requirements:
        - Directly related to the secret word
        - Would make guessing too easy if used, narrows it down to the secret word
        - NOT the secret word itself
        - NOT morphological variations (plurals, verb forms)
        - Maybe synonyms
        - Don't provide colors, categories, or very broad associations
        - Don't provide generic words like sweet, big, small, etc.
        - Has 4 letters or more (to avoid very generic short words)

        Provide very close words, not their category, rather something that makes you immediately think of this word.
        Example: Don't say "fruit" for "apple", say "orchard", "cider", "core", "pie". 


        Return ONLY a JSON array:
        ["word1", "word2", "word3", "word4", "word5"]""".strip()
    return prompt
