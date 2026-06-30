"""
Passo 4: detecta quem saiu da lista de free agents entre a execução anterior
e a atual (ou seja, provavelmente assinou contrato novo) e registra num log
acumulativo em data/free-agents/assinaturas_recentes.json.

Lê:
  - free_agents_2026.json (gerado agora pelo passo 3 — estado atual)
  - data/free-agents/free_agents_2026_snapshot.json (estado da execução anterior)
  - data/free-agents/assinaturas_recentes.json (log acumulativo, se já existir)
  - contratos_agregados_raw.json (pra buscar detalhes do contrato novo)

Escreve:
  - data/free-agents/assinaturas_recentes.json (log atualizado)
  - data/free-agents/free_agents_2026_snapshot.json (novo snapshot = estado atual)

Nota: usar player_id como chave de deduplicação garante que rodar várias vezes
não duplica entradas no log acumulativo.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

FA_ATUAL_PATH = Path("free_agents_2026.json")
SNAPSHOT_PATH = Path("data/free-agents/free_agents_2026_snapshot.json")
ASSINATURAS_PATH = Path("data/free-agents/assinaturas_recentes.json")
AGREGADOS_PATH = Path("contratos_agregados_raw.json")


def main():
    fa_atuais = json.loads(FA_ATUAL_PATH.read_text(encoding="utf-8"))
    ids_atuais = {fa["player_id"] for fa in fa_atuais}

    if not SNAPSHOT_PATH.exists():
        print("Sem snapshot anterior — primeira execução. Salvando snapshot para o próximo ciclo.")
        SNAPSHOT_PATH.write_text(
            json.dumps(fa_atuais, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return

    fa_anteriores = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    por_id_anterior = {fa["player_id"]: fa for fa in fa_anteriores}

    assinaturas = (
        json.loads(ASSINATURAS_PATH.read_text(encoding="utf-8"))
        if ASSINATURAS_PATH.exists()
        else []
    )
    ids_ja_registrados = {a["player_id"] for a in assinaturas}

    # Quem estava no snapshot mas sumiu agora = provavelmente assinou
    saiu = {pid: fa for pid, fa in por_id_anterior.items() if pid not in ids_atuais}

    if not saiu:
        print("Nenhum novo contrato detectado neste ciclo.")
        SNAPSHOT_PATH.write_text(
            json.dumps(fa_atuais, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return

    # Índice dos contratos agregados pra buscar o contrato novo
    agregados_por_jogador = defaultdict(list)
    if AGREGADOS_PATH.exists():
        for c in json.loads(AGREGADOS_PATH.read_text(encoding="utf-8")):
            if c.get("start_year") is not None:
                agregados_por_jogador[c["player_id"]].append(c)

    novos = 0
    for pid, fa_ant in saiu.items():
        if pid in ids_ja_registrados:
            continue  # já registrado em ciclo anterior, não duplica

        entradas = agregados_por_jogador.get(pid, [])
        contrato_novo = None
        if entradas:
            # Entrada com start_year mais recente = o contrato que o fez sair da lista
            mais_recente = max(entradas, key=lambda e: (e["start_year"], e.get("end_year") or 0))
            # Só considera contrato novo se start_year >= 2026
            if mais_recente.get("start_year", 0) >= 2026:
                nc = mais_recente
                contrato_novo = {
                    "team": nc.get("team"),
                    "average_salary": nc.get("average_salary"),
                    "contract_years": nc.get("contract_years"),
                    "total_value": nc.get("total_value"),
                    "start_year": nc.get("start_year"),
                    "end_year": nc.get("end_year"),
                    "contract_type": nc.get("contract_type"),
                }

        p = fa_ant.get("player", {})
        nome = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()

        assinaturas.append({
            "player_id": pid,
            "player": p,
            "status_anterior": fa_ant.get("free_agent_status"),
            "time_anterior": (fa_ant.get("team") or {}).get("abbreviation"),
            "salario_anterior": fa_ant.get("average_salary"),
            "stats_2025_26": fa_ant.get("stats_2025_26"),
            "novo_contrato": contrato_novo,
            "detectado_em": datetime.now(timezone.utc).isoformat(),
        })
        novos += 1
        time_novo = (contrato_novo or {}).get("team") or {}
        abb = time_novo.get("abbreviation", "?") if isinstance(time_novo, dict) else "?"
        sal = (contrato_novo or {}).get("average_salary")
        sal_fmt = f"${sal:,.0f}" if sal else "?"
        print(f"  NOVO: {nome} ({fa_ant.get('free_agent_status')}) → {abb} {sal_fmt}")

    print(f"\n{novos} novo(s) detectado(s). Total acumulado: {len(assinaturas)}")

    ASSINATURAS_PATH.write_text(
        json.dumps(assinaturas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    SNAPSHOT_PATH.write_text(
        json.dumps(fa_atuais, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Log salvo: {ASSINATURAS_PATH}")
    print(f"Snapshot atualizado: {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
