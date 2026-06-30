"""
Testa a hipótese: existem jogadores com Player/Team/Club Option pra 2026-27
cujo prazo de decisão ainda não passou (ou passou mas a nota não foi
atualizada) — esses não entram no nosso filtro de free agency atual porque
o contrato deles ainda "existe" formalmente até a decisão.

Não precisa chamar a API de novo — só relê contratos_agregados_raw.json.
"""

import json
from pathlib import Path
from collections import defaultdict

PALAVRAS_OPCAO = ["Player Option", "Club Option", "Team Option"]
PALAVRAS_DECIDIDO = ["exercised", "declined", "waived", "bought out"]


def main():
    raw_path = Path("contratos_agregados_raw.json")
    todos = json.loads(raw_path.read_text(encoding="utf-8"))

    por_jogador = defaultdict(list)
    for c in todos:
        if c.get("start_year") is not None:
            por_jogador[c["player_id"]].append(c)

    pendentes = []
    for pid, entradas in por_jogador.items():
        entradas.sort(key=lambda e: e["start_year"])
        mais_recente = entradas[-1]
        notes = mais_recente.get("contract_notes") or []

        for n in notes:
            if "2026-27" not in n:
                continue
            tem_opcao = any(palavra in n for palavra in PALAVRAS_OPCAO)
            if not tem_opcao:
                continue
            ja_decidido = any(p.lower() in n.lower() for p in PALAVRAS_DECIDIDO)
            if ja_decidido:
                continue

            pendentes.append(
                {
                    "player_id": pid,
                    "player": mais_recente.get("player"),
                    "team": mais_recente.get("team"),
                    "nota_opcao": n,
                    "contract_status": mais_recente.get("contract_status"),
                    "free_agent_year_atual": mais_recente.get("free_agent_year"),
                    "average_salary": mais_recente.get("average_salary"),
                }
            )
            break  # uma entrada por jogador é suficiente

    print(f"Jogadores com opção 2026-27 ainda pendente: {len(pendentes)}")

    out_path = Path("opcoes_pendentes_2026.json")
    out_path.write_text(
        json.dumps(pendentes, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Salvo em {out_path.resolve()}")

    print("\n=== Amostra (20 primeiros) ===")
    for p in pendentes[:20]:
        pl = p["player"]
        nome = f"{pl['first_name']} {pl['last_name']}"
        time = (p["team"] or {}).get("abbreviation", "?")
        print(f"  {nome:25s} | {time:4s} | {p['nota_opcao']}")


if __name__ == "__main__":
    main()
