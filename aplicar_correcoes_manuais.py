"""
Aplica correções manuais conferidas por você contra o tracker oficial da
NBA.com. Existem casos que o texto livre da BDL não deixa claro (opção não
exercida sem anotação explícita, ou data de prazo errada) — em vez de tentar
adivinhar por heurística, esse arquivo guarda as correções confirmadas à mão.

Pra adicionar uma nova correção: só acrescentar um item em CORRECOES e rodar
de novo. O script é seguro de rodar mais de uma vez (não duplica).
"""

import os
import json
import time
import math
from pathlib import Path
from collections import defaultdict

import requests
from dotenv import load_dotenv

ENV_PATH = Path.home() / "nba-team-profiles" / ".env"
load_dotenv(ENV_PATH)
API_KEY = os.getenv("BDL_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}
SEASON = 2025

# ── CORREÇÕES CONFIRMADAS MANUALMENTE (atualizado NBA.com 30/06/2026) ────────
# acao: "remover_pendente"     → tira de opcoes_pendentes (ficou no time)
#        "mover_para_confirmado" → move de pendentes → lista principal como FA
#        "adicionar_direto"      → insere na lista principal (não estava em pendentes)
#        "corrigir_status"       → corrige free_agent_status de quem já está na lista
#        "anotar"                → adiciona metadados em pendentes sem mover
CORRECOES = [
    # ── Team/Player Option NÃO exercida (erro de classificação do pipeline) ──
    {
        "nome": "Wendell Carter Jr.",
        "acao": "remover_pendente",
        "motivo": "Não aparece como free agent no tracker oficial da NBA.com",
    },
    # ── Team/Player Option EXERCIDA → jogador fica no time, não é FA ─────────
    {
        "nome": "Pelle Larsson",
        "acao": "remover_pendente",
        "motivo": "Heat exerceram Team Option — permanece no time (NBA.com 30/06/2026)",
    },
    {
        "nome": "Micah Potter",
        "acao": "remover_pendente",
        "motivo": "Pacers exerceram Team Option — permanece no time (NBA.com 30/06/2026)",
    },
    # Player Options exercidas
    {
        "nome": "Deandre Ayton",
        "acao": "remover_pendente",
        "motivo": "Lakers — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Kentavious Caldwell-Pope",
        "acao": "remover_pendente",
        "motivo": "Grizzlies — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Gary Harris",
        "acao": "remover_pendente",
        "motivo": "Bucks — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Zach LaVine",
        "acao": "remover_pendente",
        "motivo": "Kings — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Kevin Porter Jr.",
        "acao": "remover_pendente",
        "motivo": "Bucks — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Taurean Prince",
        "acao": "remover_pendente",
        "motivo": "Bucks — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "D'Angelo Russell",
        "acao": "remover_pendente",
        "motivo": "Wizards — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jericho Sims",
        "acao": "remover_pendente",
        "motivo": "Bucks — Player Option exercida (NBA.com 30/06/2026)",
    },
    {
        "nome": "Andrew Wiggins",
        "acao": "remover_pendente",
        "motivo": "Heat — Player Option exercida (NBA.com 30/06/2026)",
    },
    # Team Options exercidas
    {
        "nome": "Dalano Banton",
        "acao": "remover_pendente",
        "motivo": "Celtics exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jamaree Bouyea",
        "acao": "remover_pendente",
        "motivo": "Suns exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Pat Connaughton",
        "acao": "remover_pendente",
        "motivo": "Hornets exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Luguentz Dort",
        "acao": "remover_pendente",
        "motivo": "Thunder exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Mouhamadou Gueye",
        "acao": "remover_pendente",
        "motivo": "Bulls exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Mouhamed Gueye",
        "acao": "remover_pendente",
        "motivo": "Hawks exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "GG Jackson",
        "acao": "remover_pendente",
        "motivo": "Grizzlies exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Trayce Jackson-Davis",
        "acao": "remover_pendente",
        "motivo": "Raptors exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Brook Lopez",
        "acao": "remover_pendente",
        "motivo": "Clippers exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Karlo Matkovic",
        "acao": "remover_pendente",
        "motivo": "Pelicans exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Leonard Miller",
        "acao": "remover_pendente",
        "motivo": "Bulls exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jamal Shead",
        "acao": "remover_pendente",
        "motivo": "Raptors exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Tolu Smith",
        "acao": "remover_pendente",
        "motivo": "Pistons exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jordan Walsh",
        "acao": "remover_pendente",
        "motivo": "Celtics exerceram Team Option (NBA.com 30/06/2026)",
    },
    {
        "nome": "Julian Champagnie",
        "acao": "remover_pendente",
        "motivo": "Assinou extensão antes — não é FA (NBA.com 30/06/2026)",
    },
    # ── Player/Team Option DECLINADA → são free agents ────────────────────────
    {
        "nome": "Draymond Green",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Player Option declinada — Warriors (NBA.com 30/06/2026)",
    },
    {
        "nome": "James Harden",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Player Option declinada — Clippers/Cavaliers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Sandro Mamukelashvili",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Player Option declinada — Raptors (NBA.com 30/06/2026)",
    },
    {
        "nome": "De'Anthony Melton",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Player Option declinada — Warriors (NBA.com 30/06/2026)",
    },
    {
        "nome": "Marcus Smart",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Player Option declinada — Lakers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Gary Trent Jr.",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Bucks (NBA.com 30/06/2026)",
    },
    {
        "nome": "Nicolas Batum",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Clippers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Bogdan Bogdanovic",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Clippers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Isaiah Hartenstein",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Thunder (NBA.com 30/06/2026)",
    },
    {
        "nome": "Andre Jackson Jr.",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Bucks (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jonathan Kuminga",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Warriors/Hawks (NBA.com 30/06/2026)",
    },
    {
        "nome": "Kevon Looney",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Pelicans (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jonathan Mogbo",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Raptors (NBA.com 30/06/2026)",
    },
    {
        "nome": "Julian Phillips",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Bulls/Timberwolves; vira UFA (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jalen Pickett",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Nuggets (NBA.com 30/06/2026)",
    },
    {
        "nome": "Trendon Watford",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — 76ers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Kenrich Williams",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Thunder (NBA.com 30/06/2026)",
    },
    {
        "nome": "Ziaire Williams",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Nets (NBA.com 30/06/2026)",
    },
    {
        "nome": "Day'Ron Sharpe",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Nets (NBA.com 30/06/2026)",
    },
    {
        "nome": "Josh Minott",
        "acao": "mover_para_confirmado",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Celtics/Nets (NBA.com 30/06/2026)",
    },
    {
        "nome": "Kobe Bufkin",
        "acao": "mover_para_confirmado",
        "novo_status": "RFA",
        "motivo": "Team Option declinada — Lakers/Clippers → RFA (NBA.com 30/06/2026)",
    },
    # ── FA confirmados mas ausentes das listas BDL (adicionar direto) ─────────
    {
        "nome": "Bradley Beal",
        "acao": "adicionar_direto",
        "novo_status": "UFA",
        "motivo": "Player Option declinada — Clippers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Ron Harper Jr.",
        "acao": "adicionar_direto",
        "novo_status": "UFA",
        "motivo": "Team Option declinada — Celtics (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jordan Miller",
        "acao": "adicionar_direto",
        "novo_status": "RFA",
        "motivo": "QO recebida — Clippers (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jamir Watkins",
        "acao": "adicionar_direto",
        "novo_status": "RFA",
        "motivo": "QO recebida — Wizards (NBA.com 30/06/2026)",
    },
    # ── Status errado: BDL classifica como RFA, mas não houve QO (são UFA) ────
    {
        "nome": "Ochai Agbaji",
        "acao": "corrigir_status",
        "novo_status": "UFA",
        "motivo": "Sem Qualifying Offer — é UFA, não RFA (NBA.com 30/06/2026)",
    },
    {
        "nome": "Ousmane Dieng",
        "acao": "corrigir_status",
        "novo_status": "UFA",
        "motivo": "Sem Qualifying Offer — é UFA, não RFA (NBA.com 30/06/2026)",
    },
    {
        "nome": "Ariel Hukporti",
        "acao": "corrigir_status",
        "novo_status": "UFA",
        "motivo": "Sem Qualifying Offer — é UFA, não RFA (NBA.com 30/06/2026)",
    },
    {
        "nome": "Keshad Johnson",
        "acao": "corrigir_status",
        "novo_status": "UFA",
        "motivo": "Sem Qualifying Offer — é UFA, não RFA (NBA.com 30/06/2026)",
    },
    {
        "nome": "Keaton Wallace",
        "acao": "corrigir_status",
        "novo_status": "UFA",
        "motivo": "Sem Qualifying Offer — é UFA, não RFA (NBA.com 30/06/2026)",
    },
    {
        "nome": "Jalen Wilson",
        "acao": "corrigir_status",
        "novo_status": "UFA",
        "motivo": "Sem Qualifying Offer — é UFA, não RFA (NBA.com 30/06/2026)",
    },
]


def posicao_score(pos):
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


def rotulo_qualidade(d):
    if d < 0.25:
        return "muito parecido"
    if d < 0.45:
        return "parecido"
    if d < 0.65:
        return "referência distante"
    return "pouco confiável"


def buscar_season_average(player_id):
    resp = requests.get(
        f"{BASE_URL}/season_averages/general",
        params={
            "season": SEASON,
            "season_type": "regular",
            "type": "base",
            "player_ids[]": player_id,
        },
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    dados = resp.json().get("data", [])
    return dados[0]["stats"] if dados else None


def nome_jogador(p):
    return f"{p['first_name']} {p['last_name']}"


def main():
    finais = json.loads(Path("free_agents_2026_final.json").read_text(encoding="utf-8"))
    pendentes = json.loads(Path("opcoes_pendentes_2026_parsed.json").read_text(encoding="utf-8"))
    comps_pool = json.loads(Path("data/free-agents/comps_free_agency_2025.json").read_text(encoding="utf-8"))
    agregados = json.loads(Path("contratos_agregados_raw.json").read_text(encoding="utf-8"))

    # evita duplicar se o script for rodado de novo
    nomes_ja_no_principal = {nome_jogador(f["player"]) for f in finais}

    comps_validos = []
    for c in comps_pool:
        if not c.get("stats_2024_25"):
            continue
        c["_pos_score"] = posicao_score((c.get("player") or {}).get("position"))
        comps_validos.append(c)

    por_jogador_agregado = defaultdict(list)
    for c in agregados:
        if c.get("start_year") is not None:
            por_jogador_agregado[c["player_id"]].append(c)

    log = []

    for corr in CORRECOES:
        nome_alvo = corr["nome"]
        acao = corr["acao"]

        if acao == "remover_pendente":
            antes = len(pendentes)
            pendentes[:] = [p for p in pendentes if nome_jogador(p["player"]) != nome_alvo]
            removidos = antes - len(pendentes)
            if removidos:
                log.append(f"REMOVIDO de pendentes: {nome_alvo} — {corr['motivo']}")

        elif acao == "anotar":
            achou = False
            for p in pendentes:
                if nome_jogador(p["player"]) == nome_alvo:
                    p["confirmado_manualmente"] = True
                    p["motivo_confirmacao"] = corr["motivo"]
                    if "tipo_fa_se_recusado" in corr:
                        p["tipo_fa_se_recusado"] = corr["tipo_fa_se_recusado"]
                    achou = True
            log.append(
                f"ANOTADO: {nome_alvo} — {corr['motivo']}"
                if achou
                else f"AVISO: {nome_alvo} não encontrado em pendentes pra anotar"
            )

        elif acao == "mover_para_confirmado":
            entrada_pendente = next(
                (p for p in pendentes if nome_jogador(p["player"]) == nome_alvo), None
            )
            ja_no_principal = nome_alvo in nomes_ja_no_principal

            # Remove de pendentes de qualquer forma, se estiver lá — mesmo
            # que já tenha sido movido pra lista principal numa rodada
            # anterior (evita duplicar se o pendentes for regenerado depois)
            if entrada_pendente:
                pendentes[:] = [p for p in pendentes if nome_jogador(p["player"]) != nome_alvo]

            if ja_no_principal:
                log.append(f"JÁ ESTAVA na lista principal: {nome_alvo} (pulado o reprocessamento)")
                continue

            if not entrada_pendente:
                log.append(f"AVISO: {nome_alvo} não encontrado em pendentes nem na lista principal")
                continue

            pid = entrada_pendente["player_id"]
            entradas = por_jogador_agregado.get(pid, [])
            entradas_validas = [e for e in entradas if e.get("start_year") is not None]
            base = (
                max(entradas_validas, key=lambda e: (e["start_year"], e.get("end_year") or 0))
                if entradas_validas
                else entrada_pendente
            )

            nova_entrada = dict(base)
            nova_entrada["free_agent_status"] = corr["novo_status"]
            nova_entrada["free_agent_year"] = 2026
            nova_entrada["_confirmado_manualmente"] = corr["motivo"]

            print(f"Buscando stats 2025-26 de {nome_alvo}...")
            stats = buscar_season_average(pid)
            time.sleep(0.15)
            nova_entrada["stats_2025_26"] = stats

            if stats:
                pos_score = posicao_score(nova_entrada["player"].get("position"))
                candidatos = sorted(
                    (
                        (distancia(stats, pos_score, c["stats_2024_25"], c["_pos_score"]), c)
                        for c in comps_validos
                    ),
                    key=lambda x: x[0],
                )
                top3 = []
                for d, c in candidatos[:3]:
                    p_c = c["player"]
                    nc = c["novo_contrato"]
                    top3.append(
                        {
                            "nome": nome_jogador(p_c),
                            "posicao": p_c.get("position"),
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
                nova_entrada["comparaveis"] = top3
            else:
                nova_entrada["comparaveis"] = []

            finais.append(nova_entrada)
            nomes_ja_no_principal.add(nome_alvo)
            pendentes[:] = [p for p in pendentes if nome_jogador(p["player"]) != nome_alvo]
            log.append(
                f"MOVIDO para lista principal como {corr['novo_status']}: {nome_alvo} — {corr['motivo']}"
            )

        elif acao == "adicionar_direto":
            # Como mover_para_confirmado, mas sem precisar estar em pendentes.
            # Busca dados em contratos_agregados pelo nome.
            ja_no_principal = nome_alvo in nomes_ja_no_principal
            if ja_no_principal:
                log.append(f"JÁ ESTAVA na lista principal: {nome_alvo} (pulado)")
                continue

            entradas_agg = [
                c
                for cs in por_jogador_agregado.values()
                for c in cs
                if nome_jogador(c.get("player", {})) == nome_alvo
            ]
            if not entradas_agg:
                log.append(f"AVISO: {nome_alvo} não encontrado em contratos_agregados — não foi possível adicionar")
                continue

            base = max(entradas_agg, key=lambda e: (e.get("start_year") or 0, e.get("end_year") or 0))
            pid = base["player_id"]

            nova_entrada = dict(base)
            nova_entrada["free_agent_status"] = corr["novo_status"]
            nova_entrada["free_agent_year"] = 2026
            nova_entrada["_confirmado_manualmente"] = corr["motivo"]

            print(f"Buscando stats 2025-26 de {nome_alvo}...")
            stats = buscar_season_average(pid)
            time.sleep(0.15)
            nova_entrada["stats_2025_26"] = stats

            if stats:
                pos_score = posicao_score(nova_entrada.get("player", {}).get("position"))
                cands_comp = sorted(
                    ((distancia(stats, pos_score, c["stats_2024_25"], c["_pos_score"]), c) for c in comps_validos),
                    key=lambda x: x[0],
                )
                top3 = []
                for d, c in cands_comp[:3]:
                    p_c = c["player"]
                    nc = c["novo_contrato"]
                    top3.append({
                        "nome": nome_jogador(p_c),
                        "posicao": p_c.get("position"),
                        "stats_temporada_anterior": c["stats_2024_25"],
                        "assinou_com": (nc.get("team") or {}).get("abbreviation"),
                        "salario_medio": nc.get("average_salary"),
                        "anos_contrato": nc.get("contract_years"),
                        "valor_total": nc.get("total_value"),
                        "era_status": c.get("free_agent_status_2025"),
                        "distancia": round(d, 4),
                        "qualidade": rotulo_qualidade(d),
                    })
                nova_entrada["comparaveis"] = top3
            else:
                nova_entrada["comparaveis"] = []

            finais.append(nova_entrada)
            nomes_ja_no_principal.add(nome_alvo)
            log.append(f"ADICIONADO DIRETO como {corr['novo_status']}: {nome_alvo} — {corr['motivo']}")

        elif acao == "corrigir_status":
            achou = False
            for f in finais:
                if nome_jogador(f.get("player", {})) == nome_alvo:
                    f["free_agent_status"] = corr["novo_status"]
                    achou = True
            log.append(
                f"STATUS CORRIGIDO: {nome_alvo} → {corr['novo_status']} — {corr['motivo']}"
                if achou
                else f"AVISO: {nome_alvo} não encontrado na lista principal para corrigir status"
            )

    finais.sort(key=lambda f: f.get("average_salary") or 0, reverse=True)

    Path("free_agents_2026_final.json").write_text(
        json.dumps(finais, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    Path("opcoes_pendentes_2026_parsed.json").write_text(
        json.dumps(pendentes, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== LOG DE CORREÇÕES ===")
    for linha in log:
        print(" -", linha)

    print(f"\nLista principal agora tem {len(finais)} free agents")
    print(f"Lista de pendentes agora tem {len(pendentes)} jogadores")


if __name__ == "__main__":
    main()
