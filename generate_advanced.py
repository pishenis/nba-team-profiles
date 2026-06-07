"""
Bola Presa Stats — Gerador de Médias Avançadas por Jogador
Calcula PIE médio ponderado, TS%, net rating e usage da temporada
a partir dos advanced stats por jogo da Ball Don't Lie.

Uso:
    python3 generate_advanced.py --api-key SUA_KEY
    python3 generate_advanced.py  # usa BDL_API_KEY do ambiente
"""

import os, sys, json, time, argparse, requests
from pathlib import Path

BASE_URL   = "https://api.balldontlie.io"
SEASON     = 2025
OUTPUT_DIR = Path("data/salaries")
DELAY      = 0.15
BATCH_SIZE = 10

# Filtros de qualificação
MIN_GAMES        = 25    # mínimo de jogos na temporada
MIN_AVG_POSS     = 35.0  # possessões médias por jogo (~20 min de quadra)
MIN_AVG_USG      = 0.10  # usage mínimo de 10% (exclui jogadores só de hustle)


def get_key(args_key):
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


def aggregate_player(records):
    games = len(records)
    if games < MIN_GAMES:
        return None

    # Média de possessões por jogo — proxy de minutos
    poss_vals = [r.get("possessions") or 0 for r in records]
    avg_poss  = sum(poss_vals) / len(poss_vals)
    if avg_poss < MIN_AVG_POSS:
        return None

    # Média de usage — exclui jogadores de papel mínimo
    usg_vals = [r.get("usage_percentage") for r in records]
    avg_usg  = simple_mean(usg_vals) or 0
    if avg_usg < MIN_AVG_USG:
        return None

    pie_wp  = [(r.get("pie"),                          r.get("possessions") or 0) for r in records]
    ts_wp   = [(r.get("true_shooting_percentage"),     r.get("possessions") or 0) for r in records]
    usg_wp  = [(r.get("usage_percentage"),             r.get("possessions") or 0) for r in records]
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
                }

    all_ids = list(player_map.keys())
    print(f"Total de jogadores: {len(all_ids)}")

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

    output = []
    skipped = 0
    for pid, info in player_map.items():
        records = raw_by_player.get(pid, [])
        agg = aggregate_player(records)
        if not agg:
            skipped += 1
            continue

        pie_pct      = agg["pie"] * 100
        cap_m        = info["cap_hit_raw"] / 1e6
        cost_per_pie = round(cap_m / pie_pct, 3) if pie_pct > 0 else None

        output.append({
            "player_id":    pid,
            "name":         info["name"],
            "position":     info["position"],
            "team_abbr":    info["team_abbr"],
            "team_id":      info["team_id"],
            "cap_hit_raw":  info["cap_hit_raw"],
            "cap_hit":      info["cap_hit"],
            **agg,
            "pie_pct":      round(pie_pct, 2),
            "cost_per_pie": cost_per_pie,
        })

    output.sort(key=lambda x: x["pie"], reverse=True)

    out_file = OUTPUT_DIR / "player_advanced.json"
    out_file.write_text(json.dumps({
        "season":     SEASON,
        "min_games":  MIN_GAMES,
        "min_poss":   MIN_AVG_POSS,
        "min_usg":    MIN_AVG_USG,
        "players":    output,
    }, ensure_ascii=False, indent=2))

    print(f"\n✅ Salvo: {out_file}")
    print(f"   {len(output)} jogadores qualificados")
    print(f"   {skipped} ignorados (menos de {MIN_GAMES} jogos, <{MIN_AVG_POSS} poss/jogo ou <{MIN_AVG_USG*100:.0f}% usage)")


if __name__ == "__main__":
    main()
