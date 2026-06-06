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

HEADERS = {"Authorization": API_KEY}
BASE_V1 = "https://api.balldontlie.io/nba/v1"
BASE_V2 = "https://api.balldontlie.io/nba/v2"

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
                print(f"  Tentativa {attempt+1} falhou: {e}, aguardando 5s...")
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

def parse_clock(clock):
    """
    Aceita:
      'PT03M44.00S' (ISO 8601 do BDL)  → (3, 44)
      '3:44'                             → (3, 44)
    Retorna (minutos, segundos) restantes no período.
    """
    if not clock:
        return 0, 0
    # ISO 8601: PT##M##.##S
    m = re.match(r"PT(\d+)M([\d.]+)S", clock)
    if m:
        return int(m.group(1)), int(float(m.group(2)))
    # MM:SS
    m = re.match(r"(\d+):(\d+)", clock)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0

def clock_to_min(clock, period):
    """Converte clock restante + período em minutos decorridos."""
    mins, secs = parse_clock(clock)
    remaining = mins + secs / 60
    dur  = 12 if period <= 4 else 5
    base = (period - 1) * 12 if period <= 4 else 48 + (period - 5) * 5
    return round(base + dur - remaining, 2)

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

    # Tempo liderando e empates
    time_home = 0.0
    time_away = 0.0
    time_tied = 0.0
    lead_changes = 0
    ties = 0
    prev_leader = None
    prev_min = 0.0

    for play in scoring:
        cur_min = clock_to_min(play.get("clock", ""), play.get("period", 1))
        diff = max(0, cur_min - prev_min)
        if prev_leader == "home":   time_home += diff
        elif prev_leader == "away": time_away += diff
        else:                       time_tied += diff

        h = play.get("home_score", 0)
        a = play.get("away_score", 0)
        new_leader = "home" if h > a else ("away" if a > h else None)

        if new_leader != prev_leader:
            if new_leader is None:        ties        += 1
            elif prev_leader is not None: lead_changes += 1

        prev_leader = new_leader
        prev_min = cur_min

    max_period = max((p.get("period", 1) for p in plays), default=4)
    total = 48 + max(0, max_period - 4) * 5
    remaining = max(0, total - prev_min)
    if prev_leader == "home":   time_home += remaining
    elif prev_leader == "away": time_away += remaining
    else:                       time_tied += remaining

    # Maiores runs — janela deslizante de 5 minutos
    WINDOW = 5.0
    scoring_pts = [
        (clock_to_min(p.get("clock",""), p.get("period",1)), abbr(p.get("team",{})), p.get("score_value",0))
        for p in scoring
    ]

    def best_window(focal, opp):
        best = {"pts_focal": 0, "pts_opp": 0, "start_min": 0, "end_min": 0}
        n = len(scoring_pts)
        j = 0
        for i in range(n):
            t_start = scoring_pts[i][0]
            t_end   = t_start + WINDOW
            fp, op  = 0, 0
            last_t  = t_start
            for k in range(i, n):
                t, team, val = scoring_pts[k]
                if t > t_end:
                    break
                if team == focal: fp += val
                else:             op += val
                last_t = t
            if fp - op > best["pts_focal"] - best["pts_opp"]:
                best = {"pts_focal": fp, "pts_opp": op, "start_min": t_start, "end_min": last_t}
        return best

    rh = best_window(home_abbr, away_abbr)
    ra = best_window(away_abbr, home_abbr)

    # Maior sequência sem resposta (adversário marca 0)
    def max_consec(focal):
        cur, best_c = 0, 0
        for _, team, val in scoring_pts:
            if team == focal:
                cur += val
                best_c = max(best_c, cur)
            else:
                cur = 0
        return best_c

    consec_home = max_consec(home_abbr)
    consec_away = max_consec(away_abbr)

    return {
        "time_leading_home_fmt": fmt_min(time_home),
        "time_leading_away_fmt": fmt_min(time_away),
        "time_tied_fmt":         fmt_min(time_tied),
        "lead_changes":          lead_changes,
        "ties":                  ties,
        "best_run_home": {
            "pts_home":  rh["pts_focal"],
            "pts_away":  rh["pts_opp"],
            "start_min": rh["start_min"],
            "end_min":   rh["end_min"],
        },
        "best_run_away": {
            "pts_away":  ra["pts_focal"],
            "pts_home":  ra["pts_opp"],
            "start_min": ra["start_min"],
            "end_min":   ra["end_min"],
        },
        "max_consec_home": consec_home,
        "max_consec_away": consec_away,
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
    """
    BDL: basket em (25, 0), x=0-50 (sideline), y=0-47 (rumo ao meio-campo).
    3-pointers: score_value=3 (feitos) ou dist>=22 (errados).
    Zonas esperadas pelo jogo.html: at_rim, paint, mid, corner_3, arc_3
    """
    BX, BY = 25.0, 0.0

    zones = {
        t: {"at_rim":   {"fgm":0,"fga":0},
            "paint":    {"fgm":0,"fga":0},
            "mid":      {"fgm":0,"fga":0},
            "corner_3": {"fgm":0,"fga":0},
            "arc_3":    {"fgm":0,"fga":0}}
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

        made  = 1 if play.get("scoring_play") else 0
        val   = play.get("score_value", 0)
        dist  = ((x - BX)**2 + (y - BY)**2) ** 0.5

        # Determina se é tentativa de 3
        if made:
            is_3 = (val == 3)
        else:
            is_3 = (dist >= 22.0)

        # Classifica zona
        if dist < 4.0:
            zone = "at_rim"
        elif is_3 and abs(x - BX) >= 20 and y <= 10:
            zone = "corner_3"
        elif is_3:
            zone = "arc_3"
        elif dist < 14.0:
            zone = "paint"
        else:
            zone = "mid"

        zones[team][zone]["fgm"] += made
        zones[team][zone]["fga"] += 1

    for t in zones:
        for z in zones[t]:
            fgm = zones[t][z]["fgm"]
            fga = zones[t][z]["fga"]
            zones[t][z]["pct"] = round(fgm / fga * 100) if fga else 0

    return zones


def build_players(team_section, starter_ids, lineup_pos, adv_by_pid):
    players = []
    for p in (team_section or {}).get("players", []):
        player = p.get("player", {})
        pid    = player.get("id")
        mins   = p.get("min", "") or ""
        if not mins or mins in ("0", "0:00"):
            continue
        adv  = adv_by_pid.get(pid, {})
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
            "mu_min":         adv.get("matchup_minutes"),
            "mu_fga":         adv.get("matchup_fga"),
            "mu_fgm":         adv.get("matchup_fgm"),
            "mu_fg_pct":      adv.get("matchup_fg_pct"),
            "mu_3pa":         adv.get("matchup_3pa"),
            "mu_3pm":         adv.get("matchup_3pm"),
            "mu_pts":         adv.get("matchup_player_points"),
            "mu_ast":         adv.get("matchup_assists"),
        })
    return players


def build_players_from_stats(stats_list, starter_ids, lineup_pos, adv_by_pid):
    players = []
    for s in stats_list:
        player = s.get("player", {})
        pid    = player.get("id")
        mins   = s.get("min", "") or ""
        if not mins or mins in ("0", "0:00"):
            continue
        adv  = adv_by_pid.get(pid, {})
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
            "mu_min":         adv.get("matchup_minutes"),
            "mu_fga":         adv.get("matchup_fga"),
            "mu_fgm":         adv.get("matchup_fgm"),
            "mu_fg_pct":      adv.get("matchup_fg_pct"),
            "mu_3pa":         adv.get("matchup_3pa"),
            "mu_3pm":         adv.get("matchup_3pm"),
            "mu_pts":         adv.get("matchup_player_points"),
            "mu_ast":         adv.get("matchup_assists"),
        })
    return players

# ─── coleta principal ─────────────────────────────────────────────────────────

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

# 4. Advanced stats V2 — period=0 para dados do jogo completo
print("Coletando advanced stats...")
adv_raw    = all_pages(f"{BASE_V2}/stats/advanced", {"game_ids[]": game_id, "period": 0})
adv_by_pid = {a["player"]["id"]: a for a in adv_raw}

# 5. Play-by-play
print("Coletando play-by-play...")
plays_raw = get(f"{BASE_V1}/plays", {"game_id": game_id}).get("data", [])
print(f"  {len(plays_raw)} eventos")

# 6. Box score por time
box_score = {}
if box_score_raw:
    box_score[home_abbr] = build_players(box_score_raw.get("home_team",{}), starter_ids, lineup_pos, adv_by_pid)
    box_score[away_abbr] = build_players(box_score_raw.get("visitor_team",{}), starter_ids, lineup_pos, adv_by_pid)
else:
    print("  Box score via /stats endpoint...")
    stats_raw = all_pages(f"{BASE_V1}/stats", {"game_ids[]": game_id})
    for team_a in [home_abbr, away_abbr]:
        team_stats = [s for s in stats_raw if abbr(s.get("team",{})) == team_a]
        box_score[team_a] = build_players_from_stats(team_stats, starter_ids, lineup_pos, adv_by_pid)

# Corrige pts zerados pelo box score
if home_pts == 0 and away_pts == 0:
    home_pts = sum(p.get("pts",0) for p in box_score.get(home_abbr,[]))
    away_pts = sum(p.get("pts",0) for p in box_score.get(away_abbr,[]))
    print(f"  pts corrigidos pelo box score: {away_abbr} {away_pts} @ {home_abbr} {home_pts}")

# 7. Quartos
quarter_scores, num_periods = quarter_scores_from_game(game_data, home_abbr, away_abbr)

# 8. Dinâmica do jogo
dynamics = compute_game_flow(plays_raw, home_abbr, away_abbr)

# 9. Timeline
score_timeline = [
    {
        "min":     clock_to_min(p.get("clock",""), p.get("period",1)),
        "home":    p.get("home_score", 0),
        "away":    p.get("away_score", 0),
        "period":  p.get("period", 1),
        "scoring": p.get("scoring_play", False),
        "text":    p.get("text", ""),
    }
    for p in plays_raw
]

# 10. Shot zones — chaves: at_rim, paint, mid, corner_3, arc_3
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

# 12. Four factors, misc, hustle — chaves devem bater com jogo.html
# Computa OReb% direto do box score (BDL retorna null para esse campo)
def team_oreb(t):
    return sum(p.get("oreb", 0) for p in box_score.get(t, []))
def team_dreb(t):
    return sum(p.get("reb", 0) - p.get("oreb", 0) for p in box_score.get(t, []))

home_orb = team_oreb(home_abbr)
away_orb = team_oreb(away_abbr)
home_drb = team_dreb(home_abbr)
away_drb = team_dreb(away_abbr)

def oreb_pct(orb, opp_drb):
    return round(orb / (orb + opp_drb) * 100, 1) if (orb + opp_drb) > 0 else 0

ff, misc, hustle = {}, {}, {}
for t in [home_abbr, away_abbr]:
    ta    = [a for a in adv_raw if abbr(a.get("team",{})) == t]
    first = ta[0] if ta else {}
    orb   = home_orb if t == home_abbr else away_orb
    opp_drb = away_drb if t == home_abbr else home_drb
    opp_orb = away_orb if t == home_abbr else home_orb
    my_drb  = home_drb if t == home_abbr else away_drb
    # four_factors: efg, tov, oreb, ftr (sem sufixo _pct)
    ff[t] = {
        "efg":      round((first.get("four_factors_efg_pct") or 0) * 100, 1),
        "tov":      round((first.get("team_turnover_pct") or 0) * 100, 1),
        "oreb":     oreb_pct(orb, opp_drb),
        "ftr":      round((first.get("free_throw_attempt_rate") or 0) * 100, 1),
        "opp_efg":  round((first.get("opp_efg_pct") or 0) * 100, 1),
        "opp_tov":  round((first.get("opp_turnover_pct") or 0) * 100, 1),
        "opp_oreb": oreb_pct(opp_orb, my_drb),
        "opp_ftr":  round((first.get("opp_free_throw_attempt_rate") or 0) * 100, 1),
    }
    # misc: pts_fb (não pts_fastbreak)
    misc[t] = {
        "pts_paint":      agg(ta, "points_paint"),
        "pts_fb":         agg(ta, "points_fast_break"),
        "pts_2nd_chance": agg(ta, "points_second_chance"),
        "pts_off_tov":    agg(ta, "points_off_turnovers"),
    }
    hustle[t] = {
        "deflections":           agg(ta, "deflections"),
        "charges_drawn":         agg(ta, "charges_drawn"),
        "contested_shots":       agg(ta, "contested_shots"),
        "contested_2pt":         agg(ta, "contested_shots_2pt"),
        "contested_3pt":         agg(ta, "contested_shots_3pt"),
        "loose_balls_recovered": agg(ta, "loose_balls_recovered_total"),
        "screen_assists":        agg(ta, "screen_assists"),
    }

# 13. Output final
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
