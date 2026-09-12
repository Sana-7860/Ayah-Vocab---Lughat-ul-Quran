"""
ai_layer.py
-----------
Member 5's module: the AI differentiator for AyahVocab.

NOTE: originally built against xAI's Grok API. Since the team's Grok
account had no credits and xAI charges from the first token with no
free tier, this now points at Groq (api.groq.com) instead -- a
free-tier, OpenAI-compatible provider. Function names/behavior are
unchanged; only the base_url, key env var, and model name changed.
Flag this swap to whoever owns the pitch deck/README since the plan
names "Grok" explicitly.

Uses an OpenAI-compatible chat completions client to power three functions:

  1. diagnose_weakness(wrong_answers_log)
       -> finds the PATTERN behind a learner's mistakes, not just a list
          of missed words. Returns {"diagnosis": str, "recommended_word_ids": [...]}

  2. generate_example(word_dict)
       -> fresh Qur'anic-style example sentence + one-line grammar/root note
          for a single word. Cached per word id to avoid repeat API calls.

  3. word_doctor_chat(user_question, word_bank_context)
       -> scoped Q&A chat, answers only about Qur'anic vocabulary/grammar.

All three wrap API calls in try/except, retry once on timeout, and
return a friendly fallback so the Streamlit demo never crashes mid-pitch.

Setup
-----
pip install openai
Get a free key at https://console.groq.com (no card required) and either:
  - set it as an env var: export GROQ_API_KEY="..."
  - or (for Streamlit Cloud) add it as a secret and read via st.secrets,
    then pass it into get_client() -- see the note at the bottom.
"""

import json
import os
import time

from openai import OpenAI, APITimeoutError, APIError

GROK_API_KEY = os.environ.get("GROQ_API_KEY", "YOUR_KEY_HERE")
GROK_BASE_URL = "https://api.groq.com/openai/v1"
GROK_MODEL = "openai/gpt-oss-20b"  # confirmed available on this account's Groq key

# Simple in-memory cache: word id -> example dict. Session-lifetime only,
# which is fine for a hackathon demo (Streamlit reruns keep module-level
# state alive within the same process).
_EXAMPLE_CACHE = {}


def get_client(api_key: str = None) -> OpenAI:
    """
    Returns an OpenAI-compatible client pointed at Grok's endpoint.
    Pass api_key explicitly when calling from Streamlit so you can do
    get_client(st.secrets["GROQ_API_KEY"]) instead of relying on the env var.
    """
    return OpenAI(api_key=api_key or GROK_API_KEY, base_url=GROK_BASE_URL)


def _call_with_retry(client: OpenAI, **kwargs):
    """Retry once on timeout; let other exceptions propagate to the caller."""
    try:
        return client.chat.completions.create(**kwargs)
    except APITimeoutError:
        time.sleep(1)
        return client.chat.completions.create(**kwargs)


def _extract_json(text: str) -> dict:
    """
    Grok sometimes wraps JSON in ```json fences or adds stray text.
    Strip fences and find the first {...} block before parsing.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("json", "", 1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    return json.loads(cleaned[start : end + 1])


# ----------------------------------------------------------------------
# 1. Weakness diagnosis
# ----------------------------------------------------------------------

def diagnose_weakness(wrong_answers_log: list, client: OpenAI = None) -> dict:
    """
    wrong_answers_log: list of dicts like
        {word_id, word_ar, meaning_en, pos, root, user_answer,
         correct_answer, timestamp}

    Returns: {"diagnosis": str, "recommended_word_ids": [str, ...]}
    This is the demo's money moment -- show this on screen live.
    """
    fallback = {
        "diagnosis": "Couldn't reach the diagnosis engine right now — keep practicing and try again shortly.",
        "recommended_word_ids": [],
    }
    if not wrong_answers_log:
        return {"diagnosis": "No mistakes logged yet — nothing to diagnose!", "recommended_word_ids": []}

    client = client or get_client()

    system_prompt = (
        "You are a Qur'anic-vocabulary tutor's diagnostic assistant. You will be given "
        "a log of a learner's incorrect answers. Do NOT just restate the mistakes. "
        "Find the underlying PATTERN behind them — e.g. confusing similar-looking words, "
        "weakness on a specific root family, weakness on a part of speech (particles, "
        "verb forms, hollow verbs), or knowing a word in isolation but failing it in "
        "context. Respond with ONLY a JSON object, no other text, in this exact shape: "
        '{"diagnosis": "1-2 plain-English sentences", "recommended_word_ids": ["w0001", ...]}. '
        "recommended_word_ids must be a subset of the word_id values present in the log, "
        "at most 5 of them, chosen because they best represent the pattern."
    )

    user_prompt = (
        "Here is the wrong-answer log:\n\n"
        + json.dumps(wrong_answers_log, ensure_ascii=False, indent=2)
    )

    try:
        response = _call_with_retry(
            client,
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            timeout=20,
        )
        text = response.choices[0].message.content
        parsed = _extract_json(text)
        if "diagnosis" not in parsed or "recommended_word_ids" not in parsed:
            raise ValueError("Malformed diagnosis response")
        return parsed
    except (APITimeoutError, APIError, ValueError, json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[ai_layer] diagnose_weakness failed: {e}")
        return fallback


# ----------------------------------------------------------------------
# 2. Fresh example generator
# ----------------------------------------------------------------------

def generate_example(word_dict: dict, client: OpenAI = None) -> dict:
    """
    word_dict: Member 4's real schema -- {id, word_ar, meaning_en, pos, root, tier}.
    (No transliteration/frequency_rank fields exist in the real data --
    the function works fine without them since it just serializes
    whatever keys are present.)
    Returns: {"example_ar": str, "example_en": str, "note": str}
    Cached per word id so re-rendering a flashcard doesn't re-call the API.
    """
    word_id = word_dict.get("id", word_dict.get("word_ar"))
    if word_id in _EXAMPLE_CACHE:
        return _EXAMPLE_CACHE[word_id]

    fallback = {
        "example_ar": "",
        "example_en": "Example unavailable right now — try again in a moment.",
        "note": "",
    }

    client = client or get_client()

    system_prompt = (
        "You are a Qur'anic-Arabic tutor. Given a single vocabulary word, write ONE "
        "short, simple example sentence in Qur'anic-style Arabic using it naturally, "
        "plus its English translation, and one short line noting the root or "
        "grammatical form if relevant (omit if not applicable). Respond with ONLY "
        "a JSON object: {\"example_ar\": \"...\", \"example_en\": \"...\", \"note\": \"...\"}. "
        "Do not invent a fabricated ayah and present it as a real Qur'anic verse — "
        "write an original illustrative sentence in a similar style instead."
    )
    user_prompt = "Word: " + json.dumps(word_dict, ensure_ascii=False)

    try:
        response = _call_with_retry(
            client,
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            timeout=15,
        )
        text = response.choices[0].message.content
        parsed = _extract_json(text)
        _EXAMPLE_CACHE[word_id] = parsed
        return parsed
    except (APITimeoutError, APIError, ValueError, json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[ai_layer] generate_example failed: {e}")
        return fallback


# ----------------------------------------------------------------------
# 3. Word Doctor chat
# ----------------------------------------------------------------------

def word_doctor_chat(user_question: str, word_bank_context: list, client: OpenAI = None) -> str:
    """
    user_question: free text, e.g. "why does this word mean X here?"
    word_bank_context: a SHORT list of relevant word dicts (pre-filtered by
        simple keyword match against the full word bank -- don't send the
        whole bank here, that wastes tokens and dilutes grounding).
    Returns: a plain string answer (3-4 sentences), or a fallback string.
    """
    fallback = "Sorry, I couldn't reach the Word Doctor right now. Please try again in a moment."

    client = client or get_client()

    system_prompt = (
        "You are 'Word Doctor', a focused Qur'anic-vocabulary and grammar tutor inside "
        "a vocabulary app. Only answer questions about Qur'anic Arabic vocabulary, "
        "roots, grammar, and word meaning. Keep answers concise: 3-4 sentences. "
        "Ground your answer in the provided word list context when relevant, and do "
        "not invent words that aren't in the list. If asked something unrelated to "
        "Qur'anic vocabulary/grammar, respond exactly: \"I'm not sure, that's outside "
        "what I can help with here.\""
    )
    context_str = json.dumps(word_bank_context, ensure_ascii=False)
    user_prompt = f"Relevant word list context:\n{context_str}\n\nLearner's question:\n{user_question}"

    try:
        response = _call_with_retry(
            client,
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            timeout=15,
        )
        return response.choices[0].message.content.strip()
    except (APITimeoutError, APIError, KeyError, IndexError) as e:
        print(f"[ai_layer] word_doctor_chat failed: {e}")
        return fallback


# ----------------------------------------------------------------------
# Quick self-test with fake data
# ----------------------------------------------------------------------

if __name__ == "__main__":
    # Uses GROQ_API_KEY env var, or edit the constant above for a quick local test.
    test_log = [
        {
            "word_id": "w0010",
            "word_ar": "قَامَ",
            "meaning_en": "he stood",
            "pos": "verb",
            "root": "ق و م",
            "user_answer": "he said",
            "correct_answer": "he stood",
            "timestamp": "2026-01-01T10:00:00",
        },
        {
            "word_id": "w0011",
            "word_ar": "نَامَ",
            "meaning_en": "he slept",
            "pos": "verb",
            "root": "ن و م",
            "user_answer": "he woke",
            "correct_answer": "he slept",
            "timestamp": "2026-01-01T10:01:00",
        },
    ]

    print("=== diagnose_weakness ===")
    print(diagnose_weakness(test_log))

    print("\n=== generate_example ===")
    print(generate_example({
        "id": "w0010", "word_ar": "قَامَ", "transliteration": "qaama",
        "meaning_en": "he stood", "root": "ق و م", "pos": "verb",
    }))

    print("\n=== word_doctor_chat ===")
    print(word_doctor_chat(
        "Why is قَامَ considered a hollow verb?",
        [{"word_ar": "قَامَ", "meaning_en": "he stood", "root": "ق و م", "pos": "verb"}],
    ))
