import json
import time
from datetime import date
from nba_api.stats.endpoints import LeagueGameLog

SEASON = "2025-26"

NBA_HEADERS = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nba.com/',
    'Origin': 'https://www.nba.com',
}

# Séries confirmadas do primeiro round
SERIES = [
    {"id": "lal_hou", "home": "LAL", "away": "HOU", "home_seed": 4, "away_seed": 5, "conf": "West"},
    {"id": "den_min", "home": "DEN", "away": "MIN", "home_seed": 3, "away_seed": 6, "conf": "West"},
    {"id": "cle_tor", "home": "CLE", "away": "TOR", "home_seed": 4, "away_seed": 5, "conf": "East"},
    {"id": "nyk_atl", "home": "NYK", "away": "ATL", "home_seed": 3, "away_seed": 6, "conf": "East"},
    {"id": "sas_por", "home": "SAS", "away": "POR", "home_seed": 2, "away_seed": 7, "conf": "West"},
    {"id": "bos_phi", "home": "BOS", "away": "PHI", "home_seed": 2, "away_seed": 7, "conf": "East"},
    {"id": "det_orl", "home": "DET", "away": "ORL", "home_seed": 1, "away_seed": 8, "conf": "East"},
    {"id": "okc_phx", "home": "OKC", "away": "PHX", "home_seed": 1, "away_seed": 8, "conf": "West"}
    {"id": "sas_min", "home": "SAS", "away": "MIN", "home_seed": 2, "away_seed": 6, "conf": "West"},
    ]

def fetch_gamelog(retries=3):
    for attempt in range(retries):
        try:
            time.sleep(2)
            df = LeagueGameLog(
                season=SEASON,
                season_type_all_star="Regular Season",
                headers=NBA_HEADERS,
                timeout=60,
            ).get_data_frames()[0]
            return df
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                raise e

print("Coletando game log da temporada...")
df = fetch_gamelog()
print(f"  {len(df)} registros encontrados")

# Cada jogo aparece duas vezes no gamelog (uma por time)
# Filtra só as entradas do time mandante (MATCHUP contém "vs.")
home_games = df[df["MATCHUP"].str.contains("vs\.")].copy()
print(f"  {len(home_games)} jogos do mandante")

output = {"season": SEASON, "updated": str(date.today()), "series": {}}

for serie in SERIES:
    t1 = serie["home"]
    t2 = serie["away"]
    print(f"\nProcessando {t1} vs {t2}...")

    # Jogos onde t1 jogou em casa contra t2
    t1_home = home_games[
        (home_games["TEAM_ABBREVIATION"] == t1) &
        (home_games["MATCHUP"].str.contains(t2))
    ].copy()

    # Jogos onde t2 jogou em casa contra t1
    t2_home = home_games[
        (home_games["TEAM_ABBREVIATION"] == t2) &
        (home_games["MATCHUP"].str.contains(t1))
    ].copy()

    games = []

    for _, row in t1_home.iterrows():
        opp_score = df[
            (df["GAME_ID"] == row["GAME_ID"]) &
            (df["TEAM_ABBREVIATION"] == t2)
        ]["PTS"].values
        opp_pts = int(opp_score[0]) if len(opp_score) > 0 else 0
        games.append({
            "game_id": row["GAME_ID"],
            "date": row["GAME_DATE"],
            "home": t1,
            "away": t2,
            "home_pts": int(row["PTS"]),
            "away_pts": opp_pts,
            "winner": t1 if int(row["PTS"]) > opp_pts else t2,
        })

    for _, row in t2_home.iterrows():
        opp_score = df[
            (df["GAME_ID"] == row["GAME_ID"]) &
            (df["TEAM_ABBREVIATION"] == t1)
        ]["PTS"].values
        opp_pts = int(opp_score[0]) if len(opp_score) > 0 else 0
        games.append({
            "game_id": row["GAME_ID"],
            "date": row["GAME_DATE"],
            "home": t2,
            "away": t1,
            "home_pts": int(row["PTS"]),
            "away_pts": opp_pts,
            "winner": t2 if int(row["PTS"]) > opp_pts else t1,
        })

    # Ordena por data
    games.sort(key=lambda x: x["date"])

    # Recorde na temporada regular
    t1_wins = sum(1 for g in games if g["winner"] == t1)
    t2_wins = sum(1 for g in games if g["winner"] == t2)

    print(f"  {len(games)} jogos encontrados · {t1} {t1_wins}-{t2_wins} {t2}")

    output["series"][serie["id"]] = {
        "conf": serie["conf"],
        "home": t1,
        "away": t2,
        "home_seed": serie["home_seed"],
        "away_seed": serie["away_seed"],
        "regular_season_record": {t1: t1_wins, t2: t2_wins},
        "games": games,
    }

with open("head2head.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! head2head.json criado com {len(output['series'])} séries.")