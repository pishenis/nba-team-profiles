import json
import time
from datetime import date
from nba_api.stats.endpoints import LeagueDashLineups

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

ALL_TEAM_IDS = [
    1610612737,1610612738,1610612751,1610612766,1610612741,
    1610612739,1610612742,1610612743,1610612765,1610612744,
    1610612745,1610612754,1610612746,1610612747,1610612763,
    1610612748,1610612749,1610612750,1610612740,1610612752,
    1610612760,1610612753,1610612755,1610612756,1610612757,
    1610612758,1610612759,1610612761,1610612762,1610612764,
]

lineups_out = {}

print("Coletando lineups por time...")
for i, tid in enumerate(ALL_TEAM_IDS):
    print(f"  Time {i+1}/30 (ID {tid})")
    for attempt in range(3):
        try:
            time.sleep(1.5)
            df = LeagueDashLineups(
                season=SEASON,
                team_id_nullable=tid,
                per_mode_detailed="Per100Possessions",
                measure_type_detailed_defense="Advanced",
                headers=NBA_HEADERS,
            ).get_data_frames()[0]

            if len(df) == 0:
                break

            abbr = df["TEAM_ABBREVIATION"].iloc[0]

            # Top 5 por minutos
            top5 = df.nlargest(5, "MIN")
            lineups_out[abbr] = [
                {
                    "lineup": row["GROUP_NAME"],
                    "minutes": round(row["MIN"] or 0, 1),
                    "gp": int(row["GP"] or 0),
                    "off_rtg": round(row["OFF_RATING"] or 0, 1),
                    "def_rtg": round(row["DEF_RATING"] or 0, 1),
                    "net_rtg": round(row["NET_RATING"] or 0, 1),
                }
                for _, row in top5.iterrows()
            ]
            print(f"    {abbr}: {len(lineups_out[abbr])} lineups")
            break
        except Exception as e:
            if attempt < 2:
                print(f"    Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                print(f"    ERRO: {e}")

output = {
    "season": SEASON,
    "updated": str(date.today()),
    "teams": lineups_out,
}

with open("lineups_times.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! lineups_times.json criado com {len(lineups_out)} times.")