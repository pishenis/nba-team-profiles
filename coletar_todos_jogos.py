import json
import subprocess
import sys
import os

print("Carregando jogos_playoffs.json...")
with open("jogos_playoffs.json") as f:
    data = json.load(f)

# Coleta todos os game_ids
all_games = []
for serie_id, games in data["series"].items():
    for g in games:
        all_games.append((serie_id, g["game_id"], g["home"], g["away"], g["game_number"]))

# Verifica quais já foram coletados
already = {f.replace("jogo_","").replace(".json","") for f in os.listdir(".") if f.startswith("jogo_") and f.endswith(".json")}

to_collect = [(s,gid,h,a,n) for s,gid,h,a,n in all_games if gid not in already]

print(f"  {len(all_games)} jogos no total · {len(already)} já coletados · {len(to_collect)} para coletar")

if not to_collect:
    print("Nada a coletar.")
    sys.exit(0)

for i, (serie_id, game_id, home, away, num) in enumerate(to_collect):
    print(f"\n[{i+1}/{len(to_collect)}] {serie_id} · Jogo {num} · {away} @ {home} ({game_id})")
    result = subprocess.run(
        [sys.executable, "coletar_jogo.py", game_id],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  ERRO ao coletar {game_id}")

print(f"\nFeito! {len(to_collect)} jogos coletados.")