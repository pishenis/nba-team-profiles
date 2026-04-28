import json
import subprocess
import sys
import os

print("Carregando jogos_playoffs.json...")
with open("jogos_playoffs.json") as f:
    data = json.load(f)

all_games = []
for serie_id, games in data["series"].items():
    for g in games:
        all_games.append((serie_id, g["game_id"], g["home"], g["away"], g["game_number"]))

# Verifica quais precisam ser coletados ou recoletados
to_collect = []
for serie_id, game_id, home, away, num in all_games:
    filename = f"jogo_{game_id}.json"
    needs_collect = False

    if not os.path.exists(filename):
        needs_collect = True
        reason = "não coletado"
    else:
        try:
            with open(filename) as f:
                d = json.load(f)
            tl = len(d.get("score_timeline", []))
            bs = len(d.get("box_score", {}).get(d.get("home",""), []))
            mu = len(d.get("matchups", []))
            if tl == 0 or bs == 0:
                needs_collect = True
                reason = "incompleto"
            elif mu == 0:
                needs_collect = True
                reason = "sem matchups"
        except:
            needs_collect = True
            reason = "erro ao ler"

    if needs_collect:
        to_collect.append((serie_id, game_id, home, away, num, reason))

already = len(all_games) - len(to_collect)
print(f"  {len(all_games)} jogos no total · {already} OK · {len(to_collect)} para coletar")

if not to_collect:
    print("Nada a coletar.")
    sys.exit(0)

for i, (serie_id, game_id, home, away, num, reason) in enumerate(to_collect):
    print(f"\n[{i+1}/{len(to_collect)}] {serie_id} · Jogo {num} · {away} @ {home} ({game_id}) · {reason}")
    result = subprocess.run(
        [sys.executable, "coletar_jogo.py", game_id],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  ERRO ao coletar {game_id}")

print(f"\nFeito! {len(to_collect)} jogos coletados.")