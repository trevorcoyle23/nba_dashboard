import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
PLAY_BY_PLAY_URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"


st.set_page_config(
    page_title="Live NBA Stats Dashboard",
    layout="wide"
)


def get_json(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.nba.com",
        "Referer": "https://www.nba.com/",
        "Connection": "keep-alive",
    }

    session = requests.Session()
    response = session.get(url, headers=headers, timeout=15)

    if response.status_code == 403:
        raise RuntimeError(
            "NBA blocked the request with 403 Forbidden. "
            "Try again later, reduce refresh frequency, or use the nba_api fallback version below."
        )

    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=30)
def get_scoreboard():
    data = get_json(SCOREBOARD_URL)
    return data.get("scoreboard", {}).get("games", [])


@st.cache_data(ttl=30)
def get_boxscore(game_id):
    data = get_json(BOXSCORE_URL.format(game_id=game_id))
    return data.get("game", {})


@st.cache_data(ttl=30)
def get_play_by_play(game_id):
    data = get_json(PLAY_BY_PLAY_URL.format(game_id=game_id))
    return data.get("game", {}).get("actions", [])


def game_status_text(status):
    if status == 1:
        return "Scheduled"
    if status == 2:
        return "Live"
    if status == 3:
        return "Final"
    return "Unknown"


def build_game_label(game):
    away = game.get("awayTeam", {})
    home = game.get("homeTeam", {})

    away_name = away.get("teamTricode", "AWAY")
    home_name = home.get("teamTricode", "HOME")

    away_score = away.get("score", 0)
    home_score = home.get("score", 0)

    status = game_status_text(game.get("gameStatus"))
    clock = game.get("gameClock", "")
    period = game.get("period", 0)

    if status == "Live":
        return f"{away_name} {away_score} @ {home_name} {home_score} — Q{period} {clock}"
    return f"{away_name} {away_score} @ {home_name} {home_score} — {status}"


def get_team_rows(game):
    home = game.get("homeTeam", {})
    away = game.get("awayTeam", {})

    rows = []

    for label, team in [("Away", away), ("Home", home)]:
        stats = team.get("statistics", {})

        rows.append({
            "Side": label,
            "Team": team.get("teamTricode", label),
            "Score": team.get("score", 0),
            "FG%": round(stats.get("fieldGoalsPercentage", 0) * 100, 1),
            "3P%": round(stats.get("threePointersPercentage", 0) * 100, 1),
            "FT%": round(stats.get("freeThrowsPercentage", 0) * 100, 1),
            "REB": stats.get("reboundsTotal", 0),
            "AST": stats.get("assists", 0),
            "TOV": stats.get("turnovers", 0),
            "STL": stats.get("steals", 0),
            "BLK": stats.get("blocks", 0),
            "Paint PTS": stats.get("pointsInThePaint", 0),
            "Fast Break PTS": stats.get("pointsFastBreak", 0),
            "2nd Chance PTS": stats.get("pointsSecondChance", 0),
        })

    return pd.DataFrame(rows)


def get_period_rows(game):
    rows = []

    for side in ["awayTeam", "homeTeam"]:
        team = game.get(side, {})
        team_name = team.get("teamTricode", side)
        periods = team.get("periods", [])

        for p in periods:
            rows.append({
                "Team": team_name,
                "Period": f"Q{p.get('period')}",
                "Points": p.get("score", 0)
            })

    return pd.DataFrame(rows)


def get_players_df(game):
    rows = []

    for side in ["awayTeam", "homeTeam"]:
        team = game.get(side, {})
        team_name = team.get("teamTricode", side)

        for player in team.get("players", []):
            stats = player.get("statistics", {})

            if not player.get("played"):
                continue

            rows.append({
                "Team": team_name,
                "Player": stats.get("name", player.get("name", "Unknown")),
                "PTS": stats.get("points", 0),
                "REB": stats.get("reboundsTotal", 0),
                "AST": stats.get("assists", 0),
                "STL": stats.get("steals", 0),
                "BLK": stats.get("blocks", 0),
                "TOV": stats.get("turnovers", 0),
                "+/-": stats.get("plusMinusPoints", 0),
                "MIN": stats.get("minutesCalculated", stats.get("minutes", ""))
            })

    return pd.DataFrame(rows)


def clock_to_game_minutes(period, clock):
    if not clock or not isinstance(clock, str):
        return None

    try:
        cleaned = clock.replace("PT", "").replace("S", "")
        minutes = 0
        seconds = 0

        if "M" in cleaned:
            m_part, s_part = cleaned.split("M")
            minutes = int(float(m_part)) if m_part else 0
            seconds = float(s_part) if s_part else 0
        else:
            seconds = float(cleaned)

        remaining = minutes + seconds / 60

        # NBA quarters are 12 minutes. OT periods are 5 minutes.
        if period <= 4:
            elapsed = (period - 1) * 12 + (12 - remaining)
        else:
            elapsed = 48 + (period - 5) * 5 + (5 - remaining)

        return round(elapsed, 2)
    except Exception:
        return None


def get_scoring_timeline(actions):
    rows = []

    for action in actions:
        home_score = action.get("scoreHome")
        away_score = action.get("scoreAway")

        if home_score is None or away_score is None:
            continue

        period = action.get("period", 0)
        clock = action.get("clock", "")
        elapsed = clock_to_game_minutes(period, clock)

        if elapsed is None:
            continue

        try:
            home_score = int(home_score)
            away_score = int(away_score)
        except ValueError:
            continue

        rows.append({
            "Elapsed Minutes": elapsed,
            "Home Score": home_score,
            "Away Score": away_score,
            "Period": period,
            "Clock": clock,
            "Description": action.get("description", "")
        })

    return pd.DataFrame(rows)


def show_scoreboard_header(game):
    home = game.get("homeTeam", {})
    away = game.get("awayTeam", {})

    home_name = home.get("teamName", home.get("teamTricode", "Home"))
    away_name = away.get("teamName", away.get("teamTricode", "Away"))

    home_score = home.get("score", 0)
    away_score = away.get("score", 0)

    status = game_status_text(game.get("gameStatus"))
    period = game.get("period", 0)
    clock = game.get("gameClock", "")

    st.title("Live NBA Stats Dashboard")

    if status == "Live":
        st.subheader(f"{away_name} {away_score} @ {home_name} {home_score} — Q{period} {clock}")
    else:
        st.subheader(f"{away_name} {away_score} @ {home_name} {home_score} — {status}")

    st.caption(f"Last refreshed: {datetime.now().strftime('%I:%M:%S %p')}")


def main():
    with st.sidebar:
        st.header("Settings")

        refresh_seconds = st.slider(
            "Refresh every N seconds",
            min_value=15,
            max_value=120,
            value=30,
            step=5
        )

        auto_refresh = st.toggle("Auto-refresh", value=True)

    try:
        games = get_scoreboard()
    except Exception as e:
        st.error("Could not load NBA scoreboard data.")
        st.warning(str(e))
        st.stop()

    if not games:
        st.warning("No NBA games found for today.")
        return

    labels = [build_game_label(game) for game in games]

    selected_label = st.sidebar.selectbox("Choose game", labels)
    selected_index = labels.index(selected_label)
    selected_game_summary = games[selected_index]
    game_id = selected_game_summary.get("gameId")

    if not game_id:
        st.error("Could not find a game ID for the selected game.")
        return

    game = get_boxscore(game_id)
    actions = get_play_by_play(game_id)

    if not game:
        st.error("Boxscore data was not available for this game yet.")
        return

    show_scoreboard_header(game)

    team_df = get_team_rows(game)
    period_df = get_period_rows(game)
    players_df = get_players_df(game)
    timeline_df = get_scoring_timeline(actions)

    # Main score cards
    col1, col2, col3, col4 = st.columns(4)

    away = game.get("awayTeam", {})
    home = game.get("homeTeam", {})

    with col1:
        st.metric(
            label=away.get("teamTricode", "Away"),
            value=away.get("score", 0)
        )

    with col2:
        st.metric(
            label=home.get("teamTricode", "Home"),
            value=home.get("score", 0)
        )

    with col3:
        st.metric(
            label="Period",
            value=f"Q{game.get('period', 0)}"
        )

    with col4:
        st.metric(
            label="Clock",
            value=game.get("gameClock", "N/A")
        )

    st.divider()

    # Scoring timeline
    if not timeline_df.empty:
        st.subheader("Scoring Timeline")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=timeline_df["Elapsed Minutes"],
            y=timeline_df["Away Score"],
            mode="lines+markers",
            name=away.get("teamTricode", "Away"),
            hovertext=timeline_df["Description"],
        ))

        fig.add_trace(go.Scatter(
            x=timeline_df["Elapsed Minutes"],
            y=timeline_df["Home Score"],
            mode="lines+markers",
            name=home.get("teamTricode", "Home"),
            hovertext=timeline_df["Description"],
        ))

        fig.update_layout(
            xaxis_title="Elapsed Game Minutes",
            yaxis_title="Score",
            height=450
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Scoring timeline will appear once play-by-play scoring data is available.")

    left_col, right_col = st.columns(2)

    # Points by quarter
    with left_col:
        st.subheader("Points by Quarter")

        if not period_df.empty:
            fig = px.bar(
                period_df,
                x="Period",
                y="Points",
                color="Team",
                barmode="group",
                text="Points"
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Quarter scoring data is not available yet.")

    # Team stat comparison
    with right_col:
        st.subheader("Team Stat Comparison")

        stat_options = [
            "FG%",
            "3P%",
            "FT%",
            "REB",
            "AST",
            "TOV",
            "STL",
            "BLK",
            "Paint PTS",
            "Fast Break PTS",
            "2nd Chance PTS"
        ]

        chosen_stats = st.multiselect(
            "Choose stats to compare",
            stat_options,
            default=["FG%", "3P%", "REB", "AST", "TOV"]
        )

        if chosen_stats:
            melted = team_df.melt(
                id_vars=["Team"],
                value_vars=chosen_stats,
                var_name="Stat",
                value_name="Value"
            )

            fig = px.bar(
                melted,
                x="Stat",
                y="Value",
                color="Team",
                barmode="group",
                text="Value"
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

    left_col, right_col = st.columns(2)

    # Top scorers
    with left_col:
        st.subheader("Top Scorers")

        if not players_df.empty:
            top_scorers = players_df.sort_values("PTS", ascending=False).head(10)

            fig = px.bar(
                top_scorers,
                x="PTS",
                y="Player",
                color="Team",
                orientation="h",
                text="PTS",
                hover_data=["REB", "AST", "MIN"]
            )
            fig.update_layout(
                yaxis={"categoryorder": "total ascending"},
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Player stats are not available yet.")

    # Plus/minus
    with right_col:
        st.subheader("Player Plus/Minus")

        if not players_df.empty:
            plus_minus = players_df.sort_values("+/-", ascending=True).tail(12)

            fig = px.bar(
                plus_minus,
                x="+/-",
                y="Player",
                color="Team",
                orientation="h",
                text="+/-",
                hover_data=["PTS", "REB", "AST", "MIN"]
            )
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Plus/minus data is not available yet.")

    st.divider()

    # Boxscore table
    st.subheader("Player Boxscore")

    if not players_df.empty:
        st.dataframe(
            players_df.sort_values(["Team", "PTS"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True
        )

    # Recent plays
    st.subheader("Recent Plays")

    if actions:
        recent_actions = actions[-15:]
        recent_rows = []

        for action in reversed(recent_actions):
            recent_rows.append({
                "Period": action.get("period", ""),
                "Clock": action.get("clock", ""),
                "Score": f"{action.get('scoreAway', '')} - {action.get('scoreHome', '')}",
                "Play": action.get("description", "")
            })

        st.dataframe(
            pd.DataFrame(recent_rows),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Play-by-play data is not available yet.")

    if auto_refresh:
        time.sleep(refresh_seconds)
        st.rerun()


if __name__ == "__main__":
    main()
