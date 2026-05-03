import json
import glob

files = glob.glob("jogo_*.json")
print(f"{len(files)} arquivos encontrados")

fixed = 0
for path in files:
    try:
        with open(path) as f:
            data = json.load(f)

        changed = False
        for team, players in data.get("box_score", {}).items():
            for p in players:
                correct = p.get("pos", "") != ""
                if p.get("starter") != correct:
                    p["starter"] = correct
                    changed = True

        if changed:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            fixed += 1

    except Exception as e:
        print(f"  Erro em {path}: {e}")

print(f"Pronto! {fixed} arquivos corrigidos.")
