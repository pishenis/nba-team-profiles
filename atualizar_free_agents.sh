#!/bin/bash
# Atualiza todos os dados de Free Agents do zero, na ordem certa.
# Rodar sempre que quiser refletir mudanças recentes na BDL
# (ex: opções de jogador/equipe decididas, novas assinaturas).
#
# Uso:
#   cd ~/nba-team-profiles
#   source venv/bin/activate
#   bash atualizar_free_agents.sh

set -e  # para tudo se algum passo falhar

mkdir -p data/free-agents

echo "── 1/9 Coletando contratos por time (lista de jogadores) ──"
python explorar_contratos_fa.py

echo ""
echo "── 2/9 Coletando contratos agregados (histórico + free agency) ──"
python coletar_agregados_fa.py

echo ""
echo "── 3/9 Filtrando free agents reais de 2026 ──"
python filtrar_free_agents_reais.py

echo ""
echo "── 4/9 Detectando novas assinaturas ──"
python detectar_assinaturas.py

echo ""
echo "── 5/9 Enriquecendo com stats da temporada 2025-26 ──"
python enriquecer_stats_free_agents.py

echo ""
echo "── 6/9 Reconstruindo pool de comparáveis (free agency 2025) ──"
# Só roda se não existir ainda — pool histórico, não muda mais
if [ ! -f data/free-agents/comps_free_agency_2025.json ]; then
  python construir_comps_2025.py
else
  echo "   (arquivo já existe, pulando coleta da API)"
fi

echo ""
echo "── 7/9 Calculando comparáveis para cada free agent de 2026 ──"
python gerar_comps_finais.py

echo ""
echo "── 8/9 Identificando e parseando opções pendentes ──"
python identificar_opcoes_pendentes.py
python parsear_opcoes_pendentes.py

echo ""
echo "── 9/9 Reaplicando correções manuais confirmadas ──"
python aplicar_correcoes_manuais.py

echo ""
echo "── Copiando arquivos finais para data/free-agents/ ──"
cp free_agents_2026_final.json data/free-agents/
cp opcoes_pendentes_2026_parsed.json data/free-agents/

# Cria assinaturas_recentes.json vazio se não existir ainda
# (detectar_assinaturas.py só o cria a partir da 2ª execução)
if [ ! -f data/free-agents/assinaturas_recentes.json ]; then
  echo "[]" > data/free-agents/assinaturas_recentes.json
fi

# Timestamp da última atualização
python3 -c "
import json, datetime
ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
with open('data/free-agents/ultima_atualizacao.json', 'w') as f:
    json.dump({'timestamp': ts}, f)
print('Timestamp salvo:', ts)
"

echo ""
echo "✅ Atualização completa. Arquivos prontos em data/free-agents/"
