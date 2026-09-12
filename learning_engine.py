"""
learning_engine.py

Hackathon Learning Engine
-------------------------
Responsibilities:
1. Track mastery for every vocabulary word.
2. Implement a simple 5-box spaced-repetition system.
3. Select the next word for review.
4. Update progress after correct/wrong answers.
5. Log wrong answers for AI diagnosis.
6. Calculate tier progress: seen vs mastered.

This module is intentionally independent of Streamlit, Groq,
Google Sheets, or any frontend/database implementation.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


# =========================================================
# CONFIGURATION
# =========================================================

BOX_COOLDOWN = {
    1: 1,   # Weak / New
    2: 2,   # Learning
    3: 4,   # Improving
    4: 8,   # Mastered
    5: 16   # Strongly Mastered
}

MASTERY_BOX = 4
MIN_BOX = 1
MAX_BOX = 5


# =========================================================
# CREATE ENGINE STATE
# =========================================================

def create_engine_state() -> Dict[str, Any]:
    """Create a fresh learning state."""
    return {
        "word_state": {},
        "wrong_answers_log": [],
        "interaction_count": 0
    }


# =========================================================
# INITIALIZE INDIVIDUAL WORD STATE
# =========================================================

def ensure_word_state(
    engine_state: Dict[str, Any],
    word_id: str
) -> Dict[str, Any]:
    """Ensure that a vocabulary word has a learning-state record."""

    if word_id not in engine_state["word_state"]:
        engine_state["word_state"][word_id] = {
            "box": 1,
            "correct_count": 0,
            "wrong_count": 0,
            "seen_count": 0,
            "last_seen": None,
            "next_due_interaction": 0
        }

    return engine_state["word_state"][word_id]


# =========================================================
# FIND VOCABULARY WORD
# =========================================================

def find_word(
    vocabulary: List[Dict[str, Any]],
    word_id: str
) -> Optional[Dict[str, Any]]:
    """Find one vocabulary record using its permanent ID."""

    return next(
        (word for word in vocabulary if word.get("id") == word_id),
        None
    )


# =========================================================
# GET NEXT WORD
# =========================================================

def get_next_word(
    vocabulary: List[Dict[str, Any]],
    engine_state: Dict[str, Any],
    tier: str
) -> Optional[Dict[str, Any]]:
    """
    Select the next word that should be shown to the learner.

    Priority:
    1. Correct tier
    2. Word must be due
    3. Lowest box first
    4. Least-seen word first
    5. Highest wrong-count if otherwise equal
    """

    current_interaction = engine_state["interaction_count"]
    candidates = []

    for word in vocabulary:

        if str(word.get("tier")) != str(tier):
            continue

        word_id = word.get("id")

        if not word_id:
            continue

        state = ensure_word_state(engine_state, word_id)

        if current_interaction >= state["next_due_interaction"]:
            candidates.append({
                "word": word,
                "state": state
            })

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item["state"]["box"],
            item["state"]["seen_count"],
            -item["state"]["wrong_count"]
        )
    )

    return candidates[0]["word"]


# =========================================================
# SUBMIT ANSWER
# =========================================================

def submit_answer(
    vocabulary: List[Dict[str, Any]],
    engine_state: Dict[str, Any],
    word_id: str,
    is_correct: bool,
    user_answer: str = "",
    correct_answer: str = ""
) -> Dict[str, Any]:
    """
    Update a word after the learner submits an answer.

    Correct answer:
        Move up one box.

    Wrong answer:
        Reset to Box 1 and log the mistake.
    """

    word = find_word(vocabulary, word_id)

    if word is None:
        raise ValueError(f"Unknown word_id: {word_id}")

    state = ensure_word_state(engine_state, word_id)

    engine_state["interaction_count"] += 1
    current_interaction = engine_state["interaction_count"]

    state["seen_count"] += 1
    state["last_seen"] = datetime.now(timezone.utc).isoformat()

    if is_correct:

        state["correct_count"] += 1

        state["box"] = min(
            MAX_BOX,
            state["box"] + 1
        )

    else:

        state["wrong_count"] += 1
        state["box"] = MIN_BOX

        error_record = {
            "word_id": word_id,
            "word_ar": word.get("word_ar", ""),
            "meaning_en": word.get("meaning_en", ""),
            "pos": word.get("pos", ""),
            "root": word.get("root", ""),
            "tier": word.get("tier", ""),
            "user_answer": user_answer,
            "correct_answer": correct_answer or word.get("meaning_en", ""),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        engine_state["wrong_answers_log"].append(error_record)

    cooldown = BOX_COOLDOWN[state["box"]]

    state["next_due_interaction"] = (
        current_interaction + cooldown
    )

    return state


# =========================================================
# TIER COMPLETION
# =========================================================

def tier_completion(
    vocabulary: List[Dict[str, Any]],
    engine_state: Dict[str, Any],
    tier: str
) -> Dict[str, Any]:
    """
    Calculate learning progress for one tier.

    Seen:
        Learner attempted the word at least once.

    Mastered:
        Word currently has Box >= 4.
    """

    tier_words = [
        word
        for word in vocabulary
        if str(word.get("tier")) == str(tier)
    ]

    total_words = len(tier_words)

    if total_words == 0:
        return {
            "tier": str(tier),
            "total_words": 0,
            "seen_words": 0,
            "learning_words": 0,
            "mastered_words": 0,
            "seen_percentage": 0.0,
            "mastered_percentage": 0.0
        }

    seen_words = 0
    mastered_words = 0

    for word in tier_words:

        word_id = word.get("id")

        if not word_id:
            continue

        state = ensure_word_state(engine_state, word_id)

        if state["seen_count"] > 0:
            seen_words += 1

        if state["box"] >= MASTERY_BOX:
            mastered_words += 1

    learning_words = seen_words - mastered_words

    return {
        "tier": str(tier),
        "total_words": total_words,
        "seen_words": seen_words,
        "learning_words": learning_words,
        "mastered_words": mastered_words,
        "seen_percentage": round((seen_words / total_words) * 100, 1),
        "mastered_percentage": round((mastered_words / total_words) * 100, 1)
    }


# =========================================================
# GET WEAK WORDS
# =========================================================

def get_weak_words(
    vocabulary: List[Dict[str, Any]],
    engine_state: Dict[str, Any],
    tier: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Return the learner's weakest attempted words.

    Useful for:
    - AI diagnosis
    - Revision recommendations
    - Weak-area dashboard
    """

    results = []

    for word in vocabulary:

        if tier is not None and str(word.get("tier")) != str(tier):
            continue

        word_id = word.get("id")

        if not word_id:
            continue

        state = ensure_word_state(engine_state, word_id)

        if state["seen_count"] == 0:
            continue

        results.append({
            **word,
            "learning_state": {
                **state
            }
        })

    results.sort(
        key=lambda item: (
            item["learning_state"]["box"],
            -item["learning_state"]["wrong_count"],
            item["learning_state"]["correct_count"]
        )
    )

    return results[:limit]


# =========================================================
# GET RECENT WRONG ANSWERS
# =========================================================

def get_recent_wrong_answers(
    engine_state: Dict[str, Any],
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Return recent errors for the AI diagnosis module."""

    return engine_state["wrong_answers_log"][-limit:]


# =========================================================
# GET WORD STATUS
# =========================================================

def get_word_status(
    engine_state: Dict[str, Any],
    word_id: str
) -> Dict[str, Any]:
    """Get learning information for one word."""

    state = ensure_word_state(engine_state, word_id)
    box = state["box"]

    if box == 1:
        status = "Weak / New"
    elif box == 2:
        status = "Learning"
    elif box == 3:
        status = "Improving"
    elif box == 4:
        status = "Mastered"
    else:
        status = "Strongly Mastered"

    return {
        **state,
        "status": status,
        "is_mastered": box >= MASTERY_BOX
    }


# =========================================================
# OPTIONAL RESET FUNCTION
# =========================================================

def reset_word(
    engine_state: Dict[str, Any],
    word_id: str
) -> Dict[str, Any]:
    """Reset one word to its initial state."""

    engine_state["word_state"][word_id] = {
        "box": 1,
        "correct_count": 0,
        "wrong_count": 0,
        "seen_count": 0,
        "last_seen": None,
        "next_due_interaction": 0
    }

    return engine_state["word_state"][word_id]
