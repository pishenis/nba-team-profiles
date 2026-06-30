"""
Script de exploração: API de Contratos da BDL para Free Agents.

Objetivo: puxar os contratos dos 30 times para a temporada que acabou de
terminar e entender, com dados reais, os valores possíveis de:
  - contract_status
  - free_agent_status
  - formato de contract_notes (player option / team option / ETO)

Roda local (Claude Code) porque precisa do .env com a API key da BDL.
Ajuste BDL_API_KEY abaixo se o nome da variável no seu .env for diferente.
"""

import os
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Ajuste o caminho absoluto conforme o restante do projeto
ENV_PATH = Path.home() / "nba-team-profiles" / ".env"
load_dotenv(ENV_PATH)

API_KEY = os.getenv("BDL_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "Não achei BDL_API_KEY no .env. Confira o nome exato da variável "
        f"em {ENV_PATH} e ajuste este script."
    )

BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}

# Temporada que acabou de terminar (ajuste se necessário)
SEASON_ATUAL = 2025  # representa a temporada 2025-26
ANO_FREE_AGENCY = 2026  # verão em que esses contratos expiram

TEAM_IDS = list(range(1, 31))  # BDL usa IDs sequenciais 1-30


def buscar_contratos_time(team_id: int, season: int) -> list:
    resp = requests.get(
        f"{BASE_URL}/contracts/teams",
        params={"team_id": team_id, "season": season},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def main():
    todos_contratos = []

    for team_id in TEAM_IDS:
        print(f"Buscando contratos do time {team_id}...")
        try:
            contratos = buscar_contratos_time(team_id, SEASON_ATUAL)
            todos_contratos.extend(contratos)
        except requests.HTTPError as e:
            print(f"  Erro no time {team_id}: {e}")
        time.sleep(0.1)  # GOAT tier é 600 req/min, não tem pressa

    print(f"\nTotal de contratos coletados: {len(todos_contratos)}")

    # Salva o bruto pra inspeção manual
    out_path = Path("contratos_raw.json")
    out_path.write_text(
        json.dumps(todos_contratos, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Salvo em {out_path.resolve()}")

    # --- Exploração dos valores únicos ---
    statuses = sorted({c.get("contract_status") for c in todos_contratos})
    fa_statuses = sorted(
        {c.get("free_agent_status") for c in todos_contratos if c.get("free_agent_status")}
    )
    fa_years = sorted(
        {c.get("free_agent_year") for c in todos_contratos if c.get("free_agent_year")}
    )

    print("\n=== contract_status únicos ===")
    for s in statuses:
        print(f"  - {s}")

    print("\n=== free_agent_status únicos ===")
    for s in fa_statuses:
        print(f"  - {s}")

    print("\n=== free_agent_year únicos ===")
    for s in fa_years:
        print(f"  - {s}")

    # --- Candidatos a free agent deste verão ---
    candidatos = [
        c for c in todos_contratos if c.get("free_agent_year") == ANO_FREE_AGENCY
    ]
    print(f"\n=== Candidatos com free_agent_year == {ANO_FREE_AGENCY}: {len(candidatos)} ===")
    for c in candidatos[:10]:
        nome = c.get("player", {}).get("first_name", "") + " " + c.get("player", {}).get("last_name", "")
        print(
            f"  {nome:25s} | status={c.get('contract_status'):20s} | "
            f"fa_status={c.get('free_agent_status')} | notes={c.get('contract_notes')}"
        )

    # --- Contratos com notas de opção (pra entender o formato de texto) ---
    com_opcao = [
        c for c in todos_contratos
        if c.get("contract_notes") and any("Option" in n for n in c["contract_notes"])
    ]
    print(f"\n=== Contratos com 'Option' em contract_notes: {len(com_opcao)} ===")
    for c in com_opcao[:10]:
        nome = c.get("player", {}).get("first_name", "") + " " + c.get("player", {}).get("last_name", "")
        print(f"  {nome:25s} | notes={c.get('contract_notes')}")


if __name__ == "__main__":
    main()
