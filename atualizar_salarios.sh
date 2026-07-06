#!/bin/bash
# ─────────────────────────────────────────────────────────
# Bola Presa Stats — Atualização de Salários (script único)
# Roda generate_salaries.py com checagens automáticas.
# Uso: ./atualizar_salarios.sh
# ─────────────────────────────────────────────────────────

set -e  # para no primeiro erro

echo "🏀 Bola Presa Stats — Atualização de Salários"
echo "─────────────────────────────────────────────"

# 1. Confirma que está na pasta certa
if [ ! -f "generate_salaries.py" ]; then
  echo "❌ generate_salaries.py não encontrado nesta pasta."
  echo "   Rode: cd ~/nba-team-profiles  (ou onde estiver o projeto)"
  exit 1
fi

# 2. Confirma que o .env existe
if [ ! -f ".env" ]; then
  echo "❌ Arquivo .env não encontrado nesta pasta."
  echo "   Crie um arquivo .env com a linha: BDL_API_KEY=sua_chave"
  exit 1
fi

# 3. Avisa sobre overrides de troca pendentes
if [ -f "data/salaries/trade_overrides.json" ]; then
  N=$(python3 -c "import json; print(len(json.load(open('data/salaries/trade_overrides.json')).get('overrides',[])))" 2>/dev/null || echo "?")
  echo "📋 $N override(s) de troca serão aplicados"
else
  echo "ℹ️  Nenhum trade_overrides.json encontrado — seguindo só com dados da BDL"
fi

echo ""
echo "▶️  Rodando generate_salaries.py..."
echo ""

python3 generate_salaries.py

echo ""
echo "✅ Dados atualizados em data/salaries/"
echo ""
read -p "Quer commitar e enviar para o GitHub agora? (s/n) " RESP

if [ "$RESP" = "s" ] || [ "$RESP" = "S" ]; then
  git add data/salaries/
  ./publicar.sh "Atualização de salários $(date +%Y-%m-%d_%H:%M)"
else
  echo "Ok, os dados ficaram só localmente. Para publicar depois, rode:"
  echo "  ./publicar.sh \"Atualização de salários\""
fi
