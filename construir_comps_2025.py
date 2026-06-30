"""
Etapa B (parte 1): identifica, dentro do histórico de contratos já coletado,
quem foi free agent no verão de 2025 e o contrato novo que assinou — depois
busca as stats da temporada 2024-25 (a que gerou aquele contrato).

Lógica: para cada jogador, ordena as entradas por start_year. Se existe uma
entrada com start_year == 2025 (o contrato novo) E a entrada imediatamente
anterior no histórico tem free_agent_year == 2025, então isso é uma
assinatura de free agency real de 2025 — não rookie, não extensão antecipada.
"""

import os
import json
import time
from pathlib import Path
from collections import defaultdict

import requests
from dotenv import load_dotenv

ENV_PATH = Path.home() / "nba-team-profiles" / ".env"
load_dotenv(ENV_PATH)

API_KEY = os.getenv("BDL_API_KEY")
if not API_KEY:
    raise RuntimeError(f"BDL_API_KEY não encontrada em {ENV_PATH}")

BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}

SEASON_ANTERIOR = 2024  # temporada 2024-25, que gerou os contratos de 2025
LOTE = 25


def identificar_assinaturas_2025():
    raw_path = Path("contratos_agregados_raw.json")
    if not raw_path.exists():
        raise RuntimeError(
            "contratos_agregados_raw.json não encontrado. "
            "Rode coletar_agregados_fa.py primeiro (já deve ter rodado antes)."
        )

    todos = json.loads(raw_path.read_text(encoding="utf-8"))

    por_jogador = defaultdict(list)
    for c in todos:
        if c.get("start_year") is not None:
            por_jogador[c["player_id"]].append(c)

    assinaturas = []
    for pid, entradas in por_jogador.items():
        entradas.sort(key=lambda e: e["start_year"])

        for i, entrada in enumerate(entradas):
            if entrada.get("start_year") != 2025:
                continue
            if i == 0:
                continue  # não tem entrada anterior, não dá pra confirmar FA
            anterior = entradas[i - 1]
            if anterior.get("free_agent_year") == 2025:
                assinaturas.append(
                    {
                        "player_id": pid,
                        "player": entrada.get("player"),
                        "novo_contrato": {
                            "team": entrada.get("team"),
                            "contract_type": entrada.get("contract_type"),
                            "contract_years": entrada.get("contract_years"),
                            "total_value": entrada.get("total_value"),
                            "average_salary": entrada.get("average_salary"),
                            "start_year": entrada.get("start_year"),
                            "end_year": entrada.get("end_year"),
                        },
                        "free_agent_status_2025": anterior.get("free_agent_status"),
                    }
                )

    return assinaturas


def buscar_season_averages(player_ids: list, season: int) -> list:
    params = [("season", season), ("season_type", "regular"), ("type", "base")]
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
    assinaturas = identificar_assinaturas_2025()
    print(f"Assinaturas de free agency 2025 identificadas: {len(assinaturas)}")

    player_ids = [a["player_id"] for a in assinaturas]
    stats_por_player = {}
    for i in range(0, len(player_ids), LOTE):
        lote_ids = player_ids[i : i + LOTE]
        try:
            resultados = buscar_season_averages(lote_ids, SEASON_ANTERIOR)
            for r in resultados:
                stats_por_player[r["player"]["id"]] = r.get("stats", {})
        except requests.HTTPError as e:
            print(f"  Erro no lote {i}-{i+LOTE}: {e}")
        time.sleep(0.2)

    for a in assinaturas:
        a["stats_2024_25"] = stats_por_player.get(a["player_id"])

    sem_stats = [a for a in assinaturas if a["stats_2024_25"] is None]
    if sem_stats:
        nomes = [
            f"{a['player']['first_name']} {a['player']['last_name']}" for a in sem_stats
        ]
        print(f"Sem stats em 2024-25 (provavelmente não jogaram nos EUA/lesão): {nomes}")

    out_path = Path("data/free-agents/comps_free_agency_2025.json")
    out_path.write_text(
        json.dumps(assinaturas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSalvo em {out_path.resolve()}")

    print("\n=== Amostra (10 primeiras) ===")
    for a in assinaturas[:10]:
        p = a["player"]
        nome = f"{p['first_name']} {p['last_name']}"
        nc = a["novo_contrato"]
        s = a.get("stats_2024_25") or {}
        time_novo = (nc.get("team") or {}).get("abbreviation") or "?"
        print(
            f"  {nome:25s} | {a['free_agent_status_2025']:4s} -> {time_novo:4s} | "
            f"${nc.get('average_salary') or 0:,.0f} | "
            f"PTS {s.get('pts','?')} REB {s.get('reb','?')} AST {s.get('ast','?')}"
        )


if __name__ == "__main__":
    main()
