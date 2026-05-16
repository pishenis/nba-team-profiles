import json
import sys
import time
from datetime import date
from nba_api.stats.endpoints import (
    BoxScoreTraditionalV3,
    BoxScoreFourFactorsV3,
    BoxScoreMiscV3,
    BoxScoreHustleV2,
    PlayByPlayV3,
    BoxScoreMatchupsV3,
    BoxScoreSummaryV2,
)

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

if len(sys.argv) < 2:
    print("Uso: python3 coletar_jogo.py GAME_ID")
    sys.exit(1)

GAME_ID = sys.argv[1]
print(f"Coletando dados do jogo {GAME_ID}...")

def nba_get(cls, retries=3, **kw):
    for attempt in range(retries):
        try:
            time.sleep(1.5)
            return cls(game_id=GAME_ID, headers=NBA_HEADERS, timeout=60, **kw).get_data_frames()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Tentativa {attempt+1} falhou, aguardando 5s...")
                time.sleep(5)
            else:
                print(f"  ERRO: {e}")
                return None

# ── 1. Resumo ───────────────────────────────────────────────────────────────
print("Coletando resumo...")
summary_dfs = nba_get(BoxScoreSummaryV2)
if not summary_dfs:
    print("Erro ao coletar resumo. Abortando.")
    sys.exit(1)

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

print(f"  {away_abbr} {away_pts} @ {home_abbr} {home_pts} · {game_date}")

# ── 2. Box score ─────────────────────────────────────────────────────────────
print("Coletando box score...")
trad_dfs = nba_get(BoxScoreTraditionalV3)

def parse_players(df):
    players = []
    for _, row in df.iterrows():
        if not row.get("minutes") or str(row["minutes"]) in ["None","nan",""]:
            continue
        players.append({
            "id":       str(row.get("personId","")),
            "name":     row.get("nameI",""),
            "pos":      row.get("position",""),
            "jersey":   str(row.get("jerseyNum","")),
            "minutes":  str(row.get("minutes",""))[:5],
            "pts":      int(row.get("points",0) or 0),
            "oreb":     int(row.get("reboundsOffensive",0) or 0),
            "dreb":     int(row.get("reboundsDefensive",0) or 0),
            "reb":      int(row.get("reboundsTotal",0) or 0),
            "ast":      int(row.get("assists",0) or 0),
            "stl":      int(row.get("steals",0) or 0),
            "blk":      int(row.get("blocks",0) or 0),
            "tov":      int(row.get("turnovers",0) or 0),
            "fgm":      int(row.get("fieldGoalsMade",0) or 0),
            "fga":      int(row.get("fieldGoalsAttempted",0) or 0),
            "fg3m":     int(row.get("threePointersMade",0) or 0),
            "fg3a":     int(row.get("threePointersAttempted",0) or 0),
            "ftm":      int(row.get("freeThrowsMade",0) or 0),
            "fta":      int(row.get("freeThrowsAttempted",0) or 0),
            "plus_minus": int(row.get("plusMinusPoints",0) or 0),
            "starter":  row.get("comment","") == "",
        })
    return players

box_home, box_away = [], []
if trad_dfs:
    players_df = trad_dfs[0]
    box_home = parse_players(players_df[players_df["teamTricode"] == home_abbr])
    box_away = parse_players(players_df[players_df["teamTricode"] == away_abbr])

minutes_played = {}
for p in box_home + box_away:
    try:
        parts = p["minutes"].split(":")
        mins = int(parts[0]) + int(parts[1])/60
        minutes_played[p["id"]] = mins
    except:
        minutes_played[p["id"]] = 0

# ── 3. Four Factors ──────────────────────────────────────────────────────────
print("Coletando four factors...")
ff_dfs = nba_get(BoxScoreFourFactorsV3)

ff_home, ff_away = {}, {}
if ff_dfs:
    for _, row in ff_dfs[1].iterrows():
        data = {
            "efg":      round((row.get("effectiveFieldGoalPercentage",0) or 0)*100, 1),
            "ftr":      round(row.get("freeThrowAttemptRate",0) or 0, 3),
            "tov":      round((row.get("teamTurnoverPercentage",0) or 0)*100, 1),
            "oreb":     round((row.get("offensiveReboundPercentage",0) or 0)*100, 1),
            "opp_efg":  round((row.get("oppEffectiveFieldGoalPercentage",0) or 0)*100, 1),
            "opp_ftr":  round(row.get("oppFreeThrowAttemptRate",0) or 0, 3),
            "opp_tov":  round((row.get("oppTeamTurnoverPercentage",0) or 0)*100, 1),
            "opp_oreb": round((row.get("oppOffensiveReboundPercentage",0) or 0)*100, 1),
        }
        if row["teamTricode"] == home_abbr:
            ff_home = data
        else:
            ff_away = data

# ── 4. Misc stats ────────────────────────────────────────────────────────────
print("Coletando misc stats...")
misc_dfs = nba_get(BoxScoreMiscV3)

misc_home, misc_away = {}, {}
if misc_dfs and len(misc_dfs) >= 2:
    for _, row in misc_dfs[1].iterrows():
        data = {
            "pts_fb":         int(row.get("pointsFastBreak", 0) or 0),
            "pts_paint":      int(row.get("pointsPaint", 0) or 0),
            "pts_2nd_chance": int(row.get("pointsSecondChance", 0) or 0),
            "blocks":         int(row.get("blocks", 0) or 0),
        }
        if row["teamTricode"] == home_abbr:
            misc_home = data
        else:
            misc_away = data

# ── 5. Hustle stats ──────────────────────────────────────────────────────────
print("Coletando hustle stats...")
hustle_dfs = nba_get(BoxScoreHustleV2)

hustle_home, hustle_away = {}, {}
if hustle_dfs:
    for i, df in enumerate(hustle_dfs):
        if "teamTricode" in df.columns and "personId" not in df.columns and len(df) <= 3:
            for _, row in df.iterrows():
                data = {
                    "deflections":     int(row.get("deflections", 0) or 0),
                    "contested_shots": int(row.get("contestedShots", 0) or 0),
                    "contested_2pt":   int(row.get("contestedShots2pt", 0) or 0),
                    "contested_3pt":   int(row.get("contestedShots3pt", 0) or 0),
                    "charges_drawn":   int(row.get("chargesDrawn", 0) or 0),
                }
                if row["teamTricode"] == home_abbr:
                    hustle_home = data
                else:
                    hustle_away = data
            break

# ── 6. Play by play ──────────────────────────────────────────────────────────
print("Coletando play by play...")
pbp_dfs = nba_get(PlayByPlayV3)

score_timeline = []
shots = []
quarter_scores_home = {}
quarter_scores_away = {}
lead_changes = 0
ties = 0
prev_diff = None
home_lead_min = 0.0
away_lead_min = 0.0
tied_min = 0.0
prev_abs_min = 0.0
prev_period = 0

# Runs em janela de 5 min
best_run_home = {"pts_home": 0, "pts_away": 0, "start_min": 0, "end_min": 0}
best_run_away = {"pts_home": 0, "pts_away": 0, "start_min": 0, "end_min": 0}

# Sequência sem resposta
consec_home = 0
consec_away = 0
max_consec_home = 0
max_consec_away = 0

# Zonas de arremesso
ZONE_KEYS = ["at_rim","paint","mid","corner_3","arc_3"]
shot_zones = {abbr: {k: {"fgm":0,"fga":0} for k in ZONE_KEYS} for abbr in [home_abbr, away_abbr]}

def classify_zone(x, y, value):
    dist = (x**2 + y**2) ** 0.5
    if abs(x) >= 220 and y <= 90:
        return "corner_3"
    elif value == 3 or dist >= 237:
        return "arc_3"
    elif dist <= 40:
        return "at_rim"
    elif abs(x) <= 80 and y <= 190:
        return "paint"
    else:
        return "mid"

max_period = 4
if pbp_dfs:
    pbp = pbp_dfs[0]
    last_home, last_away = 0, 0

    for _, row in pbp.iterrows():
        period = int(row.get("period", 0) or 0)
        clock  = str(row.get("clock","PT0M0.00S"))

        try:
            clock_str = clock.replace("PT","").replace("S","")
            parts = clock_str.split("M")
            mins_left = float(parts[0])
            secs_left = float(parts[1]) if len(parts)>1 else 0
            period_elapsed = 12 - mins_left - secs_left/60
            if period <= 4:
                abs_min = (period-1)*12 + period_elapsed
            else:
                abs_min = 48 + (period-5)*5 + (5 - mins_left - secs_left/60)
        except:
            abs_min = prev_abs_min

        if period != prev_period and prev_period > 0:
            quarter_scores_home[prev_period] = last_home - sum(quarter_scores_home.get(q,0) for q in range(1,prev_period))
            quarter_scores_away[prev_period] = last_away - sum(quarter_scores_away.get(q,0) for q in range(1,prev_period))

        sh = str(row.get("scoreHome","") or "")
        sa = str(row.get("scoreAway","") or "")
        scored = False
        prev_home = last_home
        prev_away = last_away

        if sh.isdigit():
            last_home = int(sh)
            scored = True
        if sa.isdigit():
            last_away = int(sa)
            scored = True

        if scored:
            # Sequência sem resposta
            home_scored_now = last_home > prev_home
            away_scored_now = last_away > prev_away
            if home_scored_now and not away_scored_now:
                consec_home += last_home - prev_home
                consec_away = 0
                max_consec_home = max(max_consec_home, consec_home)
            elif away_scored_now and not home_scored_now:
                consec_away += last_away - prev_away
                consec_home = 0
                max_consec_away = max(max_consec_away, consec_away)
            else:
                consec_home = 0
                consec_away = 0

            # Liderança
            dt = abs_min - prev_abs_min
            if prev_diff is not None:
                if prev_diff > 0: home_lead_min += dt
                elif prev_diff < 0: away_lead_min += dt
                else: tied_min += dt
            diff = last_home - last_away
            if prev_diff is not None:
                if (prev_diff > 0 and diff < 0) or (prev_diff < 0 and diff > 0):
                    lead_changes += 1
                if diff == 0 and prev_diff != 0:
                    ties += 1
            prev_diff = diff
            prev_abs_min = abs_min

            score_timeline.append({
                "min": round(abs_min, 2),
                "home": last_home,
                "away": last_away,
                "period": period,
            })

        # Arremessos
        is_shot = int(row.get("isFieldGoal", 0) or 0)
        if is_shot:
            x = int(row.get("xLegacy", 0) or 0)
            y = int(row.get("yLegacy", 0) or 0)
            made = str(row.get("shotResult","")) == "Made"
            value = int(row.get("shotValue", 2) or 2)
            team = str(row.get("teamTricode",""))
            zone = ""
            if x or y:
                zone = classify_zone(x, y, value)
                if team in shot_zones:
                    shot_zones[team][zone]["fga"] += 1
                    if made:
                        shot_zones[team][zone]["fgm"] += 1
            shots.append({
                "team": team, "player": str(row.get("playerNameI","")),
                "x": x, "y": y, "made": made, "value": value,
                "period": period, "desc": str(row.get("description","")), "zone": zone,
            })

        prev_period = period

    if prev_period > 0:
        quarter_scores_home[prev_period] = last_home - sum(quarter_scores_home.get(q,0) for q in range(1,prev_period))
        quarter_scores_away[prev_period] = last_away - sum(quarter_scores_away.get(q,0) for q in range(1,prev_period))

    remaining = (48 if prev_period <= 4 else 48+(prev_period-4)*5) - prev_abs_min
    if prev_diff is not None and remaining > 0:
        if prev_diff > 0: home_lead_min += remaining
        elif prev_diff < 0: away_lead_min += remaining
        else: tied_min += remaining

# Zonas pct
for abbr in shot_zones:
    for z in ZONE_KEYS:
        fgm = shot_zones[abbr][z]["fgm"]
        fga = shot_zones[abbr][z]["fga"]
        shot_zones[abbr][z]["pct"] = round(fgm/fga*100, 1) if fga > 0 else 0

# Maior run em janela de 5 minutos
WINDOW = 5.0
for i, ev in enumerate(score_timeline):
    window_start = ev["min"] - WINDOW
    start_home, start_away = 0, 0
    for j in range(i-1, -1, -1):
        if score_timeline[j]["min"] <= window_start:
            start_home = score_timeline[j]["home"]
            start_away = score_timeline[j]["away"]
            break
    pts_home = ev["home"] - start_home
    pts_away = ev["away"] - start_away
    if pts_home - pts_away > best_run_home["pts_home"] - best_run_home["pts_away"]:
        best_run_home = {"pts_home": pts_home, "pts_away": pts_away,
                         "start_min": round(max(0, window_start), 1), "end_min": round(ev["min"], 1)}
    if pts_away - pts_home > best_run_away["pts_away"] - best_run_away["pts_home"]:
        best_run_away = {"pts_home": pts_home, "pts_away": pts_away,
                         "start_min": round(max(0, window_start), 1), "end_min": round(ev["min"], 1)}

def fmt_min(m):
    total_secs = int(round(m * 60))
    return f"{total_secs//60}:{total_secs%60:02d}"

def min_to_clock(m):
    if m < 0: m = 0
    q = min(4, int(m // 12) + 1)
    elapsed = m - (q-1)*12
    remaining = 12 - elapsed
    mins = int(remaining)
    secs = int(round((remaining - mins) * 60))
    return f"{mins}:{secs:02d} {q}Q"

gmax_period = max(quarter_scores_home.keys()) if quarter_scores_home else 4
game_flow = {
    "quarter_scores": {
        home_abbr: [quarter_scores_home.get(q,0) for q in range(1, max_period+1)],
        away_abbr: [quarter_scores_away.get(q,0) for q in range(1, max_period+1)],
    },
    "num_periods": max_period,
    "lead_changes": lead_changes,
    "ties": ties,
    "time_leading_home_fmt": fmt_min(home_lead_min),
    "time_leading_away_fmt": fmt_min(away_lead_min),
    "time_tied_fmt": fmt_min(tied_min),
    "best_run_home": best_run_home,
    "best_run_away": best_run_away,
    "max_consec_home": max_consec_home,
    "max_consec_away": max_consec_away,
}

print(f"  Liderança: {home_abbr} {fmt_min(home_lead_min)} · {away_abbr} {fmt_min(away_lead_min)}")
print(f"  Trocas: {lead_changes} · Empates: {ties}")
print(f"  Run {home_abbr}: {best_run_home['pts_home']}-{best_run_home['pts_away']} ({min_to_clock(best_run_home['start_min'])} a {min_to_clock(best_run_home['end_min'])})")
print(f"  Run {away_abbr}: {best_run_away['pts_away']}-{best_run_away['pts_home']} ({min_to_clock(best_run_away['start_min'])} a {min_to_clock(best_run_away['end_min'])})")
print(f"  Sequência sem resposta: {home_abbr} {max_consec_home} · {away_abbr} {max_consec_away}")

# ── 7. Matchups ──────────────────────────────────────────────────────────────
print("Coletando matchups...")
mu_dfs = nba_get(BoxScoreMatchupsV3)

matchups = []
if mu_dfs:
    for _, row in mu_dfs[0].iterrows():
        fga = int(row.get("matchupFieldGoalsAttempted",0) or 0)
        off_id = str(row.get("personIdOff",""))
        if fga < 3: continue
        if minutes_played.get(off_id, 0) < 20: continue
        matchups.append({
            "off_id":   off_id,
            "off_name": str(row.get("nameIOff","")),
            "off_team": str(row.get("teamTricode","")),
            "def_id":   str(row.get("personIdDef","")),
            "def_name": str(row.get("nameIDef","")),
            "minutes":  str(row.get("matchupMinutes","")),
            "fgm":      int(row.get("matchupFieldGoalsMade",0) or 0),
            "fga":      fga,
            "fg_pct":   round((row.get("matchupFieldGoalsPercentage",0) or 0)*100, 1),
            "fg3m":     int(row.get("matchupThreePointersMade",0) or 0),
            "fg3a":     int(row.get("matchupThreePointersAttempted",0) or 0),
            "pts":      int(row.get("playerPoints",0) or 0),
            "partial_poss": round(row.get("partialPossessions",0) or 0, 1),
        })

matchups.sort(key=lambda x: x["fga"], reverse=True)

# ── 8. Output ─────────────────────────────────────────────────────────────────
# Fallback: se pts vieram zerados do line_score, soma pelo box score
if home_pts == 0 and away_pts == 0 and (box_home or box_away):
    home_pts = sum(p.get("pts", 0) for p in box_home)
    away_pts = sum(p.get("pts", 0) for p in box_away)
    print(f"  pts corrigidos pelo box score: {away_abbr} {away_pts} @ {home_abbr} {home_pts}")
output = {
    "game_id":   GAME_ID,
    "date":      game_date,
    "home":      home_abbr,
    "away":      away_abbr,
    "home_pts":  home_pts,
    "away_pts":  away_pts,
    "winner":    home_abbr if home_pts > away_pts else away_abbr,
    "game_flow": game_flow,
    "four_factors": {home_abbr: ff_home, away_abbr: ff_away},
    "misc":      {home_abbr: misc_home, away_abbr: misc_away},
    "hustle":    {home_abbr: hustle_home, away_abbr: hustle_away},
    "box_score": {home_abbr: box_home, away_abbr: box_away},
    "score_timeline": score_timeline,
    "shots":     shots,
    "shot_zones": shot_zones,
    "matchups":  matchups,
    "collected": str(date.today()),
}

filename = f"jogo_{GAME_ID}.json"
with open(filename, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! {filename} criado.")
print(f"  Box score: {len(box_home)} {home_abbr} · {len(box_away)} {away_abbr}")
print(f"  Timeline: {len(score_timeline)} eventos · Arremessos: {len(shots)}")
print(f"  Matchups filtrados: {len(matchups)}")