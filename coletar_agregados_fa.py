"""
Passo 2 da exploração: usa os player_ids coletados em contratos_raw.json
(via /v1/contracts/teams) e busca o contrato AGREGADO de cada um, que é
onde realmente moram os campos de free agency.

Endpoint certo: GET /v1/contracts/players/aggregate?player_id=X
"""

import os
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path.home() / "nba-team-profiles" / ".env"
load_dotenv(ENV_PATH)

API_KEY = os.getenv("BDL_API_KEY")
if not API_KEY:
    raise RuntimeError(f"BDL_API_KEY não encontrada em {ENV_PATH}")

BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}

ANO_FREE_AGENCY = 2026  # verão atual


def buscar_aggregate(player_id: int) -> list:
    resp = requests.get(
        f"{BASE_URL}/contracts/players/aggregate",
        params={"player_id": player_id},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def main():
    contratos_path = Path("contratos_raw.json")
    if not contratos_path.exists():
        raise RuntimeError(
            "contratos_raw.json não encontrado. Rode explorar_contratos_fa.py primeiro."
        )

    contratos_times = json.loads(contratos_path.read_text(encoding="utf-8"))
    player_ids = sorted({c["player_id"] for c in contratos_times})
    print(f"Jogadores únicos encontrados: {len(player_ids)}")

    todos_agregados = []
    for i, pid in enumerate(player_ids, 1):
        try:
            agregados = buscar_aggregate(pid)
            todos_agregados.extend(agregados)
        except requests.HTTPError as e:
            print(f"  Erro no player_id {pid}: {e}")
        if i % 50 == 0:
            print(f"  {i}/{len(player_ids)} jogadores processados...")
        time.sleep(0.12)  # ritmo seguro, ~500/min, abaixo do limite de 600/min

    print(f"\nTotal de entradas de contrato agregado: {len(todos_agregados)}")

    out_path = Path("contratos_agregados_raw.json")
    out_path.write_text(
        json.dumps(todos_agregados, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Salvo em {out_path.resolve()}")

    # --- Exploração ---
    statuses = sorted({c.get("contract_status") for c in todos_agregados if c.get("contract_status")})
    fa_statuses = sorted({c.get("free_agent_status") for c in todos_agregados if c.get("free_agent_status")})
    fa_years = sorted({c.get("free_agent_year") for c in todos_agregados if c.get("free_agent_year")})

    print("\n=== contract_status únicos ===")
    for s in statuses:
        print(f"  - {s}")

    print("\n=== free_agent_status únicos ===")
    for s in fa_statuses:
        print(f"  - {s}")

    print("\n=== free_agent_year únicos ===")
    for s in fa_years:
        print(f"  - {s}")

    # --- Candidatos a FA deste verão ---
    candidatos = [c for c in todos_agregados if c.get("free_agent_year") == ANO_FREE_AGENCY]
    print(f"\n=== Candidatos com free_agent_year == {ANO_FREE_AGENCY}: {len(candidatos)} ===")
    for c in candidatos[:15]:
        p = c.get("player", {})
        nome = f"{p.get('first_name','')} {p.get('last_name','')}"
        print(
            f"  {nome:25s} | status={str(c.get('contract_status')):20s} | "
            f"fa_status={c.get('free_agent_status')} | notes={c.get('contract_notes')}"
        )

    # --- Quem tem opção (player/team) ---
    com_opcao = [
        c for c in todos_agregados
        if c.get("contract_notes") and any("Option" in n for n in c["contract_notes"])
    ]
    print(f"\n=== Contratos com 'Option' em contract_notes: {len(com_opcao)} ===")
    for c in com_opcao[:15]:
        p = c.get("player", {})
        nome = f"{p.get('first_name','')} {p.get('last_name','')}"
        print(f"  {nome:25s} | notes={c.get('contract_notes')}")


if __name__ == "__main__":
    main()
