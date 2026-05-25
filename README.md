# Live NBA Stats Dashboard

A real-time NBA game analytics dashboard built with **Python**, **Streamlit**, **pandas**, **Plotly**, and live NBA data endpoints.

This project displays live game data in an interactive dashboard, including the scoreboard, team comparisons, scoring timeline, player stats, plus/minus, points by quarter, and recent play-by-play updates.

---

## Features

- Live NBA scoreboard
- Select any NBA game currently available for the day
- Auto-refreshing dashboard
- Team score comparison
- Scoring timeline chart
- Points by quarter chart
- Team stat comparison chart
- Top scorers chart
- Player plus/minus chart
- Full player boxscore table
- Recent play-by-play feed
- Error handling for unavailable or blocked data endpoints

---

## Tech Stack

- Python (v3.10+)
- Streamlit
- pandas
- Plotly
- requests
- NBA live data endpoints

---

## Dependencies & Execution

```text
pip3 install streamlit pandas plotly requests
python3 -m streamlit run dashboard.py
```
---

## Project Structure

```text
nba-dashboard/
│
├── dashboard.py
└── README.md
