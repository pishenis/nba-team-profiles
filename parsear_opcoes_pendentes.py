"""
Lê opcoes_pendentes_2026.json e extrai de cada nota de contrato:
  - tipo_opcao: "Jogador" ou "Equipe"
  - data_decisao: data do prazo, em formato DD/MM/AAAA
  - data_confiavel: False se o ano do prazo não bater com a temporada
    a que a opção se refere (sinal de possível inconsistência na BDL)

Não chama a API — só processa o arquivo que já temos.
"""

import json
import re
from pathlib import Path


def ja_decidido(nota):
    nota_lower = nota.lower()
    # cobre "exercised", "exerciwed" (typo real visto na BDL) e variações
    radicais = ["exerci", "declin", "waive", "bought out"]
    return any(r in nota_lower for r in radicais)


def parse_nota(nota):
    if "Player Option" in nota:
        tipo = "Jogador"
    elif "Club Option" in nota or "Team Option" in nota:
        tipo = "Equipe"
    else:
        tipo = "Desconhecido"

    # prefixo da nota, ex: "2026-27:" -> ano de início = 2026
    m_temporada = re.match(r"(\d{4})-(\d{2}):", nota)
    temporada_inicio = int(m_temporada.group(1)) if m_temporada else None

    # qualquer data M/D/AA ou M/D/AAAA na nota (não exige a palavra "deadline",
    # porque algumas notas só colocam a data entre parênteses sem ela)
    m_data = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b", nota)
    data_decisao = None
    data_confiavel = None
    if m_data:
        mes, dia, ano_str = m_data.groups()
        ano = int(ano_str) if len(ano_str) == 4 else 2000 + int(ano_str)
        data_decisao = f"{dia.zfill(2)}/{mes.zfill(2)}/{ano}"
        data_confiavel = (temporada_inicio is None) or (ano == temporada_inicio)

    return tipo, data_decisao, data_confiavel


def chave_ordenacao(p):
    if not p.get("data_decisao"):
        return "9999"
    dia, mes, ano = p["data_decisao"].split("/")
    return f"{ano}{mes}{dia}"


def main():
    path = Path("opcoes_pendentes_2026.json")
    candidatos = json.loads(path.read_text(encoding="utf-8"))

    descartados = [c for c in candidatos if ja_decidido(c["nota_opcao"])]
    pendentes = [c for c in candidatos if not ja_decidido(c["nota_opcao"])]

    if descartados:
        print(f"Removidos por já estarem decididos (inclusive typos como 'exerciwed'): {len(descartados)}")
        for d in descartados:
            pl = d["player"]
            print(f"  {pl['first_name']} {pl['last_name']} | {d['nota_opcao']}")
        print()

    for p in pendentes:
        tipo, data, confiavel = parse_nota(p["nota_opcao"])
        p["tipo_opcao"] = tipo
        p["data_decisao"] = data
        p["data_confiavel"] = confiavel

    pendentes.sort(key=chave_ordenacao)

    jogador = [p for p in pendentes if p["tipo_opcao"] == "Jogador"]
    equipe = [p for p in pendentes if p["tipo_opcao"] == "Equipe"]
    outros = [p for p in pendentes if p["tipo_opcao"] == "Desconhecido"]
    revisar = [p for p in pendentes if p["data_confiavel"] is False]
    sem_data = [p for p in pendentes if p["data_decisao"] is None]

    print(f"Free agents pendentes (já excluindo decididos): {len(pendentes)}")
    print(f"Opção de Jogador: {len(jogador)}")
    print(f"Opção de Equipe: {len(equipe)}")
    print(f"Não identificado: {len(outros)}")
    print(f"Precisam revisão manual (ano do prazo não bate com a temporada): {len(revisar)}")
    print(f"Sem prazo informado na nota: {len(sem_data)}")

    out_path = Path("opcoes_pendentes_2026_parsed.json")
    out_path.write_text(json.dumps(pendentes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSalvo em {out_path.resolve()}")

    print("\n=== Opção de Equipe (ordenado por data) ===")
    for p in equipe:
        pl = p["player"]
        nome = f"{pl['first_name']} {pl['last_name']}"
        time = (p["team"] or {}).get("abbreviation", "?")
        if p["data_decisao"] is None:
            flag = "  (sem prazo informado)"
        elif p["data_confiavel"] is False:
            flag = "  ⚠ revisar manualmente (ano inconsistente)"
        else:
            flag = ""
        print(f"  {nome:25s} | {time:4s} | {p['data_decisao']}{flag}")

    print("\n=== Opção de Jogador (ordenado por data) ===")
    for p in jogador:
        pl = p["player"]
        nome = f"{pl['first_name']} {pl['last_name']}"
        time = (p["team"] or {}).get("abbreviation", "?")
        if p["data_decisao"] is None:
            flag = "  (sem prazo informado)"
        elif p["data_confiavel"] is False:
            flag = "  ⚠ revisar manualmente (ano inconsistente)"
        else:
            flag = ""
        print(f"  {nome:25s} | {time:4s} | {p['data_decisao']}{flag}")

    if outros:
        print("\n=== Não identificado (conferir manualmente) ===")
        for p in outros:
            pl = p["player"]
            print(f"  {pl['first_name']} {pl['last_name']} | {p['nota_opcao']}")


if __name__ == "__main__":
    main()
