"""
Etapa A: enriquece free_agents_2026.json com as stats da temporada 2025-26
(pts, reb, ast, min, fg%, 3p%, ft%) de cada free agent, puxando do endpoint
de season averages da BDL.
"""

import os
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

API_KEY = os.getenv("BDL_API_KEY")
if not API_KEY:
    raise RuntimeError(f"BDL_API_KEY não encontrada em {ENV_PATH}")

BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}

SEASON = 2025  # temporada 2025-26, que acabou de terminar
LOTE = 25  # quantos player_ids por chamada, pra não estourar URL


def buscar_season_averages(player_ids: list) -> list:
    params = [("season", SEASON), ("season_type", "regular"), ("type", "base")]
    for pid in player_ids:
        params.append(("player_ids[]", pid))

    resp = requests.get(
        f"{BASE_URL}/season_averages/general",
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def main():
    fa_path = Path("free_agents_2026.json")
    if not fa_path.exists():
        raise RuntimeError(
            "free_agents_2026.json não encontrado. Rode filtrar_free_agents_reais.py primeiro."
        )

    free_agents = json.loads(fa_path.read_text(encoding="utf-8"))
    print(f"Free agents carregados: {len(free_agents)}")

    player_ids = [fa["player_id"] for fa in free_agents]

    stats_por_player = {}
    for i in range(0, len(player_ids), LOTE):
        lote_ids = player_ids[i : i + LOTE]
        try:
            resultados = buscar_season_averages(lote_ids)
            for r in resultados:
                pid = r["player"]["id"]
                stats_por_player[pid] = r.get("stats", {})
        except requests.HTTPError as e:
            print(f"  Erro no lote {i}-{i+LOTE}: {e}")
        time.sleep(0.2)

    print(f"Jogadores com stats encontradas: {len(stats_por_player)}")
    sem_stats = [fa for fa in free_agents if fa["player_id"] not in stats_por_player]
    if sem_stats:
        nomes = [
            f"{fa['player']['first_name']} {fa['player']['last_name']}"
            for fa in sem_stats
        ]
        print(f"\nSem stats em {SEASON} (provavelmente não jogou ou poucos jogos): {nomes}")

    # Merge
    for fa in free_agents:
        fa["stats_2025_26"] = stats_por_player.get(fa["player_id"])

    out_path = Path("free_agents_2026_enriched.json")
    out_path.write_text(
        json.dumps(free_agents, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSalvo em {out_path.resolve()}")

    # Amostra pra conferência visual
    print("\n=== Amostra (5 primeiros, já ordenados por salário) ===")
    for fa in free_agents[:5]:
        p = fa["player"]
        nome = f"{p['first_name']} {p['last_name']}"
        s = fa.get("stats_2025_26") or {}
        print(
            f"  {nome:25s} | PTS {s.get('pts', '?')} | REB {s.get('reb', '?')} | "
            f"AST {s.get('ast', '?')} | MIN {s.get('min', '?')}"
        )


if __name__ == "__main__":
    main()
