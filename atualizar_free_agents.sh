#!/bin/bash
# Atualiza todos os dados de Free Agents do zero, na ordem certa.
# Rodar sempre que quiser refletir mudanças recentes na BDL
# (ex: opções de jogador/equipe decididas, novas assinaturas).
#
# Uso:
#   cd ~/nba-team-profiles
#   source venv/bin/activate
#   bash atualizar_free_agents.sh

set -e  # para tudo se algum passo falhar, em vez de seguir com dado quebrado

echo "── 1/8 Coletando contratos por time (lista de jogadores) ──"
python explorar_contratos_fa.py

echo ""
echo "── 2/8 Coletando contratos agregados (histórico + free agency) ──"
python coletar_agregados_fa.py

echo ""
echo "── 3/8 Filtrando free agents reais de 2026 ──"
python filtrar_free_agents_reais.py

echo ""
echo "── 4/8 Enriquecendo com stats da temporada 2025-26 ──"
python enriquecer_stats_free_agents.py

echo ""
echo "── 5/8 Reconstruindo pool de comparáveis (free agency 2025) ──"
python construir_comps_2025.py

echo ""
echo "── 6/8 Calculando comparáveis para cada free agent de 2026 ──"
python gerar_comps_finais.py

echo ""
echo "── 7/8 Identificando e parseando opções pendentes ──"
python identificar_opcoes_pendentes.py
python parsear_opcoes_pendentes.py

echo ""
echo "── 8/8 Reaplicando correções manuais confirmadas ──"
python aplicar_correcoes_manuais.py

echo ""
echo "── Copiando arquivos finais para data/free-agents/ ──"
mkdir -p data/free-agents
cp free_agents_2026_final.json data/free-agents/
cp opcoes_pendentes_2026_parsed.json data/free-agents/

echo ""
echo "✅ Atualização completa. Arquivos prontos em data/free-agents/"
