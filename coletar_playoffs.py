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

# Mapeamento de abreviações para IDs de série
# Chave = par de times ordenado alfabeticamente
SERIES_MAP = {
    # Primeiro Round
    frozenset(["OKC","PHX"]): "okc_phx",
    frozenset(["LAL","HOU"]): "lal_hou",
    frozenset(["DEN","MIN"]): "den_min",
    frozenset(["SAS","POR"]): "sas_por",
    frozenset(["DET","ORL"]): "det_orl",
    frozenset(["CLE","TOR"]): "cle_tor",
    frozenset(["NYK","ATL"]): "nyk_atl",
    frozenset(["BOS","PHI"]): "bos_phi",
    # Segundo Round — adicionar pares à medida que forem confirmados
    frozenset(["SAS","MIN"]): "sas_min",
    frozenset(["OKC","LAL"]): "okc_lal",
    frozenset(["NYK","PHI"]): "nyk_phi",
}

print("Coletando jogos de playoff...")
for attempt in range(3):
    try:
        time.sleep(2)
        df = LeagueGameLog(
            season=SEASON,
            season_type_all_star="Playoffs",
            headers=NBA_HEADERS,
            timeout=60,
        ).get_data_frames()[0]
        break
    except Exception as e:
        if attempt < 2:
            print(f"  Tentativa {attempt+1} falhou, aguardando 5s...")
            time.sleep(5)
        else:
            print(f"  ERRO: {e}")
            exit(1)

print(f"  {len(df)} registros encontrados")

# Filtra só jogos do mandante (evita duplicatas)
home_games = df[df["MATCHUP"].str.contains("vs\.")].copy()
print(f"  {len(home_games)} jogos únicos")

# Agrupa por série
series_games = {}

for _, row in home_games.iterrows():
    game_id   = str(row["GAME_ID"])
    game_date = str(row["GAME_DATE"])
    home_abbr = str(row["TEAM_ABBREVIATION"])
    home_pts  = int(row["PTS"] or 0)

    # Acha o time visitante
    opp_row = df[(df["GAME_ID"] == row["GAME_ID"]) & (df["TEAM_ABBREVIATION"] != home_abbr)]
    if opp_row.empty:
        continue
    away_abbr = str(opp_row.iloc[0]["TEAM_ABBREVIATION"])
    away_pts  = int(opp_row.iloc[0]["PTS"] or 0)

    # Identifica série
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

# Ordena jogos por data dentro de cada série
for serie_id in series_games:
    series_games[serie_id].sort(key=lambda x: x["date"])
    # Numera os jogos
    for i, g in enumerate(series_games[serie_id]):
        g["game_number"] = i + 1

# Calcula placar da série
series_scores = {}
for serie_id, games in series_games.items():
    teams = list({g["home"] for g in games} | {g["away"] for g in games})
    wins = {t: sum(1 for g in games if g["winner"] == t) for t in teams}
    series_scores[serie_id] = wins

output = {
    "season": SEASON,
    "updated": str(date.today()),
    "series": series_games,
    "series_scores": series_scores,
}

with open("jogos_playoffs.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! jogos_playoffs.json criado.")
for serie_id, games in series_games.items():
    scores = series_scores[serie_id]
    teams = list(scores.keys())
    if len(teams) == 2:
        t1, t2 = teams
        print(f"  {serie_id}: {t1} {scores[t1]}-{scores[t2]} {t2} ({len(games)} jogos)")