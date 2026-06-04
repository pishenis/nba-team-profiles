#!/usr/bin/env python3
"""
coletar_jogo.py — BallDontLie edition
Uso:
  python3 coletar_jogo.py <YYYY-MM-DD>   # busca jogo de playoffs na data
  python3 coletar_jogo.py <bdl_id>       # coleta pelo ID numérico do BDL
"""

import json, os, re, sys, time
from datetime import date as dt_date
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BDL_API_KEY")
if not API_KEY:
    print("ERRO: BDL_API_KEY não encontrado no .env")
    sys.exit(1)

HEADERS  = {"Authorization": API_KEY}
BASE_V1  = "https://api.balldontlie.io/nba/v1"
BASE_V2  = "https://api.balldontlie.io/nba/v2"

# ─── helpers de API ──────────────────────────────────────────────────────────

def get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            time.sleep(0.4)
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if r.status_code == 429:
                print("  Rate limit, aguardando 15s...")
                time.sleep(15)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Tentativa {attempt + 1} falhou: {e}, aguardando 5s...")
                time.sleep(5)
            else:
                raise

def all_pages(url, params=None):
    params = dict(params or {})
    params["per_page"] = 100
    items = []
    while True:
        data = get(url, params)
        items.extend(data.get("data", []))
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
    return items

# ─── helpers gerais ──────────────────────────────────────────────────────────

def abbr(team_obj):
    return (team_obj or {}).get("abbreviation", "")

def short_name(player):
    fn = (player.get("first_name") or "")
    ln = (player.get("last_name") or "")
    return f"{fn[0]}. {ln}" if fn else ln

def clock_to_min(clock, period):
    try:
        parts = clock.split(":")
        mins = int(parts[0])
        secs = int(parts[1]) if len(parts) > 1 else 0
        remaining = mins + secs / 60
        dur  = 12 if period <= 4 else 5
        base = (period - 1) * 12 if period <= 4 else 48 + (period - 5) * 5
        return round(base + dur - remaining, 2)
    except Exception:
        return 0.0

def fmt_clock(clock, period):
    labels = {1: "1Q", 2: "2Q", 3: "3Q", 4: "4Q"}
    lbl = labels.get(period, f"OT{period - 4}")
    return f"{clock} {lbl}"

def fmt_min(total_min):
    total_min = max(0, total_min)
    m = int(total_min)
    s = int(round((total_min - m) * 60))
    return f"{m}:{s:02d}"

def agg(lst, key):
    return sum((x.get(key) or 0) for x in lst)

# ─── cálculos de jogo ────────────────────────────────────────────────────────

def compute_game_flow(plays, home_abbr, away_abbr):
    scoring = [
        p for p in plays
        if p.get("scoring_play") and p.get("team") and p.get("score_value", 0) > 0
    ]

    time_home = 0.0
    time_away = 0.0
    time_tied = 0.0
    lead_changes = 0
    score_ties = 0
    prev_leader = None
    prev_min = 0.0

    for play in scoring:
        cur_min = clock_to_min(play.get("clock", "0:00"), play.get("period", 1))
        diff = cur_min - prev_min
        if prev_leader == "home":   time_home += diff
        elif prev_leader == "away": time_away += diff
        else:                       time_tied += diff

        h = play.get("home_score", 0)
        a = play.get("away_score", 0)
        new_leader = "home" if h > a else ("away" if a > h else None)

        if new_leader != prev_leader:
            if new_leader is None:    score_ties   += 1
            elif prev_leader is not None: lead_changes += 1

        prev_leader = new_leader
        prev_min = cur_min

    max_period = max((p.get("period", 1) for p in plays), default=4)
    total = 48 + max(0, max_period - 4) * 5
    remaining = total - prev_min
    if prev_leader == "home":   time_home += remaining
    elif prev_leader == "away": time_away += remaining
    else:                       time_tied += remaining

    # Maior sequência
    best = {home_abbr: (0, 0, "", ""), away_abbr: (0, 0, "", "")}
    for focal in [home_abbr, away_abbr]:
        opp = away_abbr if focal == home_abbr else home_abbr
        cur_f, cur_o = 0, 0
        started = False
        start_c, start_p = "", 1

        for play in scoring:
            team = abbr(play.get("team", {}))
            val  = play.get("score_value", 0)
            c, p = play.get("clock", ""), play.get("period", 1)

            if team == focal:
                if not started:
                    start_c, start_p = c, p
                    started = True
                cur_f += val
                if cur_f > best[focal][0]:
                    best[focal] = (cur_f, cur_o, fmt_clock(start_c, start_p), fmt_clock(c, p))
            else:
                cur_o += val
                if cur_o >= cur_f and cur_f > 0:
                    cur_f, cur_o, started = 0, 0, False

    bh, ba = best[home_abbr], best[away_abbr]
    winner_run = home_abbr if bh[0] >= ba[0] else away_abbr
    bw = best[winner_run]

    return {
        "time_leading": {home_abbr: fmt_min(time_home), away_abbr: fmt_min(time_away)},
        "time_tied":    fmt_min(time_tied),
        "lead_changes": lead_changes,
        "score_ties":   score_ties,
        "biggest_run": {
            "team":  winner_run,
            "run":   f"{bw[0]}-{bw[1]}",
            "start": bw[2],
            "end":   bw[3],
            home_abbr: f"{bh[0]}-{bh[1]}",
            away_abbr: f"{ba[0]}-{ba[1]}",
        },
    }


def quarter_scores_from_game(game_data, home_abbr, away_abbr):
    home_qs, away_qs = [], []
    for q in range(1, 5):
        home_qs.append(game_data.get(f"home_q{q}") or 0)
        away_qs.append(game_data.get(f"visitor_q{q}") or 0)
    for ot in range(1, 4):
        h = game_data.get(f"home_ot{ot}")
        a = game_data.get(f"visitor_ot{ot}")
        if h is not None and (h > 0 or (a or 0) > 0):
            home_qs.append(h or 0)
            away_qs.append(a or 0)
    return {home_abbr: home_qs, away_abbr: away_qs}, len(home_qs)


def build_shot_zones(plays, home_abbr, away_abbr):
    zones = {
        t: {"ra": [0,0], "paint_non_ra": [0,0], "mid": [0,0], "corner_3": [0,0], "above_3": [0,0]}
        for t in [home_abbr, away_abbr]
    }
    for play in plays:
        if not play.get("shooting_play"):
            continue
        x = play.get("coordinate_x")
        y = play.get("coordinate_y")
        team = abbr(play.get("team", {}))
        if team not in zones or x is None or y is None:
            continue
        made = 1 if play.get("scoring_play") else 0
        is_3 = "3" in (play.get("type") or "")
        dist = (x**2 + y**2) ** 0.5
        if dist <= 4:             zone = "ra"
        elif is_3 and abs(x)>=22: zone = "corner_3"
        elif is_3:                zone = "above_3"
        elif dist <= 12:          zone = "paint_non_ra"
        else:                     zone = "mid"
        zones[team][zone][0] += made
        zones[team][zone][1] += 1
    return zones


def build_players_from_box(team_section, starter_ids, lineup_pos, adv_by_pid):
    players = []
    for p in (team_section or {}).get("players", []):
        player = p.get("player", {})
        pid    = player.get("id")
        mins   = p.get("min", "") or ""
        if not mins or mins in ("0", "0:00"):
            continue
        adv = adv_by_pid.get(pid, {})
        is_s = pid in starter_ids
        players.append({
            "name":           short_name(player),
            "minutes":        mins,
            "pos":            lineup_pos.get(pid, player.get("position","")) if is_s else "",
            "starter":        is_s,
            "pts":            p.get("pts", 0),
            "reb":            p.get("reb", 0),
            "oreb":           p.get("oreb", 0),
            "ast":            p.get("ast", 0),
            "stl":            p.get("stl", 0),
            "blk":            p.get("blk", 0),
            "tov":            p.get("turnover", 0),
            "fgm":            p.get("fgm", 0),
            "fga":            p.get("fga", 0),
            "fg3m":           p.get("fg3m", 0),
            "fg3a":           p.get("fg3a", 0),
            "ftm":            p.get("ftm", 0),
            "fta":            p.get("fta", 0),
            "pf":             p.get("pf", 0),
            "plus_minus":     p.get("plus_minus") or 0,
            "off_rating":     adv.get("offensive_rating"),
            "def_rating":     adv.get("defensive_rating"),
            "ts_pct":         adv.get("true_shooting_percentage"),
            "deflections":    adv.get("deflections"),
            "charges_drawn":  adv.get("charges_drawn"),
            "contested_shots":adv.get("contested_shots"),
        })
    return players


def build_players_from_stats(stats_list, team_a, starter_ids, lineup_pos, adv_by_pid):
    players = []
    for s in stats_list:
        player = s.get("player", {})
        pid    = player.get("id")
        mins   = s.get("min", "") or ""
        if not mins or mins in ("0", "0:00"):
            continue
        adv = adv_by_pid.get(pid, {})
        is_s = pid in starter_ids
        players.append({
            "name":           short_name(player),
            "minutes":        mins,
            "pos":            lineup_pos.get(pid, player.get("position","")) if is_s else "",
            "starter":        is_s,
            "pts":            s.get("pts", 0),
            "reb":            s.get("reb", 0),
            "oreb":           s.get("oreb", 0),
            "ast":            s.get("ast", 0),
            "stl":            s.get("stl", 0),
            "blk":            s.get("blk", 0),
            "tov":            s.get("turnover", 0),
            "fgm":            s.get("fgm", 0),
            "fga":            s.get("fga", 0),
            "fg3m":           s.get("fg3m", 0),
            "fg3a":           s.get("fg3a", 0),
            "ftm":            s.get("ftm", 0),
            "fta":            s.get("fta", 0),
            "pf":             s.get("pf", 0),
            "plus_minus":     s.get("plus_minus") or 0,
            "off_rating":     adv.get("offensive_rating"),
            "def_rating":     adv.get("defensive_rating"),
            "ts_pct":         adv.get("true_shooting_percentage"),
            "deflections":    adv.get("deflections"),
            "charges_drawn":  adv.get("charges_drawn"),
            "contested_shots":adv.get("contested_shots"),
        })
    return players

# ─── coleta ───────────────────────────────────────────────────────────────────

arg = sys.argv[1] if len(sys.argv) > 1 else None
if not arg:
    print("Uso: python3 coletar_jogo.py <YYYY-MM-DD ou bdl_game_id>")
    sys.exit(1)

# 1. Jogo
if re.match(r"^\d{4}-\d{2}-\d{2}$", arg):
    print(f"Buscando jogo de playoffs em {arg}...")
    raw = get(f"{BASE_V1}/games", {"dates[]": arg, "postseason": "true"})
    games_list = raw.get("data", [])
    if not games_list:
        raw = get(f"{BASE_V1}/games", {"dates[]": arg})
        games_list = raw.get("data", [])
    if not games_list:
        print(f"Nenhum jogo encontrado em {arg}.")
        sys.exit(1)
    if len(games_list) == 1:
        game_data = games_list[0]
    else:
        print("Mais de um jogo encontrado:")
        for i, g in enumerate(games_list):
            print(f"  [{i}] ID {g['id']} — {g['visitor_team']['abbreviation']} @ {g['home_team']['abbreviation']}")
        idx = int(input("Escolha o número: "))
        game_data = games_list[idx]
else:
    print(f"Buscando jogo BDL #{arg}...")
    game_data = get(f"{BASE_V1}/games/{arg}").get("data", {})

game_id   = game_data["id"]
home_abbr = abbr(game_data["home_team"])
away_abbr = abbr(game_data["visitor_team"])
home_pts  = game_data.get("home_team_score", 0) or 0
away_pts  = game_data.get("visitor_team_score", 0) or 0
game_date = game_data.get("date", str(dt_date.today()))
print(f"  {away_abbr} {away_pts} @ {home_abbr} {home_pts} · {game_date}")

# 2. Box score
print("Coletando box score...")
bs_raw = get(f"{BASE_V1}/box_scores", {"date": game_date}).get("data", [])
box_score_raw = None
for bs in bs_raw:
    ht = abbr(bs.get("home_team", {}).get("team", {}))
    if ht == home_abbr:
        box_score_raw = bs
        break

# 3. Lineups
print("Coletando lineups...")
lineups_raw = all_pages(f"{BASE_V1}/lineups", {"game_ids[]": game_id})
starter_ids = {lu["player"]["id"] for lu in lineups_raw if lu.get("starter")}
lineup_pos  = {lu["player"]["id"]: lu.get("position", "") for lu in lineups_raw}

# 4. Advanced stats V2
print("Coletando advanced stats...")
adv_raw    = all_pages(f"{BASE_V2}/stats/advanced", {"game_ids[]": game_id})
adv_by_pid = {a["player"]["id"]: a for a in adv_raw}

# 5. Play-by-play
print("Coletando play-by-play...")
plays_raw = get(f"{BASE_V1}/plays", {"game_id": game_id}).get("data", [])
print(f"  {len(plays_raw)} eventos")

# 6. Box score → dict por time
box_score = {}
if box_score_raw:
    box_score[home_abbr] = build_players_from_box(box_score_raw.get("home_team",{}), starter_ids, lineup_pos, adv_by_pid)
    box_score[away_abbr] = build_players_from_box(box_score_raw.get("visitor_team",{}), starter_ids, lineup_pos, adv_by_pid)
else:
    print("  Box score via /stats endpoint...")
    stats_raw = all_pages(f"{BASE_V1}/stats", {"game_ids[]": game_id})
    for team_a in [home_abbr, away_abbr]:
        team_stats = [s for s in stats_raw if abbr(s.get("team",{})) == team_a]
        box_score[team_a] = build_players_from_stats(team_stats, team_a, starter_ids, lineup_pos, adv_by_pid)

# Corrige pts zerados
if home_pts == 0 and away_pts == 0:
    home_pts = sum(p.get("pts",0) for p in box_score.get(home_abbr,[]))
    away_pts = sum(p.get("pts",0) for p in box_score.get(away_abbr,[]))
    print(f"  pts corrigidos pelo box score: {away_abbr} {away_pts} @ {home_abbr} {home_pts}")

# 7. Quartos
quarter_scores, num_periods = quarter_scores_from_game(game_data, home_abbr, away_abbr)

# 8. Dinâmica
dynamics = compute_game_flow(plays_raw, home_abbr, away_abbr)

# 9. Timeline
score_timeline = [
    {
        "min":     clock_to_min(p.get("clock","0:00"), p.get("period",1)),
        "home":    p.get("home_score", 0),
        "away":    p.get("away_score", 0),
        "period":  p.get("period", 1),
        "scoring": p.get("scoring_play", False),
        "text":    p.get("text", ""),
    }
    for p in plays_raw
]

# 10. Shot zones
shot_zones = build_shot_zones(plays_raw, home_abbr, away_abbr)

# 11. Arremessos individuais
shots = [
    {
        "x":    p.get("coordinate_x"),
        "y":    p.get("coordinate_y"),
        "made": p.get("scoring_play", False),
        "type": p.get("type", ""),
        "team": abbr(p.get("team",{})),
        "text": p.get("text", ""),
    }
    for p in plays_raw
    if p.get("shooting_play") and p.get("coordinate_x") is not None
]

# 12. Four factors, misc, hustle por time
ff, misc, hustle = {}, {}, {}
for t in [home_abbr, away_abbr]:
    ta    = [a for a in adv_raw if abbr(a.get("team",{})) == t]
    first = ta[0] if ta else {}
    ff[t] = {
        "efg_pct":      first.get("four_factors_efg_pct"),
        "tov_pct":      first.get("team_turnover_pct"),
        "oreb_pct":     first.get("four_factors_oreb_pct"),
        "ftr":          first.get("free_throw_attempt_rate"),
        "opp_efg_pct":  first.get("opp_efg_pct"),
        "opp_tov_pct":  first.get("opp_turnover_pct"),
        "opp_oreb_pct": first.get("opp_oreb_pct"),
        "opp_ftr":      first.get("opp_free_throw_attempt_rate"),
    }
    misc[t] = {
        "pts_paint":      agg(ta, "points_paint"),
        "pts_2nd_chance": agg(ta, "points_second_chance"),
        "pts_fastbreak":  agg(ta, "points_fast_break"),
        "pts_off_tov":    agg(ta, "points_off_turnovers"),
    }
    hustle[t] = {
        "deflections":           agg(ta, "deflections"),
        "charges_drawn":         agg(ta, "charges_drawn"),
        "contested_shots":       agg(ta, "contested_shots"),
        "loose_balls_recovered": agg(ta, "loose_balls_recovered_total"),
        "screen_assists":        agg(ta, "screen_assists"),
    }

# 13. Salva
output = {
    "game_id":       str(game_id),
    "date":          game_date,
    "home":          home_abbr,
    "away":          away_abbr,
    "home_pts":      home_pts,
    "away_pts":      away_pts,
    "winner":        home_abbr if home_pts > away_pts else away_abbr,
    "source":        "balldontlie",
    "game_flow": {
        "quarter_scores": quarter_scores,
        "num_periods":    num_periods,
        **dynamics,
    },
    "four_factors":   ff,
    "misc":           misc,
    "hustle":         hustle,
    "box_score":      box_score,
    "score_timeline": score_timeline,
    "shots":          shots,
    "shot_zones":     shot_zones,
    "matchups":       [],
    "collected":      str(dt_date.today()),
}

filename = f"jogo_{game_id}.json"
with open(filename, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nFeito! {filename} criado.")
print(f"  Box score: {len(box_score.get(home_abbr,[]))} {home_abbr} · {len(box_score.get(away_abbr,[]))} {away_abbr}")
print(f"  Timeline: {len(score_timeline)} eventos · Arremessos: {len(shots)}")
print(f"  Períodos: {num_periods}")
