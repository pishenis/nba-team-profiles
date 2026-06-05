#!/usr/bin/env python3
"""
coletar_playoffs.py — BallDontLie edition
Coleta todos os jogos de playoff e gera jogos_playoffs.json
"""

import json, os, time
from datetime import date
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BDL_API_KEY")
if not API_KEY:
    print("ERRO: BDL_API_KEY não encontrado")
    exit(1)

HEADERS = {"Authorization": API_KEY}
BASE    = "https://api.balldontlie.io/nba/v1"
SEASON  = 2025  # BDL usa ano numérico

SERIES_MAP = {
    frozenset(["OKC","PHX"]): "okc_phx",
    frozenset(["LAL","HOU"]): "lal_hou",
    frozenset(["DEN","MIN"]): "den_min",
    frozenset(["SAS","POR"]): "sas_por",
    frozenset(["DET","ORL"]): "det_orl",
    frozenset(["CLE","TOR"]): "cle_tor",
    frozenset(["NYK","ATL"]): "nyk_atl",
    frozenset(["BOS","PHI"]): "bos_phi",
    frozenset(["SAS","MIN"]): "sas_min",
    frozenset(["OKC","LAL"]): "okc_lal",
    frozenset(["NYK","PHI"]): "nyk_phi",
    frozenset(["DET","CLE"]): "det_cle",
    frozenset(["OKC","SAS"]): "okc_sas",
    frozenset(["NYK","CLE"]): "nyk_cle",
    frozenset(["SAS","NYK"]): "finals",
}

def get_all_pages(url, params=None):
    params = dict(params or {})
    params["per_page"] = 100
    items = []
    while True:
        time.sleep(0.3)
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("data", []))
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
    return items

print("Coletando jogos de playoff via BDL...")
games_raw = get_all_pages(f"{BASE}/games", {"seasons[]": SEASON, "postseason": "true"})
print(f"  {len(games_raw)} jogos encontrados")

series_games = {}

for g in games_raw:
    home_abbr = g["home_team"]["abbreviation"]
    away_abbr = g["visitor_team"]["abbreviation"]
    home_pts  = g.get("home_team_score", 0) or 0
    away_pts  = g.get("visitor_team_score", 0) or 0
    game_id   = str(g["id"])
    game_date = (g.get("date") or "")[:10]

    pair = frozenset([home_abbr, away_abbr])
    serie_id = SERIES_MAP.get(pair)
    if not serie_id:
        print(f"  Série não mapeada: {home_abbr} vs {away_abbr}")
        continue

    if serie_id not in series_games:
        series_games[serie_id] = []

    series_games[serie_id].append({
        "game_id":  game_id,
        "date":     game_date,
        "home":     home_abbr,
        "away":     away_abbr,
        "home_pts": home_pts,
        "away_pts": away_pts,
        "winner":   home_abbr if home_pts > away_pts else away_abbr,
    })

# Ordena por data e numera
for serie_id in series_games:
    series_games[serie_id].sort(key=lambda x: x["date"])
    for i, g in enumerate(series_games[serie_id]):
        g["game_number"] = i + 1

# Calcula placar da série
series_scores = {}
for serie_id, games in series_games.items():
    teams = list({g["home"] for g in games} | {g["away"] for g in games})
    wins  = {t: sum(1 for g in games if g["winner"] == t) for t in teams}
    series_scores[serie_id] = wins

output = {
    "season":        "2025-26",
    "updated":       str(date.today()),
    "series":        series_games,
    "series_scores": series_scores,
}

with open("jogos_playoffs.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! jogos_playoffs.json criado.")
for serie_id, games in series_games.items():
    scores = series_scores[serie_id]
    teams  = list(scores.keys())
    if len(teams) == 2:
        t1, t2 = teams
        print(f"  {serie_id}: {t1} {scores[t1]}-{scores[t2]} {t2} ({len(games)} jogos)")
