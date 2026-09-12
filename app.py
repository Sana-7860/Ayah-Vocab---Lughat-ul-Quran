"""
app.py -- AyahVocab home page

Tier selector + short description of each tier + Continue Learning button.
Owned by: Member 3 (App Shell / Gamification Dev)
"""

import streamlit as st
from gamification import GameState, render_top_bar

st.set_page_config(page_title="AyahVocab", page_icon="📖", layout="wide")

# Initialize (or attach to) game state and update the daily streak
gs = GameState()
gs.update_streak()

render_top_bar()

st.title("📖 AyahVocab — Lughat ul Quran")
st.subheader("Learn the words that unlock 85% of the Qur'an.")

st.markdown("---")

tier_info = {
    50: {
        "label": "Tier 1 — 50%",
        "desc": "The 250 most frequent roots. Daily flashcards + a 10-question quiz. "
                "Goal: recognize half the words on any given page.",
    },
    65: {
        "label": "Tier 2 — 65%",
        "desc": "~400 roots. Adaptive repetition kicks in -- wrong answers return sooner. "
                "Hearts limit careless guessing.",
    },
    85: {
        "label": "Tier 3 — 85%",
        "desc": "~500 roots. AI diagnosis is active on every miss. Word Doctor chat unlocks. "
                "Mastery badge earned.",
    },
}

cols = st.columns(3)
for col, (tier, info) in zip(cols, tier_info.items()):
    with col:
        st.markdown(f"### {info['label']}")
        st.write(info["desc"])
        if st.button(f"Continue Learning ({tier}%)", key=f"tier_btn_{tier}"):
            st.session_state["selected_tier"] = tier
            st.success(f"Tier {tier}% selected. Open the **Learn** page from the sidebar to start.")

st.markdown("---")
st.caption(
    "Use the sidebar to move between Learn (flashcards), Quiz, Progress, and Word Doctor."
)
