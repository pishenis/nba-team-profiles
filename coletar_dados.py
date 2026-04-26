import json
import time
from datetime import date, timedelta
from nba_api.stats.endpoints import (
    LeagueDashTeamStats,
    LeagueDashTeamShotLocations,
    LeagueDashPtStats,
    LeagueDashTeamClutch,
    LeagueHustleStatsTeam,
    LeagueGameLog,
    SynergyPlayTypes,
)

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

today = date.today()
PERIODS = [
    {"key": "full", "label": "Temporada completa", "date_from": "", "date_to": ""},
    {"key": "30d",  "label": "Últimos 30 dias",    "date_from": (today - timedelta(days=30)).strftime("%m/%d/%Y"), "date_to": today.strftime("%m/%d/%Y")},
    {"key": "14d",  "label": "Últimas 2 semanas",  "date_from": (today - timedelta(days=14)).strftime("%m/%d/%Y"), "date_to": today.strftime("%m/%d/%Y")},
]

def fetch(cls, date_from="", date_to="", retries=3, **kw):
    for attempt in range(retries):
        try:
            time.sleep(1.5)
            return cls(
                season=SEASON,
                headers=NBA_HEADERS,
                date_from_nullable=date_from,
                date_to_nullable=date_to,
                **kw
            ).get_data_frames()[0]
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                raise e

def collect_period(period):
    df = period["date_from"]
    dt = period["date_to"]
    key = period["key"]
    print(f"\n=== {period['label']} ===")

    print("  Stats base...")
    base = fetch(LeagueDashTeamStats, df, dt, measure_type_detailed_defense="Base", per_mode_detailed="PerGame")
    print("  Stats avancadas...")
    advanced = fetch(LeagueDashTeamStats, df, dt, measure_type_detailed_defense="Advanced", per_mode_detailed="PerGame")
    print("  Stats misc...")
    misc = fetch(LeagueDashTeamStats, df, dt, measure_type_detailed_defense="Misc", per_mode_detailed="PerGame")
    print("  Stats opponent...")
    opponent = fetch(LeagueDashTeamStats, df, dt, measure_type_detailed_defense="Opponent", per_mode_detailed="PerGame")

    print("  Clutch...")
    clutch = fetch(LeagueDashTeamClutch, df, dt, measure_type_detailed_defense="Base", per_mode_detailed="Totals")

    print("  Hustle...")
    hustle = fetch(LeagueHustleStatsTeam, df, dt, per_mode_time="PerGame")

    print("  Arremessos ofensivos por zona...")
    time.sleep(1.5)
    sz_off_raw = LeagueDashTeamShotLocations(
        season=SEASON, per_mode_detailed="PerGame",
        distance_range="By Zone", measure_type_simple="Base",
        date_from_nullable=df, date_to_nullable=dt,
        headers=NBA_HEADERS
    ).get_data_frames()[0]
    sz_off_raw.columns = ["_".join(c).strip("_") for c in sz_off_raw.columns]

    print("  Arremessos defensivos por zona...")
    time.sleep(1.5)
    sz_def_raw = LeagueDashTeamShotLocations(
        season=SEASON, per_mode_detailed="PerGame",
        distance_range="By Zone", measure_type_simple="Opponent",
        date_from_nullable=df, date_to_nullable=dt,
        headers=NBA_HEADERS
    ).get_data_frames()[0]
    sz_def_raw.columns = ["_".join(c).strip("_") for c in sz_def_raw.columns]

    print("  Drives...")
    drives = fetch(LeagueDashPtStats, df, dt, per_mode_simple="PerGame", player_or_team="Team", pt_measure_type="Drives")

    print("  Post-ups...")
    postups = fetch(LeagueDashPtStats, df, dt, per_mode_simple="PerGame", player_or_team="Team", pt_measure_type="PostTouch")

    print("  Play types...")
    pt_types = ["Transition","PRBallHandler","PRRollMan","Isolation","Spotup","Postup","Handoff","Cut","OffScreen"]
    play_types = {}
    for pt in pt_types:
        for attempt in range(3):
            try:
                time.sleep(1.5)
                pt_df = SynergyPlayTypes(
                    season=SEASON,
                    per_mode_simple="PerGame",
                    play_type_nullable=pt,
                    type_grouping_nullable="offensive",
                    season_type_all_star="Regular Season",
                    headers=NBA_HEADERS
                ).get_data_frames()[0]
                play_types[pt] = pt_df.to_dict(orient="records")
                print(f"    {pt} OK")
                break
            except Exception as e:
                if attempt < 2:
                    print(f"    {pt} tentativa {attempt+1} falhou, aguardando 5s...")
                    time.sleep(5)
                else:
                    print(f"    {pt} ERRO: {e}")

    result = {
        "season": SEASON,
        "period": period["label"],
        "updated": str(today),
        "base": base.to_dict(orient="records"),
        "advanced": advanced.to_dict(orient="records"),
        "misc": misc.to_dict(orient="records"),
        "opponent": opponent.to_dict(orient="records"),
        "clutch": clutch.to_dict(orient="records"),
        "hustle": hustle.to_dict(orient="records"),
        "shot_zones_off": sz_off_raw.to_dict(orient="records"),
        "shot_zones_def": sz_def_raw.to_dict(orient="records"),
        "drives": drives.to_dict(orient="records"),
        "postups": postups.to_dict(orient="records"),
        "play_types": play_types,
    }

    filename = f"dados_nba_{key}.json"
    with open(filename, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Salvo: {filename}")

# Game log — coletado uma vez só (temporada completa)
print("\n=== Game Log (temporada completa) ===")
time.sleep(2)
for attempt in range(3):
    try:
        game_log_df = LeagueGameLog(
            season=SEASON,
            player_or_team_abbreviation='T',
            headers=NBA_HEADERS
        ).get_data_frames()[0]
        with open("dados_nba_gamelog.json", "w") as f:
            json.dump(game_log_df.to_dict(orient="records"), f, indent=2)
        print(f"  Salvo: dados_nba_gamelog.json ({len(game_log_df)} registros)")
        break
    except Exception as e:
        if attempt < 2:
            print(f"  Tentativa {attempt+1} falhou, aguardando 5s...")
            time.sleep(5)
        else:
            print(f"  ERRO no game log: {e}")

for period in PERIODS:
    collect_period(period)

print("\nFeito! Todos os períodos coletados.")