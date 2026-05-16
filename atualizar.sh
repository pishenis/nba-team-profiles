#!/bin/bash
DIR="/Users/macintoshhd/nba-team-profiles"
cd "$DIR"
source "$DIR/venv/bin/activate"

echo "$(date): Iniciando atualizacao..." >> "$DIR/atualizar.log"

python3 "$DIR/coletar_playoffs.py" >> "$DIR/atualizar.log" 2>&1
python3 "$DIR/coletar_todos_jogos.py" >> "$DIR/atualizar.log" 2>&1
python3 "$DIR/corrigir_starter.py" >> "$DIR/atualizar.log" 2>&1

cd "$DIR"
git add -A
git commit -m "Atualizacao playoffs $(date '+%Y-%m-%d')" >> "$DIR/atualizar.log" 2>&1
git push >> "$DIR/atualizar.log" 2>&1

echo "$(date): Atualizacao concluida." >> "$DIR/atualizar.log"