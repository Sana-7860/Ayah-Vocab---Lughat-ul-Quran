"""
gamification.py
----------------
Self-contained gamification layer for AyahVocab.

Holds a GameState class that is backed by st.session_state so its values
survive across page switches during a single browser session (Streamlit
reruns the whole script on every interaction, so anything that needs to
persist must live in st.session_state rather than a plain Python variable).

Owned by: Member 3 (App Shell / Gamification Dev)
"""

import datetime
import streamlit as st

MAX_HEARTS = 5
XP_PER_CORRECT = 10
XP_STREAK_BONUS = 2

# Badge thresholds tied to tier completion
TIER_BADGES = {
    50: "50% Club",
    65: "65% Club",
    85: "85% Master",
}

# League order, mapped to the highest tier a learner has made real progress in
LEAGUE_ORDER = ["Bronze", "Silver", "Gold"]


class GameState:
    """
    Wraps st.session_state so the rest of the app can call simple methods
    like add_xp(10) instead of poking session_state dict keys everywhere.
    Call GameState() once at the top of any page -- it will either create
    fresh state (first run) or attach to the existing state (later runs).
    """

    def __init__(self):
        defaults = {
            "xp": 0,
            "hearts": MAX_HEARTS,
            "streak_days": 0,
            "last_active_date": None,
            "badges": [],
            "current_league": "Bronze",
            "wrong_answers_log": [],  # filled in by Member 4/5's code
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    # ---- XP ----
    def add_xp(self, amount: int):
        st.session_state["xp"] += amount

    # ---- Hearts ----
    def lose_heart(self):
        if st.session_state["hearts"] > 0:
            st.session_state["hearts"] -= 1

    def regain_hearts(self, amount: int = MAX_HEARTS):
        st.session_state["hearts"] = min(MAX_HEARTS, st.session_state["hearts"] + amount)

    # ---- Streak ----
    def update_streak(self):
        today = datetime.date.today()
        last = st.session_state["last_active_date"]

        if last is None:
            st.session_state["streak_days"] = 1
        elif last == today:
            pass  # already counted today, do nothing
        elif last == today - datetime.timedelta(days=1):
            st.session_state["streak_days"] += 1
            self.add_xp(XP_STREAK_BONUS)
        else:
            st.session_state["streak_days"] = 1  # streak broken, restart

        st.session_state["last_active_date"] = today

    # ---- Badges ----
    def award_badge(self, name: str):
        if name not in st.session_state["badges"]:
            st.session_state["badges"].append(name)

    def check_tier_badge(self, tier: int, percent_mastered: float):
        """Call this after updating progress -- awards a badge automatically
        once a tier is fully mastered (100%)."""
        if percent_mastered >= 100 and tier in TIER_BADGES:
            self.award_badge(TIER_BADGES[tier])

    # ---- League ----
    def get_league(self) -> str:
        return st.session_state["current_league"]

    def set_league(self, tier_reached: int):
        mapping = {50: "Bronze", 65: "Silver", 85: "Gold"}
        st.session_state["current_league"] = mapping.get(tier_reached, "Bronze")

    # ---- Wrong-answer log (handoff point to Member 5's AI layer) ----
    def log_wrong_answer(self, entry: dict):
        """entry shape agreed with Member 4/5:
        {word_id, word_ar, meaning_en, pos, root, user_answer, correct_answer, timestamp}
        """
        st.session_state["wrong_answers_log"].append(entry)


def render_top_bar():
    """Shows hearts / XP / streak at the top of every page. Call this first
    thing in app.py and every page under pages/."""
    gs = GameState()
    hearts_display = "❤️" * st.session_state["hearts"] + "🤍" * (MAX_HEARTS - st.session_state["hearts"])

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(f"### {hearts_display}")
    col2.markdown(f"**⚡ XP:** {st.session_state['xp']}")
    col3.markdown(f"**🔥 Streak:** {st.session_state['streak_days']} days")
    col4.markdown(f"**🏆 League:** {gs.get_league()}")
    st.divider()
