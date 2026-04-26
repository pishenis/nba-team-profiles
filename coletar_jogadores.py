import json
import time
import requests
from datetime import date
from nba_api.stats.endpoints import (
    LeagueDashPlayerStats,
    LeagueDashLineups,
    CommonPlayerInfo,
    PlayerAwards,
)

SEASON = "2025-26"
MIN_MINUTES = 13.0
MIN_GAMES = 14

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

PBP_BASE = "https://api.pbpstats.com"
today = date.today()

try:
    existing = json.load(open("jogadores.json"))
    existing_players = existing.get("players", {})
    print(f"Bio existente carregada: {len(existing_players)} jogadores")
except:
    existing_players = {}
    print("Sem bio existente — fará chamadas individuais")

def nba_fetch(cls, retries=3, **kw):
    for attempt in range(retries):
        try:
            time.sleep(1.5)
            return cls(season=SEASON, headers=NBA_HEADERS, **kw).get_data_frames()[0]
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                raise e

def pbp_fetch(endpoint, params, retries=3):
    for attempt in range(retries):
        try:
            time.sleep(1)
            r = requests.get(f"{PBP_BASE}/{endpoint}", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                print(f"    ERRO em {endpoint}: {e}")
                return {}

# ── 1. Stats básicas ────────────────────────────────────────────────────────
print("Coletando stats básicas...")
base_df = nba_fetch(LeagueDashPlayerStats, measure_type_detailed_defense="Base", per_mode_detailed="PerGame")
totals_df = nba_fetch(LeagueDashPlayerStats, measure_type_detailed_defense="Base", per_mode_detailed="Totals")

eligible = base_df[(base_df["MIN"] >= MIN_MINUTES) & (base_df["GP"] >= MIN_GAMES)].copy()
print(f"  {len(eligible)} jogadores elegíveis")

player_ids = eligible["PLAYER_ID"].tolist()
totals_idx = {r["PLAYER_ID"]: r for r in totals_df.to_dict(orient="records")}

# ── 2. Stats avançadas ──────────────────────────────────────────────────────
print("Coletando stats avançadas...")
adv_df = nba_fetch(LeagueDashPlayerStats, measure_type_detailed_defense="Advanced", per_mode_detailed="PerGame")
adv_idx = {r["PLAYER_ID"]: r for r in adv_df.to_dict(orient="records")}

# ── 3. PBPStats — totals ────────────────────────────────────────────────────
print("Coletando pbpstats totals...")
pbp_totals = pbp_fetch("get-totals/nba", {"Season": SEASON, "SeasonType": "Regular Season", "Type": "Player"})
pbp_totals_idx = {str(r.get("EntityId","")): r for r in pbp_totals.get("multi_row_table_data", [])}

# ── 4. PBPStats — assist combo ──────────────────────────────────────────────
print("Coletando pbpstats assist combos...")
assist_raw = pbp_fetch("get-assist-combo-summary/nba", {"Season": SEASON, "SeasonType": "Regular Season"})
assist_rows = assist_raw.get("results", [])
print(f"  {len(assist_rows)} combinações encontradas")
assists_scored = {}
assists_given  = {}
for row in assist_rows:
    scorer = str(row.get("scorer_player_id", ""))
    passer = str(row.get("assist_player_id", ""))
    if scorer not in assists_scored: assists_scored[scorer] = []
    assists_scored[scorer].append(row)
    if passer not in assists_given: assists_given[passer] = []
    assists_given[passer].append(row)

# ── 5. Lineups por time (30 chamadas) ──────────────────────────────────────
print("Coletando lineups por time...")
lineups_by_player = {}
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
            team_abbr = df["TEAM_ABBREVIATION"].iloc[0] if len(df) > 0 else ""
            for _, row in df.iterrows():
                group_id = row["GROUP_ID"]
                pids_in_lineup = [p for p in group_id.split("-") if p]
                lineup_data = {
                    "team": team_abbr,
                    "lineup": row["GROUP_NAME"],
                    "minutes": round(row["MIN"] or 0, 1),
                    "off_rtg": round(row["OFF_RATING"] or 0, 1),
                    "def_rtg": round(row["DEF_RATING"] or 0, 1),
                    "net_rtg": round(row["NET_RATING"] or 0, 1),
                }
                for pid in pids_in_lineup:
                    if pid not in lineups_by_player:
                        lineups_by_player[pid] = []
                    lineups_by_player[pid].append(lineup_data)
            break
        except Exception as e:
            if attempt < 2:
                print(f"    Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                print(f"    ERRO no time {tid}: {e}")

# ── 6. Bio — reusa existente ou busca individual ────────────────────────────
print(f"\nVerificando bio de {len(player_ids)} jogadores...")
players_bio = {}

for i, pid in enumerate(player_ids):
    pid_str = str(pid)
    name = eligible[eligible["PLAYER_ID"] == pid]["PLAYER_NAME"].values[0]
    current_team = str(eligible[eligible["PLAYER_ID"] == pid]["TEAM_ABBREVIATION"].values[0])

    ex = existing_players.get(pid_str, {})
    if ex and ex.get("team") == current_team and ex.get("height") and ex.get("awards") is not None:
        print(f"  [{i+1}/{len(player_ids)}] {name} — bio reutilizada")
        players_bio[pid_str] = {
            "info": {
                "POSITION": ex.get("position",""),
                "HEIGHT": ex.get("height",""),
                "WEIGHT": ex.get("weight",""),
                "COUNTRY": ex.get("country",""),
                "DRAFT_YEAR": ex.get("draft_year",""),
                "DRAFT_ROUND": ex.get("draft_round",""),
                "DRAFT_NUMBER": ex.get("draft_number",""),
                "SCHOOL": ex.get("college",""),
                "JERSEY": ex.get("jersey",""),
            },
            "awards": [{"DESCRIPTION": a["description"], "SEASON": a["year"]} for a in ex.get("awards", [])],
        }
        continue

    print(f"  [{i+1}/{len(player_ids)}] {name} — buscando bio nova")
    try:
        time.sleep(1)
        info_df = CommonPlayerInfo(player_id=pid, headers=NBA_HEADERS).get_data_frames()[0]
        info = info_df.iloc[0].to_dict()
    except Exception as e:
        print(f"    CommonPlayerInfo ERRO: {e}")
        info = {}

    try:
        time.sleep(1)
        awards_df = PlayerAwards(player_id=pid, headers=NBA_HEADERS).get_data_frames()[0]
        awards = awards_df.to_dict(orient="records")
    except Exception as e:
        print(f"    PlayerAwards ERRO: {e}")
        awards = []

    players_bio[pid_str] = {"info": info, "awards": awards}

# ── 7. Montar resultado ─────────────────────────────────────────────────────
print("\nMontando resultado...")
players_out = {}

for _, row in eligible.iterrows():
    pid = row["PLAYER_ID"]
    pid_str = str(pid)
    name = row["PLAYER_NAME"]
    current_team = row["TEAM_ABBREVIATION"]

    base   = row.to_dict()
    totals = totals_idx.get(pid, {})
    adv    = adv_idx.get(pid, {})
    pbp    = pbp_totals_idx.get(pid_str, {})
    bio    = players_bio.get(pid_str, {})
    info   = bio.get("info", {})
    awards_raw = bio.get("awards", [])

    awards = []
    for a in awards_raw:
        desc = a.get("DESCRIPTION") or a.get("description","")
        year = a.get("SEASON") or a.get("year","")
        if desc:
            awards.append({"description": desc, "year": year})

    # Lineups — filtra pelo time atual
    player_lineups = sorted(
        [l for l in lineups_by_player.get(pid_str, []) if l.get("team") == current_team],
        key=lambda x: x["minutes"], reverse=True
    )[:5]
    player_lineups = [{k:v for k,v in l.items() if k != "team"} for l in player_lineups]

    # Assist network — filtra pelo time atual
    received = sorted(
        [r for r in assists_scored.get(pid_str, []) if r.get("team") == current_team],
        key=lambda x: x.get("total", 0), reverse=True
    )[:3]
    given = sorted(
        [g for g in assists_given.get(pid_str, []) if g.get("team") == current_team],
        key=lambda x: x.get("total", 0), reverse=True
    )[:3]

    # Shot zones
    def zone(fgm_k, fga_k):
        fgm = pbp.get(fgm_k, 0) or 0
        fga = pbp.get(fga_k, 0) or 0
        return {"fgm": fgm, "fga": fga, "pct": round(fgm/fga*100, 1) if fga > 0 else 0}

    # Como pontua
    gp = base.get("GP", 1) or 1
    pts_ast2       = pbp.get("PtsAssisted2s", 0) or 0
    pts_unast2     = pbp.get("PtsUnassisted2s", 0) or 0
    pts_ast3       = pbp.get("PtsAssisted3s", 0) or 0
    pts_unast3     = pbp.get("PtsUnassisted3s", 0) or 0
    pts_assisted   = pts_ast2 + pts_ast3
    pts_unassisted = pts_unast2 + pts_unast3
    pts_ft         = pbp.get("FtPoints", 0) or 0
    pts_putbacks   = pbp.get("PtsPutbacks", 0) or 0
    pts_total      = pbp.get("Points", 0) or 0

    pts_created_pg  = round(pts_unassisted / gp, 1)
    pts_assisted_pg = round(pts_assisted / gp, 1)
    pts_ft_pg       = round(pts_ft / gp, 1)
    pts_putbacks_pg = round(pts_putbacks / gp, 1)
    pts_total_pg    = round(pts_total / gp, 1) if pts_total > 0 else 0.1

    # FGA bloqueados
    fga_blocked_pg = round((pbp.get("Fg2aBlocked", 0) or 0) / gp, 1)

    # Turnovers
    tov_total      = pbp.get("Turnovers", 0) or 0
    tov_bad_pass   = (pbp.get("BadPassTurnovers", 0) or 0) + (pbp.get("BadPassOutOfBoundsTurnovers", 0) or 0)
    tov_lost_ball  = (pbp.get("LostBallTurnovers", 0) or 0) + (pbp.get("LostBallOutOfBoundsTurnovers", 0) or 0)
    tov_violations = max(0, tov_total - tov_bad_pass - tov_lost_ball)
    tov_live_pct   = round((pbp.get("LiveBallTurnoverPct", 0) or 0) * 100, 1)

    # On/off — reusa do existente
    ex = existing_players.get(pid_str, {})
    on_off = ex.get("on_off", {
        "on":  {"off_rtg":0,"def_rtg":0,"net_rtg":0,"efg":0,"oreb":0,"tov":0,"min":0},
        "off": {"off_rtg":0,"def_rtg":0,"net_rtg":0,"efg":0,"oreb":0,"tov":0,"min":0},
    })

    players_out[pid_str] = {
        "id": pid_str,
        "name": name,
        "team": current_team,
        "team_id": str(base.get("TEAM_ID", "")),
        "position": info.get("POSITION", base.get("PLAYER_POSITION", "")),
        "height": info.get("HEIGHT", ""),
        "weight": info.get("WEIGHT", ""),
        "country": info.get("COUNTRY", ""),
        "draft_year": info.get("DRAFT_YEAR", ""),
        "draft_round": info.get("DRAFT_ROUND", ""),
        "draft_number": info.get("DRAFT_NUMBER", ""),
        "college": info.get("SCHOOL", ""),
        "jersey": info.get("JERSEY", ""),
        "awards": awards,
        "games_played": int(base.get("GP", 0)),
        "per_game": {
            "pts":     round(base.get("PTS", 0) or 0, 1),
            "reb":     round(base.get("REB", 0) or 0, 1),
            "ast":     round(base.get("AST", 0) or 0, 1),
            "stl":     round(base.get("STL", 0) or 0, 1),
            "blk":     round(base.get("BLK", 0) or 0, 1),
            "fg2_pct": round((base.get("FGM", 0) - base.get("FG3M", 0)) /
                             max((base.get("FGA", 0) - base.get("FG3A", 0)), 1) * 100, 1),
            "fg3_pct": round((base.get("FG3_PCT", 0) or 0) * 100, 1),
            "min":     round(base.get("MIN", 0) or 0, 1),
            "tov":     round(base.get("TOV", 0) or 0, 1),
        },
        "totals": {
            "dd2": int(totals.get("DD2", 0) or 0),
            "td3": int(totals.get("TD3", 0) or 0),
        },
        "advanced": {
            "ts_pct":  round((adv.get("TS_PCT", 0) or 0) * 100, 1),
            "usg_pct": round((adv.get("USG_PCT", 0) or 0) * 100, 1),
            "off_rtg": round(adv.get("OFF_RATING", 0) or 0, 1),
            "def_rtg": round(adv.get("DEF_RATING", 0) or 0, 1),
            "net_rtg": round(adv.get("NET_RATING", 0) or 0, 1),
        },
        "shot_zones": {
            "at_rim":    zone("AtRimFGM", "AtRimFGA"),
            "short_mid": zone("ShortMidRangeFGM", "ShortMidRangeFGA"),
            "long_mid":  zone("LongMidRangeFGM", "LongMidRangeFGA"),
            "corner_3":  zone("Corner3FGM", "Corner3FGA"),
            "arc_3":     zone("Arc3FGM", "Arc3FGA"),
        },
        "scoring_profile": {
            "pts_created":      pts_created_pg,
            "pts_assisted_val": pts_assisted_pg,
            "pts_ft":           pts_ft_pg,
            "pts_putbacks":     pts_putbacks_pg,
            "pts_total_pg":     pts_total_pg,
            "fga_blocked_pg":   fga_blocked_pg,
        },
        "turnovers": {
            "total_pg":    round(tov_total / gp, 1),
            "bad_pass":    tov_bad_pass,
            "lost_ball":   tov_lost_ball,
            "violations":  tov_violations,
            "live_ball_pct": tov_live_pct,
        },
        "on_off": on_off,
        "lineups": player_lineups,
        "assist_network": {
            "received_from": [
                {
                    "name":      r.get("assist_player", ""),
                    "id":        str(r.get("assist_player_id", "")),
                    "total":     r.get("total", 0),
                    "at_rim":    r.get("atrim", 0),
                    "short_mid": r.get("shortmidrange", 0),
                    "long_mid":  r.get("longmidrange", 0),
                    "corner_3":  r.get("corner3", 0),
                    "arc_3":     r.get("arc3", 0),
                }
                for r in received
            ],
            "given_to": [
                {
                    "name":      g.get("scorer_player", ""),
                    "id":        str(g.get("scorer_player_id", "")),
                    "total":     g.get("total", 0),
                    "at_rim":    g.get("atrim", 0),
                    "short_mid": g.get("shortmidrange", 0),
                    "long_mid":  g.get("longmidrange", 0),
                    "corner_3":  g.get("corner3", 0),
                    "arc_3":     g.get("arc3", 0),
                }
                for g in given
            ],
        },
    }

output = {
    "season": SEASON,
    "updated": str(today),
    "players": players_out,
}

with open("jogadores.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! jogadores.json criado com {len(players_out)} jogadores.")