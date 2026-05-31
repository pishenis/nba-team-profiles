import json
import time
from nba_api.stats.endpoints import BoxScoreSummaryV2

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

GAME_ID = "0062500001"

print(f"Buscando dados do jogo {GAME_ID} (NBA Cup Final)...")
time.sleep(2)
summary_dfs = BoxScoreSummaryV2(
    game_id=GAME_ID,
    headers=NBA_HEADERS,
    timeout=60,
).get_data_frames()

line_score = summary_dfs[5]
game_info  = summary_dfs[0]

game_date    = str(game_info["GAME_DATE_EST"].iloc[0])[:10]
home_team_id = int(game_info["HOME_TEAM_ID"].iloc[0])

row0 = line_score.iloc[0]
row1 = line_score.iloc[1]
if int(row0["TEAM_ID"]) == home_team_id:
    home_row, away_row = row0, row1
else:
    home_row, away_row = row1, row0

home_abbr = home_row["TEAM_ABBREVIATION"]
away_abbr = away_row["TEAM_ABBREVIATION"]
home_pts  = int(home_row["PTS"] or 0)
away_pts  = int(away_row["PTS"] or 0)
winner    = home_abbr if home_pts > away_pts else away_abbr

print(f"  {away_abbr} {away_pts} @ {home_abbr} {home_pts} · {game_date} · venceu: {winner}")

cup_game = {
    "game_id": GAME_ID,
    "date": game_date,
    "home": home_abbr,
    "away": away_abbr,
    "home_pts": home_pts,
    "away_pts": away_pts,
    "winner": winner,
    "is_cup": True,
}

# Injeta no head2head.json na série finals
with open("head2head.json") as f:
    h2h = json.load(f)

serie = h2h["series"].get("finals")
if not serie:
    print("ERRO: série 'finals' não encontrada no head2head.json")
    exit(1)

# Remove jogo da cup se já existir (evita duplicata)
serie["games"] = [g for g in serie["games"] if g.get("game_id") != GAME_ID]

# Insere e reordena por data
serie["games"].append(cup_game)
serie["games"].sort(key=lambda x: x["date"])

with open("head2head.json", "w") as f:
    json.dump(h2h, f, indent=2)

print(f"Feito! NBA Cup Final injetada na série finals.")
print(f"  Total de jogos na série: {len(serie['games'])}")
