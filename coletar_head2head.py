#!/usr/bin/env python3
"""
coletar_head2head.py — BallDontLie edition
Coleta confrontos da temporada regular entre adversários dos playoffs
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
SEASON  = 2025

# Mapeamento abreviação → BDL team ID
TEAM_IDS = {
    "ATL": 1,  "BOS": 2,  "BKN": 3,  "CHA": 4,  "CHI": 5,
    "CLE": 6,  "DAL": 7,  "DEN": 8,  "DET": 9,  "GSW": 10,
    "HOU": 11, "IND": 12, "LAC": 13, "LAL": 14, "MEM": 15,
    "MIA": 16, "MIL": 17, "MIN": 18, "NOP": 19, "NYK": 20,
    "OKC": 21, "ORL": 22, "PHI": 23, "PHX": 24, "POR": 25,
    "SAC": 26, "SAS": 27, "TOR": 28, "UTA": 29, "WAS": 30,
}

SERIES = [
    {"id": "lal_hou", "home": "LAL", "away": "HOU", "home_seed": 4, "away_seed": 5, "conf": "West"},
    {"id": "den_min", "home": "DEN", "away": "MIN", "home_seed": 3, "away_seed": 6, "conf": "West"},
    {"id": "cle_tor", "home": "CLE", "away": "TOR", "home_seed": 4, "away_seed": 5, "conf": "East"},
    {"id": "nyk_atl", "home": "NYK", "away": "ATL", "home_seed": 3, "away_seed": 6, "conf": "East"},
    {"id": "sas_por", "home": "SAS", "away": "POR", "home_seed": 2, "away_seed": 7, "conf": "West"},
    {"id": "bos_phi", "home": "BOS", "away": "PHI", "home_seed": 2, "away_seed": 7, "conf": "East"},
    {"id": "det_orl", "home": "DET", "away": "ORL", "home_seed": 1, "away_seed": 8, "conf": "East"},
    {"id": "okc_phx", "home": "OKC", "away": "PHX", "home_seed": 1, "away_seed": 8, "conf": "West"},
    {"id": "sas_min", "home": "SAS", "away": "MIN", "home_seed": 2, "away_seed": 6, "conf": "West"},
    {"id": "okc_lal", "home": "OKC", "away": "LAL", "home_seed": 1, "away_seed": 4, "conf": "West"},
    {"id": "nyk_phi", "home": "NYK", "away": "PHI", "home_seed": 3, "away_seed": 7, "conf": "East"},
    {"id": "det_cle", "home": "DET", "away": "CLE", "home_seed": 1, "away_seed": 4, "conf": "East"},
    {"id": "okc_sas", "home": "OKC", "away": "SAS", "home_seed": 1, "away_seed": 2, "conf": "West"},
    {"id": "nyk_cle", "home": "CLE", "away": "NYK", "home_seed": 4, "away_seed": 3, "conf": "East"},
    {"id": "finals",  "home": "SAS", "away": "NYK", "home_seed": 2, "away_seed": 3, "conf": "Finals"},
]

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

output = {"season": "2025-26", "updated": str(date.today()), "series": {}}

for serie in SERIES:
    t1   = serie["home"]
    t2   = serie["away"]
    id1  = TEAM_IDS.get(t1)
    id2  = TEAM_IDS.get(t2)
    if not id1 or not id2:
        print(f"  ID não encontrado para {t1} ou {t2}")
        continue

    print(f"\nProcessando {t1} vs {t2}...")

    # BDL retorna jogos de qualquer um dos dois times — filtramos depois
    games_raw = get_all_pages(f"{BASE}/games", {
        "seasons[]":  SEASON,
        "team_ids[]": [id1, id2],
        "postseason": "false",
    })

    games = []
    for g in games_raw:
        ha = g["home_team"]["abbreviation"]
        aa = g["visitor_team"]["abbreviation"]
        if {ha, aa} != {t1, t2}:
            continue  # ignora jogos contra outros times
        home_pts  = g.get("home_team_score", 0) or 0
        away_pts  = g.get("visitor_team_score", 0) or 0
        is_cup    = bool(g.get("ist_stage"))  # jogo da NBA Cup
        entry = {
            "game_id":  str(g["id"]),
            "date":     (g.get("date") or "")[:10],
            "home":     ha,
            "away":     aa,
            "home_pts": home_pts,
            "away_pts": away_pts,
            "winner":   ha if home_pts > away_pts else aa,
        }
        if is_cup:
            entry["is_cup"] = True
        games.append(entry)

    games.sort(key=lambda x: x["date"])

    # Recorde: exclui jogos da NBA Cup da contagem
    t1_wins = sum(1 for g in games if g["winner"] == t1 and not g.get("is_cup"))
    t2_wins = sum(1 for g in games if g["winner"] == t2 and not g.get("is_cup"))
    print(f"  {len(games)} jogos · {t1} {t1_wins}-{t2_wins} {t2}")

    output["series"][serie["id"]] = {
        "conf":                   serie["conf"],
        "home":                   t1,
        "away":                   t2,
        "home_seed":              serie["home_seed"],
        "away_seed":              serie["away_seed"],
        "regular_season_record":  {t1: t1_wins, t2: t2_wins},
        "games":                  games,
    }

with open("head2head.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! head2head.json criado com {len(output['series'])} séries.")
