"""
Etapa C: para cada free agent de 2026 (com stats de 2025-26), acha o
"comparável" mais próximo entre quem assinou contrato na free agency de 2025
(com stats de 2024-25) — baseado em posição + pts/reb/ast/min.

É uma heurística simples (distância euclidiana normalizada), não um modelo
sofisticado. A ideia é dar um ponto de referência de mercado, não uma
previsão exata.
"""

import json
from pathlib import Path
import math


def posicao_score(pos):
    """Converte posição em um número pra medir 'distância' entre posições.
    G=2, F=4, C=5. Posições combinadas (ex: 'F-C') usam a média."""
    if not pos:
        return 3.0
    partes = [p for p in pos.replace(" ", "").split("-") if p]
    escala = {"G": 2, "F": 4, "C": 5}
    valores = [escala.get(p, 3) for p in partes]
    return sum(valores) / len(valores) if valores else 3.0


def normalizar(valor, maximo):
    if valor is None:
        return 0.0
    try:
        return min(float(valor), maximo) / maximo
    except (TypeError, ValueError):
        return 0.0


def distancia(stats_a, pos_score_a, stats_b, pos_score_b):
    d_pos = abs(pos_score_a - pos_score_b) / 3.0
    d_pts = normalizar(stats_a.get("pts"), 30) - normalizar(stats_b.get("pts"), 30)
    d_reb = normalizar(stats_a.get("reb"), 15) - normalizar(stats_b.get("reb"), 15)
    d_ast = normalizar(stats_a.get("ast"), 10) - normalizar(stats_b.get("ast"), 10)
    d_min = normalizar(stats_a.get("min"), 36) - normalizar(stats_b.get("min"), 36)
    return math.sqrt((d_pos * 2) ** 2 + d_pts**2 + d_reb**2 + d_ast**2 + d_min**2)


def main():
    fa_path = Path("free_agents_2026_enriched.json")
    comps_path = Path("comps_free_agency_2025.json")

    free_agents = json.loads(fa_path.read_text(encoding="utf-8"))
    comps_pool = json.loads(comps_path.read_text(encoding="utf-8"))

    # Pré-calcula posição-score e descarta comps sem stats
    comps_validos = []
    for c in comps_pool:
        if not c.get("stats_2024_25"):
            continue
        c["_pos_score"] = posicao_score((c.get("player") or {}).get("position"))
        comps_validos.append(c)

    print(f"Pool de comparáveis válidos: {len(comps_validos)}")

    def rotulo_qualidade(d):
        if d < 0.25:
            return "muito parecido"
        if d < 0.45:
            return "parecido"
        if d < 0.65:
            return "referência distante"
        return "pouco confiável"

    sem_comp = 0
    for fa in free_agents:
        stats_fa = fa.get("stats_2025_26")
        if not stats_fa:
            fa["comparaveis"] = []
            sem_comp += 1
            continue

        pos_fa = posicao_score(fa["player"].get("position"))

        candidatos = []
        for c in comps_validos:
            d = distancia(stats_fa, pos_fa, c["stats_2024_25"], c["_pos_score"])
            candidatos.append((d, c))
        candidatos.sort(key=lambda x: x[0])

        top3 = []
        for d, c in candidatos[:3]:
            p = c["player"]
            nc = c["novo_contrato"]
            top3.append(
                {
                    "nome": f"{p['first_name']} {p['last_name']}",
                    "posicao": p.get("position"),
                    "stats_temporada_anterior": c["stats_2024_25"],
                    "assinou_com": (nc.get("team") or {}).get("abbreviation"),
                    "salario_medio": nc.get("average_salary"),
                    "anos_contrato": nc.get("contract_years"),
                    "valor_total": nc.get("total_value"),
                    "era_status": c.get("free_agent_status_2025"),
                    "distancia": round(d, 4),
                    "qualidade": rotulo_qualidade(d),
                }
            )
        fa["comparaveis"] = top3
        if not top3:
            sem_comp += 1

    print(f"Free agents sem comparável: {sem_comp}")

    out_path = Path("free_agents_2026_final.json")
    out_path.write_text(
        json.dumps(free_agents, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Salvo em {out_path.resolve()}")

    print("\n=== Amostra (8 primeiros, ordenados por salário) ===")
    for fa in free_agents[:8]:
        p = fa["player"]
        nome = f"{p['first_name']} {p['last_name']}"
        comps = fa.get("comparaveis") or []
        if comps:
            print(f"  {nome} ({p.get('position')}):")
            for comp in comps:
                print(
                    f"      [{comp['qualidade']:18s} d={comp['distancia']}] {comp['nome']} "
                    f"({comp['posicao']}) -> {comp['anos_contrato']}a/"
                    f"${comp['salario_medio']:,.0f} com {comp['assinou_com']}"
                )
        else:
            print(f"  {nome} -> sem comparável (sem stats)")


if __name__ == "__main__":
    main()
