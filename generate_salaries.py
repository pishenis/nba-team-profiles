"""
Bola Presa Stats — Gerador de Salários por Time
Usa a API Ball Don't Lie (tier GOAT) para buscar contratos e gerar JSONs estáticos.

Endpoints utilizados:
  GET /v1/contracts/team    → salários por temporada por time
  GET /v1/contracts/players → detalhes do contrato agregado (tipo, signed_using, etc.)

Uso:
    python generate_salaries.py --api-key SUA_KEY
    python generate_salaries.py  # usa variável de ambiente BDL_API_KEY
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

BASE_URL = "https://api.balldontlie.io/v1"
SEASON = 2025          # temporada atual (2025-26)
OUTPUT_DIR = Path("data/salaries")
REQUEST_DELAY = 0.12   # ~500 req/min seguro para GOAT (600 req/min)

# IDs dos 30 times na Ball Don't Lie
TEAM_IDS = list(range(1, 31))


def get_api_key(args_key: str) -> str:
    key = args_key or os.environ.get("BDL_API_KEY", "")
    if not key:
        print("ERRO: Informe a API key via --api-key ou variável BDL_API_KEY")
        sys.exit(1)
    return key


def bdl_get(endpoint: str, params: dict, headers: dict) -> dict:
    """Faz GET com retry simples em caso de rate limit."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(3):
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  Rate limit — aguardando {wait}s...")
            time.sleep(wait)
        else:
            print(f"  ERRO {resp.status_code}: {resp.text[:200]}")
            return {}
    return {}


def fetch_all_pages(endpoint: str, params: dict, headers: dict) -> list:
    """Busca todas as páginas de um endpoint paginado por cursor."""
    results = []
    cursor = None
    while True:
        p = {**params, "per_page": 100}
        if cursor:
            p["cursor"] = cursor
        data = bdl_get(endpoint, p, headers)
        items = data.get("data", [])
        results.extend(items)
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(REQUEST_DELAY)
        if not cursor:
            break
    return results


def fetch_team_contracts(team_id: int, headers: dict) -> list:
    """Busca contratos por temporada de um time."""
    return fetch_all_pages(
        "/contracts/teams",
        {"team_id": team_id, "seasons[]": SEASON},
        headers,
    )


def fetch_player_contract_aggregates(player_ids: list, headers: dict) -> dict:
    """
    Busca aggregates (tipo de contrato, signed_using, etc.) para uma lista de jogadores.
    Retorna dict: player_id → aggregate mais recente com status CURRENT.
    O endpoint /contracts/players/aggregate aceita um player_id por vez.
    """
    result = {}
    for pid in player_ids:
        data = bdl_get("/contracts/players/aggregate", {"player_id": pid}, headers)
        for item in data.get("data", []):
            status = (item.get("contract_status") or "").upper()
            # Pega o CURRENT; se não tiver, guarda o primeiro como fallback
            if pid not in result or status == "CURRENT":
                result[pid] = item
        time.sleep(REQUEST_DELAY)
    return result


def format_salary(value) -> str:
    """Formata valor inteiro em dólares → '$59.6M'."""
    if value is None:
        return "—"
    v = int(value)
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,}"


def translate_contract_type(ct: str) -> str:
    mapping = {
        "Rookie": "Rookies",
        "Free Agent": "Agente Livre",
        "Extension": "Extensão",
        "Two-Way": "Two-Way",
        "10-Day": "10 Dias",
        "Exhibit 10": "Exhibit 10",
        "Minimum": "Mínimo",
        "G League": "G League",
    }
    return mapping.get(ct, ct or "—")


def translate_signed_using(su: str) -> str:
    mapping = {
        "Bird Rights": "Bird Rights",
        "Cap Space": "Espaço no Cap",
        "Non-Bird Rights": "Non-Bird Rights",
        "Early Bird Rights": "Early Bird Rights",
        "Mid-Level Exception": "Exceção MLE",
        "Bi-Annual Exception": "Exceção Bi-anual",
        "Rookie Scale": "Contrato de Rookie",
        "Traded": "Troca",
        "Minimum Salary Exception": "Salário Mínimo",
        "Two-Way Contract": "Two-Way",
    }
    for k, v in mapping.items():
        if su and k.lower() in su.lower():
            return v
    return su or "—"


def translate_fa_status(status: str) -> str:
    if not status:
        return "—"
    s = status.upper()
    if s == "UFA":
        return "UFA (Irrestrito)"
    if s == "RFA":
        return "RFA (Restrito)"
    return status


def build_team_payload(team_id: int, headers: dict):
    """Monta o payload completo de um time."""
    print(f"  Buscando contratos do time {team_id}...")
    contracts = fetch_team_contracts(team_id, headers)
    if not contracts:
        print(f"  Sem dados para team_id={team_id}")
        return None

    # Dados do time a partir do primeiro contrato
    sample = contracts[0]
    team_info = sample.get("team", {})

    # Busca aggregates para todos os jogadores deste time
    player_ids = list({c["player_id"] for c in contracts if c.get("player_id")})
    print(f"  Buscando aggregates de {len(player_ids)} jogadores...")
    aggregates = fetch_player_contract_aggregates(player_ids, headers)

    players = []
    total_cap = 0

    for c in contracts:
        pid = c.get("player_id")
        player = c.get("player", {})
        cap_hit = c.get("cap_hit")
        base_salary = c.get("base_salary")
        total_cash = c.get("total_cash")
        rank = c.get("rank")

        if cap_hit:
            total_cap += cap_hit

        agg = aggregates.get(pid, {})

        # Extrai notas de opções do campo contract_notes
        notes = agg.get("contract_notes") or {}
        options_text = []
        if isinstance(notes, dict):
            for k, v in notes.items():
                if v:
                    options_text.append(f"{k}: {v}")

        players.append({
            "player_id": pid,
            "name": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
            "position": player.get("position", ""),
            "jersey_number": player.get("jersey_number", ""),
            "cap_hit_raw": cap_hit,
            "cap_hit": format_salary(cap_hit),
            "base_salary": format_salary(base_salary),
            "total_cash": format_salary(total_cash),
            "salary_rank": rank,
            # Do aggregate
            "contract_type": translate_contract_type(agg.get("contract_type", "")),
            "contract_type_raw": agg.get("contract_type", ""),
            "start_year": agg.get("start_year"),
            "end_year": agg.get("end_year"),
            "contract_years": agg.get("contract_years"),
            "total_value": format_salary(agg.get("total_value")),
            "average_salary": format_salary(agg.get("average_salary")),
            "guaranteed_at_signing": format_salary(agg.get("guaranteed_at_signing")),
            "total_guaranteed": format_salary(agg.get("total_guaranteed")),
            "signed_using": translate_signed_using(agg.get("signed_using", "")),
            "signed_using_raw": agg.get("signed_using", ""),
            "free_agent_year": agg.get("free_agent_year"),
            "free_agent_status": translate_fa_status(agg.get("free_agent_status", "")),
            "contract_status": agg.get("contract_status", ""),
            "contract_notes": options_text,
        })

    # Ordena por cap_hit decrescente (None vai para o fim)
    players.sort(key=lambda p: p["cap_hit_raw"] or 0, reverse=True)

    return {
        "team": {
            "id": team_info.get("id", team_id),
            "full_name": team_info.get("full_name", ""),
            "abbreviation": team_info.get("abbreviation", ""),
            "city": team_info.get("city", ""),
            "name": team_info.get("name", ""),
            "conference": team_info.get("conference", ""),
            "division": team_info.get("division", ""),
        },
        "season": SEASON,
        "total_cap_raw": total_cap,
        "total_cap": format_salary(total_cap),
        "player_count": len(players),
        "players": players,
    }


def fetch_nba_player_ids() -> dict:
    """
    Busca o mapa nome → nba_player_id direto da API pública da NBA.
    Funciona localmente; o GitHub Actions é bloqueado mas o JSON gerado
    fica salvo em data/salaries/nba_player_ids.json para uso do HTML.
    """
    import unicodedata

    def normalize(s):
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")

    url = "https://stats.nba.com/stats/commonallplayers"
    params = {
        "LeagueID": "00",
        "Season": "2025-26",
        "IsOnlyCurrentSeason": "1",
    }
    headers_nba = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.nba.com/",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, params=params, headers=headers_nba, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        headers_row = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]
        id_idx   = headers_row.index("PERSON_ID")
        name_idx = headers_row.index("DISPLAY_FIRST_LAST")
        mapa = {}
        for row in rows:
            nba_id = str(row[id_idx])
            name   = str(row[name_idx]).strip()
            mapa[name] = nba_id
            norm = normalize(name)
            if norm != name:
                mapa[norm] = nba_id
        print(f"  → {len(mapa)} entradas de jogadores da NBA")
        return mapa
    except Exception as e:
        print(f"  Aviso: não foi possível buscar IDs da NBA ({e})")
        return {}


def main():
    parser = argparse.ArgumentParser(description="Gera JSONs de salários por time")
    parser.add_argument("--api-key", default="", help="Ball Don't Lie API key")
    parser.add_argument("--team-id", type=int, default=0, help="Gerar só para um time específico")
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    headers = {"Authorization": api_key}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Gera mapa nome → NBA player_id para fotos
    print("\nBuscando IDs de jogadores da NBA...")
    nba_ids = fetch_nba_player_ids()
    if nba_ids:
        ids_file = OUTPUT_DIR / "nba_player_ids.json"
        ids_file.write_text(json.dumps(nba_ids, ensure_ascii=False, indent=2))
        print(f"  → Salvo: {ids_file}")

    team_ids = [args.team_id] if args.team_id else TEAM_IDS

    index = []  # para salaries_index.json

    for team_id in team_ids:
        print(f"\n[Time {team_id}/{len(team_ids) if not args.team_id else 1}]")
        payload = build_team_payload(team_id, headers)
        if not payload:
            continue

        abbr = payload["team"]["abbreviation"].lower()
        out_file = OUTPUT_DIR / f"salaries_{abbr}.json"
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"  → Salvo: {out_file}  ({payload['player_count']} jogadores, cap: {payload['total_cap']})")

        index.append({
            "team_id": payload["team"]["id"],
            "full_name": payload["team"]["full_name"],
            "abbreviation": payload["team"]["abbreviation"],
            "conference": payload["team"]["conference"],
            "total_cap": payload["total_cap"],
            "total_cap_raw": payload["total_cap_raw"],
            "player_count": payload["player_count"],
            "file": f"data/salaries/salaries_{abbr}.json",
        })

    # Salva índice global
    index.sort(key=lambda t: t["total_cap_raw"] or 0, reverse=True)
    index_file = OUTPUT_DIR / "salaries_index.json"
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"\n✅ Índice salvo: {index_file}")
    print("✅ Pronto!")


if __name__ == "__main__":
    main()
