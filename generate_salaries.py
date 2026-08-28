"""
Bola Presa Stats — Gerador de Salários por Time
Usa a API Ball Don't Lie (tier GOAT) para buscar contratos e gerar JSONs estáticos.

Endpoints utilizados:
  GET /v1/contracts/teams    → salários por temporada por time
  GET /v1/contracts/players/aggregate → detalhes do contrato agregado

Overrides manuais de troca:
  Lê data/salaries/trade_overrides.json (gerado via trade_overrides.html)
  e força o jogador para o novo time quando a BDL ainda não atualizou.

Uso:
    python3 generate_salaries.py --api-key SUA_KEY
    python3 generate_salaries.py  # usa variável de ambiente BDL_API_KEY
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from _env_loader import require_env

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

BASE_URL = "https://api.balldontlie.io/v1"
SEASON = 2026
OUTPUT_DIR = Path("data/salaries")
REQUEST_DELAY = 0.12

TEAM_IDS = list(range(1, 31))

# BDL team_id → abreviação (para aplicar overrides por abbr)
BDL_TEAM_ABBR = {
    1: "ATL", 2: "BOS", 3: "BKN", 4: "CHA", 5: "CHI",
    6: "CLE", 7: "DAL", 8: "DEN", 9: "DET", 10: "GSW",
    11: "HOU", 12: "IND", 13: "LAC", 14: "LAL", 15: "MEM",
    16: "MIA", 17: "MIL", 18: "MIN", 19: "NOP", 20: "NYK",
    21: "OKC", 22: "ORL", 23: "PHI", 24: "PHX", 25: "POR",
    26: "SAC", 27: "SAS", 28: "TOR", 29: "UTA", 30: "WAS",
}
ABBR_TO_BDL_ID = {v: k for k, v in BDL_TEAM_ABBR.items()}


def get_api_key(args_key: str) -> str:
    if args_key:
        return args_key
    env = require_env("BDL_API_KEY")
    return env["BDL_API_KEY"]


def bdl_get(endpoint: str, params: dict, headers: dict) -> dict:
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
    return fetch_all_pages(
        "/contracts/teams",
        {"team_id": team_id, "seasons[]": SEASON},
        headers,
    )


def fetch_player_contract_aggregates(player_ids: list, headers: dict) -> dict:
    result = {}
    for pid in player_ids:
        data = bdl_get("/contracts/players/aggregate", {"player_id": pid}, headers)
        for item in data.get("data", []):
            status = (item.get("contract_status") or "").upper()
            if pid not in result or status == "CURRENT":
                result[pid] = item
        time.sleep(REQUEST_DELAY)
    return result


def format_salary(value) -> str:
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
        "Rookie": "Rookies", "Free Agent": "Agente Livre", "Extension": "Extensão",
        "Two-Way": "Two-Way", "10-Day": "10 Dias", "Exhibit 10": "Exhibit 10",
        "Minimum": "Mínimo", "G League": "G League",
    }
    return mapping.get(ct, ct or "—")


def translate_signed_using(su: str) -> str:
    mapping = {
        "Bird Rights": "Bird Rights", "Cap Space": "Espaço no Cap",
        "Non-Bird Rights": "Non-Bird Rights", "Early Bird Rights": "Early Bird Rights",
        "Mid-Level Exception": "Exceção MLE", "Bi-Annual Exception": "Exceção Bi-anual",
        "Rookie Scale": "Contrato de Rookie", "Traded": "Troca",
        "Minimum Salary Exception": "Salário Mínimo", "Two-Way Contract": "Two-Way",
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


def load_trade_overrides() -> dict:
    """
    Lê data/salaries/trade_overrides.json gerado pela interface trade_overrides.html.
    Retorna dict: player_id → {new_team_abbr, player_name, ...}
    """
    f = OUTPUT_DIR / "trade_overrides.json"
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text())
        overrides = {}
        for ov in data.get("overrides", []):
            pid = ov.get("player_id")
            if pid:
                overrides[pid] = ov
        if overrides:
            print(f"\n📋 {len(overrides)} override(s) de troca carregado(s) de trade_overrides.json")
            for pid, ov in overrides.items():
                print(f"   {ov['player_name']}: {ov.get('old_team_abbr','?')} → {ov['new_team_abbr']}")
        return overrides
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Aviso: erro ao ler trade_overrides.json ({e}) — ignorando")
        return {}


def build_team_payload(team_id: int, headers: dict, overrides: dict, all_team_contracts: dict):
    """Monta o payload completo de um time, aplicando overrides de troca."""
    print(f"  Buscando contratos do time {team_id}...")
    contracts = fetch_team_contracts(team_id, headers)

    # Remove jogadores que têm override SAINDO deste time
    contracts = [
        c for c in contracts
        if not (c.get("player_id") in overrides and overrides[c["player_id"]]["new_team_abbr"] != BDL_TEAM_ABBR.get(team_id))
    ]

    # Adiciona jogadores que têm override ENTRANDO neste time
    # (o contrato original deles está armazenado em all_team_contracts por player_id)
    target_abbr = BDL_TEAM_ABBR.get(team_id)
    for pid, ov in overrides.items():
        if ov["new_team_abbr"] == target_abbr:
            original_contract = all_team_contracts.get(pid)
            if original_contract:
                contracts.append(original_contract)

    if not contracts:
        print(f"  Sem dados para team_id={team_id}")
        return None

    # Deduplica por player_id: se o BDL retornar contrato expirado + novo pro mesmo
    # jogador (comum no início da temporada), fica só com o CURRENT; se não houver
    # CURRENT, fica com o mais recente (maior cap_hit como desempate).
    by_pid: dict = {}
    for c in contracts:
        pid = c.get("player_id")
        if not pid:
            continue
        existing = by_pid.get(pid)
        if existing is None:
            by_pid[pid] = c
        elif (c.get("contract_status") or "").upper() == "CURRENT":
            by_pid[pid] = c
        elif (existing.get("contract_status") or "").upper() != "CURRENT":
            if (c.get("cap_hit") or 0) > (existing.get("cap_hit") or 0):
                by_pid[pid] = c
    contracts = list(by_pid.values())

    # Segundo dedup: por nome completo — o BDL às vezes cria dois player_id distintos
    # para o mesmo jogador (ex: Luka Doncic: 132 e 1093968488). Mesma lógica de desempate.
    def _player_name(c):
        p = c.get("player", {})
        return (p.get("first_name", "") + " " + p.get("last_name", "")).strip().lower()

    by_name: dict = {}
    for c in contracts:
        name = _player_name(c)
        if not name:
            continue
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = c
        elif (c.get("contract_status") or "").upper() == "CURRENT":
            by_name[name] = c
        elif (existing.get("contract_status") or "").upper() != "CURRENT":
            if (c.get("cap_hit") or 0) > (existing.get("cap_hit") or 0):
                by_name[name] = c
    contracts = list(by_name.values())

    # Remove contratos expirados — são jogadores que saíram do time; o BDL ainda retorna
    # o contrato antigo deles quando consultamos por time, mas não faz sentido exibi-los
    # na página atual (ex: LeBron aparecia no LAL depois de assinar com o PHI).
    contracts = [c for c in contracts if (c.get("contract_status") or "").upper() != "EXPIRED"]

    if not contracts:
        print(f"  Sem contratos ativos para team_id={team_id}")
        return None

    # Dados do time — usa o nome oficial do BDL_TEAM_ABBR como fallback se vier de override
    sample = contracts[0]
    team_info = sample.get("team", {})

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

        # Segundo filtro: o endpoint de aggregates pode confirmar "expired" mesmo quando
        # o endpoint de times não sinalizou — jogador sem contrato ativo neste time.
        if (agg.get("contract_status") or "").upper() == "EXPIRED":
            if cap_hit:
                total_cap -= cap_hit
            continue

        notes = agg.get("contract_notes") or {}
        options_text = []
        if isinstance(notes, dict):
            for k, v in notes.items():
                if v:
                    options_text.append(f"{k}: {v}")

        is_overridden = pid in overrides and overrides[pid]["new_team_abbr"] == target_abbr

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
            "traded_via_override": is_overridden,
        })

    players.sort(key=lambda p: p["cap_hit_raw"] or 0, reverse=True)

    return {
        "team": {
            "id": team_info.get("id", team_id),
            "full_name": team_info.get("full_name", ""),
            "abbreviation": team_info.get("abbreviation", BDL_TEAM_ABBR.get(team_id, "")),
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


def main():
    parser = argparse.ArgumentParser(description="Gera JSONs de salários por time")
    parser.add_argument("--api-key", default="", help="Ball Don't Lie API key")
    parser.add_argument("--team-id", type=int, default=0, help="Gerar só para um time específico")
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    headers = {"Authorization": api_key}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    overrides = load_trade_overrides()

    team_ids = [args.team_id] if args.team_id else TEAM_IDS

    # Pré-busca: para aplicar overrides corretamente, precisamos do contrato
    # original de CADA jogador com override, vindo do time ONDE ELE ESTÁ HOJE na BDL.
    # Buscamos isso uma vez no início, escaneando todos os 30 times.
    all_team_contracts = {}
    if overrides:
        print("\nPré-carregando contratos originais para aplicar overrides...")
        for team_id in TEAM_IDS:
            contracts = fetch_team_contracts(team_id, headers)
            for c in contracts:
                pid = c.get("player_id")
                if pid in overrides:
                    all_team_contracts[pid] = c
        print(f"  → {len(all_team_contracts)}/{len(overrides)} contratos originais localizados")

    index = []

    for team_id in team_ids:
        print(f"\n[Time {team_id}/{len(team_ids) if not args.team_id else 1}]")
        payload = build_team_payload(team_id, headers, overrides, all_team_contracts)
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

    index.sort(key=lambda t: t["total_cap_raw"] or 0, reverse=True)
    index_file = OUTPUT_DIR / "salaries_index.json"
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"\n✅ Índice salvo: {index_file}")
    print("✅ Pronto!")


if __name__ == "__main__":
    main()
