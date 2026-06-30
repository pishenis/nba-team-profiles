"""
Passo 3: a partir de contratos_agregados_raw.json (1704 entradas, várias por
jogador), pega só a entrada MAIS RECENTE de cada jogador (maior start_year)
e filtra quem realmente é free agent neste verão.

Por quê: cada jogador tem várias entradas no histórico (rookie, extensões
etc.), e entradas antigas já substituídas por uma extensão posterior ainda
carregam um free_agent_year preenchido. Olhar só a entrada mais recente
evita contar jogador que já assinou extensão como se fosse FA.
"""

import json
from pathlib import Path
from collections import defaultdict

ANO_FREE_AGENCY = 2026


def main():
    raw_path = Path("contratos_agregados_raw.json")
    if not raw_path.exists():
        raise RuntimeError(
            "contratos_agregados_raw.json não encontrado. "
            "Rode coletar_agregados_fa.py primeiro."
        )

    todos = json.loads(raw_path.read_text(encoding="utf-8"))
    print(f"Total de entradas carregadas: {len(todos)}")

    # Agrupa por player_id
    por_jogador = defaultdict(list)
    for c in todos:
        por_jogador[c["player_id"]].append(c)

    print(f"Jogadores únicos: {len(por_jogador)}")

    # Para cada jogador, pega a entrada com maior start_year
    # (em caso de empate, desempata pelo maior end_year)
    mais_recentes = []
    for pid, entradas in por_jogador.items():
        entradas_validas = [e for e in entradas if e.get("start_year") is not None]
        if not entradas_validas:
            continue
        mais_recente = max(
            entradas_validas,
            key=lambda e: (e["start_year"], e.get("end_year") or 0),
        )
        mais_recentes.append(mais_recente)

    print(f"Entradas mais recentes (1 por jogador): {len(mais_recentes)}")

    # Filtra quem é FA real neste verão
    free_agents = [
        c for c in mais_recentes if c.get("free_agent_year") == ANO_FREE_AGENCY
    ]
    free_agents.sort(
        key=lambda c: c.get("average_salary") or 0, reverse=True
    )

    print(f"\n=== FREE AGENTS REAIS deste verão ({ANO_FREE_AGENCY}): {len(free_agents)} ===\n")

    ufa = [f for f in free_agents if f.get("free_agent_status") == "UFA"]
    rfa = [f for f in free_agents if f.get("free_agent_status") == "RFA"]
    print(f"UFA: {len(ufa)} | RFA: {len(rfa)}\n")

    for c in free_agents[:30]:
        p = c.get("player", {})
        nome = f"{p.get('first_name','')} {p.get('last_name','')}"
        time_anterior = (c.get("team") or {}).get("abbreviation") or "?"
        salario = c.get("average_salary")
        salario_fmt = f"${salario:,.0f}" if salario else "?"
        notes = c.get("contract_notes")
        print(
            f"  {nome:25s} | {time_anterior:4s} | {c.get('free_agent_status'):4s} | "
            f"{salario_fmt:14s} | {notes if notes else ''}"
        )

    # Salva o resultado limpo para uso posterior na página
    out_path = Path("free_agents_2026.json")
    out_path.write_text(
        json.dumps(free_agents, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSalvo em {out_path.resolve()}")

    # Aviso sobre possíveis problemas de qualidade de dado
    anos_estranhos = {
        c.get("free_agent_year")
        for c in mais_recentes
        if c.get("free_agent_year") and len(str(c.get("free_agent_year"))) != 4
    }
    if anos_estranhos:
        print(
            f"\nATENÇÃO: encontrei free_agent_year com formato estranho: {anos_estranhos} "
            "— provavelmente erro de dado na fonte da BDL, vale investigar manualmente."
        )


if __name__ == "__main__":
    main()
