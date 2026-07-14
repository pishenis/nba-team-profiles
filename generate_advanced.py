"""
Bola Presa Stats — Gerador de Médias Avançadas por Jogador
Calcula PER (simplificado), PIE ponderado, TS%, net rating e usage.

Fontes:
  - /v1/season_averages  → stats de box score para PER
  - /v2/stats/advanced   → PIE, net rating, TS%, usage por jogo

Uso:
    python3 generate_advanced.py --api-key SUA_KEY
    python3 generate_advanced.py  # usa BDL_API_KEY do ambiente
"""

import os, sys, json, time, argparse, requests
from pathlib import Path
from _env_loader import load_env

BASE_URL   = "https://api.balldontlie.io"
SEASON     = 2025
OUTPUT_DIR = Path("data/salaries")
DELAY      = 0.15
BATCH_SIZE = 10

# Filtros de qualificação (aplicados sobre advanced stats)
MIN_GAMES    = 25    # mínimo de jogos
MIN_AVG_POSS = 35.0  # possessões médias por jogo (~20 min)
MIN_AVG_USG  = 0.10  # usage mínimo de 10%

# PER médio da liga (constante de normalização — média histórica NBA)
LEAGUE_AVG_PER = 15.0


def get_key(args_key):
    load_env()
    key = args_key or os.environ.get("BDL_API_KEY", "")
    if not key:
        print("ERRO: informe a API key via --api-key ou BDL_API_KEY")
        sys.exit(1)
    return key


def bdl_get(path, params, headers):
    url = BASE_URL + path
    for attempt in range(3):
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"    Rate limit — aguardando {wait}s...")
            time.sleep(wait)
        else:
            print(f"    ERRO {r.status_code}: {r.text[:120]}")
            return {}
    return {}


# ── SEASON AVERAGES (para PER) ───────────────────────────────────────────────

def fetch_season_averages(player_ids, headers):
    """
    Busca médias de temporada via /v1/season_averages.
    Endpoint aceita apenas um player_id por vez.
    Retorna dict: player_id → stats dict.
    """
    result = {}
    total = len(player_ids)
    for i, pid in enumerate(player_ids):
        if i % 50 == 0:
            print(f"  Season averages: {i}/{total}...")
        data = bdl_get("/v1/season_averages", {"season": SEASON, "player_id": pid}, headers)
        for row in data.get("data", []):
            rpid = row.get("player_id")
            if rpid:
                result[rpid] = row
        time.sleep(DELAY)
    return result


def parse_min(val):
    """Converte '35:11' ou 35.18 para float de minutos."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        parts = str(val).split(":")
        return int(parts[0]) + int(parts[1]) / 60
    except (IndexError, ValueError):
        return 0.0


def calc_per(s):
    """PER simplificado de Hollinger, normalizado para média da liga = 15."""
    try:
        min_ = parse_min(s.get("min"))
        if min_ < 10:
            return None
        pts  = float(s.get("pts")      or 0)
        fgm  = float(s.get("fgm")      or 0)
        fga  = float(s.get("fga")      or 0)
        ftm  = float(s.get("ftm")      or 0)
        fta  = float(s.get("fta")      or 0)
        oreb = float(s.get("oreb")     or 0)
        dreb = float(s.get("dreb")     or 0)
        ast  = float(s.get("ast")      or 0)
        stl  = float(s.get("stl")      or 0)
        blk  = float(s.get("blk")      or 0)
        tov  = float(s.get("turnover") or 0)
        pf   = float(s.get("pf")       or 0)

        uper = (1 / min_) * (
            pts
            + 0.4 * fgm
            - 0.7 * fga
            - 0.4 * (fta - ftm)
            + 0.7 * oreb
            + 0.3 * dreb
            + stl
            + 0.7 * ast
            + 0.7 * blk
            - 0.4 * pf
            - tov
        )
        # Factor de normalização empírico para media ≈ 15
        per = uper * 67
        return round(per, 1)
    except (TypeError, ZeroDivisionError):
        return None


# ── ADVANCED STATS (para PIE, net rating, TS%) ──────────────────────────────

def fetch_all_advanced(player_ids, headers):
    results = []
    cursor = None
    params = {"seasons[]": SEASON, "period": 0, "per_page": 100}
    for pid in player_ids:
        params.setdefault("player_ids[]", [])
        params["player_ids[]"].append(pid)

    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        data = bdl_get("/v2/stats/advanced", p, headers)
        items = data.get("data", [])
        results.extend(items)
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(DELAY)
        if not cursor:
            break
    return results


def weighted_mean(values_weights):
    total_w = sum(w for v, w in values_weights if v is not None and w)
    if not total_w:
        return None
    return sum(v * w for v, w in values_weights if v is not None and w) / total_w


def simple_mean(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def aggregate_advanced(records):
    """Agrega registros por jogo em médias da temporada com filtros de qualificação."""
    games = len(records)
    if games < MIN_GAMES:
        return None

    poss_vals = [r.get("possessions") or 0 for r in records]
    avg_poss  = sum(poss_vals) / len(poss_vals)
    if avg_poss < MIN_AVG_POSS:
        return None

    usg_vals = [r.get("usage_percentage") for r in records]
    avg_usg  = simple_mean(usg_vals) or 0
    if avg_usg < MIN_AVG_USG:
        return None

    pie_wp  = [(r.get("pie"),                             r.get("possessions") or 0) for r in records]
    ts_wp   = [(r.get("true_shooting_percentage"),        r.get("possessions") or 0) for r in records]
    usg_wp  = [(r.get("usage_percentage"),                r.get("possessions") or 0) for r in records]
    efg_wp  = [(r.get("effective_field_goal_percentage"), r.get("possessions") or 0) for r in records]
    net_vals = [r.get("net_rating")       for r in records]
    off_vals = [r.get("offensive_rating") for r in records]
    def_vals = [r.get("defensive_rating") for r in records]

    pie = weighted_mean(pie_wp)
    if pie is None:
        return None

    return {
        "games":      games,
        "avg_poss":   round(avg_poss, 1),
        "pie":        round(pie, 4),
        "ts_pct":     round(weighted_mean(ts_wp) or 0, 4),
        "net_rating": round(simple_mean(net_vals) or 0, 2),
        "off_rating": round(simple_mean(off_vals) or 0, 2),
        "def_rating": round(simple_mean(def_vals) or 0, 2),
        "usg_pct":    round(weighted_mean(usg_wp) or 0, 4),
        "efg_pct":    round(weighted_mean(efg_wp) or 0, 4),
    }


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()
    headers = {"Authorization": get_key(args.api_key)}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    index_file = OUTPUT_DIR / "salaries_index.json"
    if not index_file.exists():
        print("ERRO: salaries_index.json não encontrado. Rode generate_salaries.py primeiro.")
        sys.exit(1)

    # Carrega jogadores dos JSONs de salários
    index = json.loads(index_file.read_text())
    player_map = {}
    print("Carregando jogadores dos JSONs de salários...")
    for entry in index:
        abbr = entry["abbreviation"].lower()
        f = OUTPUT_DIR / f"salaries_{abbr}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        for p in data.get("players", []):
            pid = p.get("player_id")
            if pid and pid not in player_map:
                player_map[pid] = {
                    "name":        p["name"],
                    "position":    p.get("position", ""),
                    "team_abbr":   data["team"]["abbreviation"],
                    "team_id":     data["team"]["id"],
                    "cap_hit_raw": p.get("cap_hit_raw") or 0,
                    "cap_hit":     p.get("cap_hit", "—"),
                    "contract_years": p.get("contract_years"),
                    "end_year":    p.get("end_year"),
                }

    all_ids = list(player_map.keys())
    print(f"Total de jogadores: {len(all_ids)}")

    # 1. Busca season averages para PER
    print("\nBuscando médias de temporada (season averages)...")
    season_avgs = fetch_season_averages(all_ids, headers)
    print(f"  → {len(season_avgs)} jogadores com dados de temporada")

    # Calcula PER de todos e acha a média da liga para normalizar
    raw_pers = {}
    for pid, s in season_avgs.items():
        per = calc_per(s)
        if per is not None:
            raw_pers[pid] = per

    # Normaliza para média = 15
    if raw_pers:
        liga_media = sum(raw_pers.values()) / len(raw_pers)
        fator = LEAGUE_AVG_PER / liga_media
        print(f"  → PER médio bruto da liga: {liga_media:.2f} · fator de normalização: {fator:.3f}")
        per_norm = {pid: round(per * fator, 1) for pid, per in raw_pers.items()}
    else:
        per_norm = {}
        print("  → Sem dados de PER")

    # 2. Busca advanced stats para PIE, net rating, TS%
    print("\nBuscando advanced stats por jogo...")
    raw_by_player = {}
    total_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(all_ids), BATCH_SIZE):
        batch = all_ids[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Lote {batch_num}/{total_batches}...")
        records = fetch_all_advanced(batch, headers)
        for rec in records:
            pid = rec.get("player", {}).get("id")
            if pid:
                raw_by_player.setdefault(pid, []).append(rec)

    # 3. Agrega e monta resultado final
    output = []
    skipped = 0
    for pid, info in player_map.items():
        records = raw_by_player.get(pid, [])
        agg = aggregate_advanced(records)
        if not agg:
            skipped += 1
            continue

        per       = per_norm.get(pid)
        savg      = season_avgs.get(pid, {})
        pie_pct   = agg["pie"] * 100
        cap_m     = info["cap_hit_raw"] / 1e6

        # Custo-benefício por PER (preferido) ou PIE
        cost_per_per = round(cap_m / per, 2) if per and per > 0 else None
        cost_per_pie = round(cap_m / pie_pct, 3) if pie_pct > 0 else None

        output.append({
            "player_id":     pid,
            "name":          info["name"],
            "position":      info["position"],
            "team_abbr":     info["team_abbr"],
            "team_id":       info["team_id"],
            "cap_hit_raw":   info["cap_hit_raw"],
            "cap_hit":       info["cap_hit"],
            "contract_years": info.get("contract_years"),
            "end_year":      info.get("end_year"),
            # Box score médias
            "pts":  round(float(savg.get("pts")  or 0), 1),
            "reb":  round(float(savg.get("reb")  or 0), 1),
            "ast":  round(float(savg.get("ast")  or 0), 1),
            "min":  round(parse_min(savg.get("min")), 1),
            # Eficiência
            "per":          per,
            "cost_per_per": cost_per_per,  # $M por ponto de PER
            **agg,
            "pie_pct":      round(pie_pct, 2),
            "cost_per_pie": cost_per_pie,
        })

    # Ordena por PER desc (com fallback para PIE)
    output.sort(key=lambda x: x.get("per") or 0, reverse=True)

    out_file = OUTPUT_DIR / "player_advanced.json"
    out_file.write_text(json.dumps({
        "season":    SEASON,
        "min_games": MIN_GAMES,
        "min_poss":  MIN_AVG_POSS,
        "min_usg":   MIN_AVG_USG,
        "players":   output,
    }, ensure_ascii=False, indent=2))

    print(f"\n✅ Salvo: {out_file}")
    print(f"   {len(output)} jogadores qualificados")
    print(f"   {skipped} ignorados pelos filtros")

    # Preview do top 5
    print("\nTop 5 por PER:")
    for p in output[:5]:
        print(f"  {p['name']:25s} PER: {str(p.get('per') or '—'):5} | {p['cap_hit']:8} | {p['pts']}pts {p['reb']}reb {p['ast']}ast")


if __name__ == "__main__":
    main()
