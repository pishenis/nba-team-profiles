# -*- coding: utf-8 -*-
"""Gera o `nba_player_ids.json` — mapa nome do jogador → id do stats.nba.com.

Esse mapa é a ponte para as FOTOS (`cdn.nba.com/headshots/...`). Quem consome:
as páginas do Stats (rankings, salaries, free-agents) e a Bolsa de Valores dos
Jogos Bola Presa, que não tem outro caminho — a balldontlie não devolve foto
nem id da NBA em campo nenhum.

Até out/2026 não existia script: era feito à mão no Mac, uma vez por
temporada. O resultado é que o arquivo em produção envelhecia e a classe de
calouros inteira ficava sem foto — medido no beta de pré-temporada 2026-27, o
arquivo de jun/2026 cobria 94,8% do catálogo da Bolsa contra 99,8% de um
arquivo regerado.

Uso:
    venv/bin/python3 gerar_player_ids.py                     # grava no repo
    venv/bin/python3 gerar_player_ids.py --saida CAMINHO     # grava fora
    venv/bin/python3 gerar_player_ids.py --season 2026-27    # força a temporada

ONDE GRAVAR NO SERVIDOR: **fora da árvore do git.** O clone em
/var/www/bolapresa-stats se atualiza por `git pull --ff-only` no cron, e a
chave de deploy é read-only (não dá para commitar de lá). Um arquivo
rastreado modificado localmente faz o pull falhar assim que chegar um commit
que o toque — e aí o site inteiro para de atualizar por causa de uma foto.
Por isso o cron usa `--saida /var/www/bp-dados/nba_player_ids.json`.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SAIDA_PADRAO = RAIZ / "data" / "salaries" / "nba_player_ids.json"

# Abaixo disso a resposta é suspeita o bastante para não sobrescrever nada:
# a liga tem ~550-620 jogadores ativos a qualquer momento.
MINIMO_ABSOLUTO = 400


def temporada_corrente(hoje=None):
    """'2026-27' — a temporada vira em agosto, antes da pré-temporada."""
    hoje = hoje or date.today()
    inicio = hoje.year if hoje.month >= 8 else hoje.year - 1
    return f"{inicio}-{str(inicio + 1)[-2:]}"


def buscar(season):
    from nba_api.stats.endpoints import commonallplayers

    resposta = commonallplayers.CommonAllPlayers(
        is_only_current_season=1, season=season, timeout=60
    ).get_dict()["resultSets"][0]
    colunas = resposta["headers"]
    i_id = colunas.index("PERSON_ID")
    i_nome = colunas.index("DISPLAY_FIRST_LAST")
    return {linha[i_nome]: str(linha[i_id]) for linha in resposta["rowSet"] if linha[i_nome]}


def carregar_atual(caminho):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def validar(novo, atual):
    """Devolve o motivo para NÃO gravar, ou None se estiver tudo bem.

    A guarda existe porque este arquivo roda sozinho no cron: uma resposta
    vazia ou truncada da NBA sobrescrevendo um arquivo bom tira a foto de
    todo mundo, e ninguém fica sabendo até alguém abrir o site.
    """
    if not novo:
        return "a NBA devolveu ZERO jogadores"
    if len(novo) < MINIMO_ABSOLUTO:
        return f"só {len(novo)} jogadores (mínimo aceitável: {MINIMO_ABSOLUTO})"
    if atual and len(novo) < len(atual):
        return f"{len(novo)} jogadores contra {len(atual)} do arquivo atual — encolheu"
    return None


def gravar(caminho, mapa):
    """Grava de forma atômica: arquivo temporário no mesmo diretório + rename.

    Sem isso, uma queda no meio da escrita deixaria um JSON pela metade, que é
    pior que um arquivo velho — o `fetch` do navegador falha e some a foto de
    todo mundo.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dict(sorted(mapa.items())), ensure_ascii=False, indent=2) + "\n"
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=caminho.parent, prefix=".tmp_player_ids", delete=False)
    try:
        tmp.write(texto)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, caminho)
    except BaseException:
        os.unlink(tmp.name)
        raise


def main():
    ap = argparse.ArgumentParser(description="Gera o mapa nome → id da NBA (fotos)")
    ap.add_argument("--saida", default=str(SAIDA_PADRAO))
    ap.add_argument("--season", default=None, help="ex.: 2026-27 (padrão: a corrente)")
    ap.add_argument("--conferir", action="store_true",
                    help="só mostra o que mudaria, sem gravar")
    args = ap.parse_args()

    season = args.season or temporada_corrente()
    atual = carregar_atual(args.saida)
    print(f"temporada {season} | arquivo atual: {len(atual)} nomes em {args.saida}")

    try:
        novo = buscar(season)
    except Exception as e:                                  # rede, timeout, mudança de schema
        print(f"ERRO ao consultar a NBA: {type(e).__name__}: {e}", file=sys.stderr)
        print("arquivo atual preservado.", file=sys.stderr)
        return 1

    problema = validar(novo, atual)
    if problema:
        print(f"RECUSADO: {problema}", file=sys.stderr)
        print("arquivo atual preservado.", file=sys.stderr)
        return 1

    entraram = sorted(set(novo) - set(atual))
    sairam = sorted(set(atual) - set(novo))
    print(f"recebidos: {len(novo)} nomes  (+{len(entraram)} / -{len(sairam)})")
    if entraram:
        print(f"  entraram: {', '.join(entraram[:12])}" + (" ..." if len(entraram) > 12 else ""))
    if sairam:
        print(f"  saíram:   {', '.join(sairam[:12])}" + (" ..." if len(sairam) > 12 else ""))

    if args.conferir:
        print("(--conferir: nada gravado)")
        return 0

    gravar(args.saida, novo)
    print(f"gravado: {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
