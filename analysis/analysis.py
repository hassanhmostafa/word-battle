"""
Charts for Word-Guess game analytics  (with data labels)
-------------------------------------------------------
1. Average Guess Accuracy: AI vs User  (bar, % plus value on bars)
2. User-selected Categories (bar, integer count on bars)
3. Key Event-type Distribution (pie)
4. Rounds Played per Session (bar, integer count on bars)

Run from the folder that contains word_game.logs.json
>  python game_charts.py
"""

import json
from pathlib import Path
from collections import defaultdict

from matplotlib.ticker import MaxNLocator
import pandas as pd
import matplotlib.pyplot as plt

# ------------- Helper -------------------------------------------------
def add_bar_labels(ax, fmt="{:d}", y_offset=3):
    """
    Attach a text label above each bar displaying its height.
    fmt – a format string like "{:d}" or "{:.1%}"
    y_offset – vertical offset in points
    """
    for bar in ax.patches:
        height = bar.get_height()
        ax.annotate(fmt.format(height),
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, y_offset), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9)

# ------------- Load and flatten the log file --------------------------
log_path = Path("word_game.logs.json")
with log_path.open(encoding="utf-8") as fp:
    raw = json.load(fp)

df = pd.json_normalize(raw)          # flatten nested “details.*” keys
df["ts"] = pd.to_datetime(df["timestamp"])

# ------------- 1. Average Guess Accuracy: AI vs User ------------------
user_guesses = df[df["event"] == "userGuessSubmitted"]
ai_guesses   = df[df["event"] == "aiGuessMade"]

user_acc = user_guesses["details.isCorrect"].mean()
ai_acc   = ai_guesses["details.isCorrect"].mean()

plt.figure(figsize=(5, 4))
ax1 = plt.gca()
bars = ax1.bar(["User", "AI"], [user_acc, ai_acc])
ax1.set_ylim(0, 1)
ax1.set_ylabel("Correct-guess rate")
ax1.set_title("Average Guess Accuracy: AI vs User")

add_bar_labels(ax1, fmt="{:.1%}")    # shows 74.3% etc.
plt.tight_layout()
plt.savefig("average_accuracy.pdf", dpi=300)

# ------------- 2. User-Selected Categories During Gameplay ------------
rounds_user = df[(df["event"] == "newRoundStarted") &
                 (df["details.phase"] == "user-guess")]

cat_counts = rounds_user["details.category"].value_counts()

plt.figure(figsize=(6, 4))
ax2 = cat_counts.plot(kind="bar")
ax2.set_ylabel("Number of rounds")
ax2.set_title("User-Selected Categories During Gameplay")
add_bar_labels(ax2)                  # integer counts
plt.tight_layout()
plt.savefig("user_categories.pdf", dpi=300)

# ------------- 3. Distribution of Key Event Types (Pie) ---------------
TOP_N = 7
event_counts = df["event"].value_counts()
top = event_counts.head(TOP_N)
others = event_counts.iloc[TOP_N:].sum()
if others:
    top["other"] = others

label_map = {
    "newRoundStarted": "User Guess Turn Started",
    "userGuessSubmitted": "User Guess Submitted",
    "aiGuessMade": "AI Guess Submitted",
    "aiGuessRoundStarted": "AI Guess Turn Started",
    "gameOver": "Game Over",
    "playAgainClicked": "Play Again Clicked",
    "revealAnswer": "Answer Revealed",
    "other": "Other"
}

# Re-label the series
top_renamed = top.rename(index=label_map)

# Plot as bar chart
plt.figure(figsize=(8, 5))
ax = plt.gca()
bars = ax.bar(top_renamed.index, top_renamed.values)
ax.set_ylabel("Event Count")
ax.set_title("Distribution of Key Event Types Across All Sessions")
ax.set_xticklabels(top_renamed.index, rotation=45, ha='right')

y_max = max(top_renamed.values) * 1.10  # Add 10% headroom
ax.set_ylim(0, y_max)

for bar in bars:
    height = bar.get_height()
    ax.annotate(f'{height}', xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')

plt.tight_layout()
plt.savefig("event_distribution_barplot.pdf", dpi=300)


# ------------- 4. Rounds Played Per Session ---------------------------
all_rounds = df[(df["event"] == "newRoundStarted")]
rounds_per_session = all_rounds.groupby("sessionId").size()
dist = rounds_per_session.value_counts().sort_index()

plt.figure(figsize=(6, 4))
plt.hist(rounds_per_session, bins=range(0, rounds_per_session.max() + 5, 5), edgecolor="black", rwidth=0.9)
plt.xlabel("Rounds per session (binned)")
plt.ylabel("Number of sessions")
plt.title("Distribution of Rounds Played Per Session")
plt.gca().yaxis.set_major_locator(MaxNLocator(integer=True))  # Force integer y-ticks
plt.tight_layout()
plt.savefig("rounds_played_hist.pdf", dpi=300)



# ------------- Show all figures ---------------------------------------






# 5. Engagement summary stats  << NEW >>
total_rounds              = len(all_rounds)
sessions_n                = df["sessionId"].nunique()
avg_rounds_per_user       = total_rounds / sessions_n
total_user_guesses        = (df["event"] == "userGuessSubmitted").sum()
total_ai_guesses        = (df["event"] == "aiGuessMade").sum()
total_skipped_words       = (df["event"] == "userSkippedWord").sum()
play_again_clicks         = (df["event"] == "playAgainClicked").sum()

# mean active duration: span from 1st to last event in each session
session_durations_min = (
    df.groupby("sessionId")["ts"]
      .apply(lambda g: (g.max() - g.min()).total_seconds() / 60)
)
mean_active_minutes = session_durations_min.mean()


# Group by user ID and count total rounds played per user
rounds_per_user = all_rounds.groupby("sessionId").size()
avg_rounds_user = rounds_per_user.mean()
std_rounds_user = rounds_per_user.std()

# Active duration per user in minutes
user_durations_min = (
    df.groupby("sessionId")["ts"]
      .apply(lambda g: (g.max() - g.min()).total_seconds() / 60)
)
avg_duration_user = user_durations_min.mean()
std_duration_user = user_durations_min.std()


# Calculate active session durations (in minutes)
session_durations_min = (
    df.groupby("sessionId")["ts"]
      .apply(lambda g: (g.max() - g.min()).total_seconds() / 60)
)

# --- Exclude outliers using IQR ---
Q1 = session_durations_min.quantile(0.25)
Q3 = session_durations_min.quantile(0.75)
IQR = Q3 - Q1

# Define bounds for non-outlier range
lower_bound = Q1 - 1.5 * IQR
upper_bound = Q3 + 1.5 * IQR

# Filter out outliers
filtered_durations = session_durations_min[
    (session_durations_min >= lower_bound) &
    (session_durations_min <= upper_bound)
]

# Calculate new mean and std dev
mean_filtered_duration = filtered_durations.mean()
std_filtered_duration  = filtered_durations.std()

# Print result
print(f"• Mean active session duration (no outliers): {mean_filtered_duration:.2f} minutes")
print(f"• Std. deviation of session duration (no outliers): {std_filtered_duration:.2f} minutes")


print("\nPer-user engagement stats:")
print(f"• Average rounds played per user: {avg_rounds_user:.2f}")
print(f"• Standard deviation of rounds played per user: {std_rounds_user:.2f}")
print(f"• Average active session duration per user: {avg_duration_user:.2f} minutes")
print(f"• Standard deviation of session duration per user: {std_duration_user:.2f} minutes")


play_again_users = df[df["event"] == "playAgainClicked"]["sessionId"].nunique()
print(f"• {play_again_users} unique users clicked on 'Play Again'")

# print human-readable summary
print("\nObjective engagement data from the 15 sessions included the following:")
print(f"• {total_rounds} rounds played across all users.")
print(f"• An average of {avg_rounds_per_user:.1f} rounds per user.")
print(f"• {total_user_guesses} total user guesses submitted.")
print(f"• {total_ai_guesses} total ai guesses submitted.")
print(f"• {total_skipped_words} words skipped.")
print(f"• “Play Again” was clicked {play_again_clicks} times.")
print(f"• Mean active session duration: {mean_active_minutes:.1f} minutes (excluding idle time).")



plt.show()