#!/bin/bash
# ─────────────────────────────────────────────────────────
# Bola Presa Stats — Orquestrador de coleta (roda via cron no servidor)
#
# Uso: ./cron_stats.sh <diario|jogos|free-agents|playoffs>
#
#   diario       coletar_todos_jogos.py + corrigir_starter.py + generate_salaries.py +
#                generate_advanced.py (cadência diária)
#   jogos        coletar_todos_jogos.py + corrigir_starter.py, em alta frequência
#                no horário de jogos (sem os passos de salário/advanced)
#   free-agents  pipeline completa de free agents (atualizar_free_agents.sh)
#   playoffs     coletar_playoffs.py + coletar_head2head.py — playoffs 2025-26
#                encerrados; este modo NÃO entra no crontab. Reativar manualmente
#                (crontab -e) só a partir de abril/2027.
#
# flock em /tmp/bp-stats.lock evita execuções simultâneas — o cron de
# `git pull` de 5 minutos usa o mesmo lock (ver crontab).
# ─────────────────────────────────────────────────────────

set -uo pipefail

REPO_DIR="/var/www/bolapresa-stats"
LOCK_FILE="/tmp/bp-stats.lock"
LOG_DIR="/var/log/bp-stats"
MAX_LOG_SIZE=$((1024 * 1024))  # 1 MB

MODE="${1:-}"
case "$MODE" in
  diario|jogos|free-agents|playoffs) ;;
  *)
    echo "Uso: $0 <diario|jogos|free-agents|playoffs>" >&2
    exit 1
    ;;
esac

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$MODE.log"

# Rotação simples: trunca se passar de 1 MB
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
  : > "$LOG_FILE"
fi

log() {
  echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') [$MODE] $*" >> "$LOG_FILE"
}

# Lock compartilhado — se já houver uma execução rodando (deste script ou do
# pull de 5 min), sai sem esperar.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "já há uma execução em andamento — saindo"
  exit 0
fi

cd "$REPO_DIR" || { echo "não achei $REPO_DIR" >&2; exit 1; }

# Arquivos que sempre ficam com a versão do GitHub em caso de conflito
# (gerados por coleta, não editados manualmente) — mesma lógica do publicar.sh
AUTO_RESOLVE_THEIRS=(
  "head2head.json"
  "jogos_playoffs.json"
  "atualizar.log"
)

# Verifica se estamos em rebase (conflito de commit sendo reaplicado)
in_rebase() {
  [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]
}

# Resolve os arquivos conhecidos do conflito atual usando a versão do GitHub.
# IMPORTANTE: tanto num conflito de rebase quanto num conflito de reaplicação
# do autostash, "--ours" é a versão já pulada do GitHub e "--theirs" é a
# versão local (confirmado empiricamente; no rebase o rótulo é contraintuitivo
# porque HEAD, durante a repetição de cada commit, é o próprio upstream).
# Retorna 1 se sobrar algum arquivo não previsto em conflito.
resolve_known_conflicts() {
  local unresolved="$1"
  local unknown=""
  local f known auto
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    known=0
    for auto in "${AUTO_RESOLVE_THEIRS[@]}"; do
      if [ "$f" = "$auto" ]; then
        git checkout --ours "$f" 2>/dev/null && git add "$f"
        known=1
        break
      fi
    done
    [ "$known" = "0" ] && unknown="$unknown $f"
  done <<< "$unresolved"
  if [ -n "$unknown" ]; then
    log "conflitos em arquivos não previstos:$unknown"
    return 1
  fi
  return 0
}

# git pull --rebase --autostash, resolvendo conflitos conhecidos — cobre tanto
# conflito de rebase de commit (fica em .git/rebase-merge|apply) quanto
# conflito na reaplicação do autostash (não fica em nenhum diretório de
# rebase, mas deixa "unmerged paths" na árvore — precisa de "git stash drop"
# no final). Retorna 1 em falha real (conflito não resolvido ou erro de rede/auth).
pull_rebase() {
  git pull --rebase --autostash >> "$LOG_FILE" 2>&1
  local pull_status=$?

  local rebasing=0
  in_rebase && rebasing=1
  local unresolved
  unresolved=$(git diff --name-only --diff-filter=U 2>/dev/null || true)

  if [ $pull_status -ne 0 ] && [ "$rebasing" = "0" ] && [ -z "$unresolved" ]; then
    log "ERRO: git pull --rebase falhou sem conflito (rede/auth?) — abortando"
    return 1
  fi

  while [ "$rebasing" = "1" ] || [ -n "$unresolved" ]; do
    if [ -n "$unresolved" ]; then
      if ! resolve_known_conflicts "$unresolved"; then
        if [ "$rebasing" = "1" ]; then
          git rebase --abort 2>/dev/null || true
        fi
        log "ERRO: conflito não resolvido automaticamente — abortando"
        return 1
      fi
    fi

    if [ "$rebasing" = "1" ]; then
      GIT_EDITOR=true git rebase --continue >> "$LOG_FILE" 2>&1 || true
    else
      # conflito era da reaplicação do autostash — já resolvido e staged acima
      git stash drop >> "$LOG_FILE" 2>&1 || true
    fi

    rebasing=0
    in_rebase && rebasing=1
    unresolved=$(git diff --name-only --diff-filter=U 2>/dev/null || true)
  done

  return 0
}

log "=== início (modo: $MODE) ==="

# Rebase travado de uma execução anterior interrompida (queda de energia etc.)
if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
  log "rebase travado de execução anterior — abortando para recomeçar limpo"
  git rebase --abort 2>/dev/null || true
fi

log "sincronizando com o GitHub (pull --rebase --autostash)"
if ! pull_rebase; then
  log "=== fim (modo: $MODE, falhou no pull) ==="
  exit 1
fi

PYTHON="$REPO_DIR/venv/bin/python3"

run_collectors() {
  case "$MODE" in
    diario)
      "$PYTHON" coletar_todos_jogos.py
      "$PYTHON" corrigir_starter.py
      "$PYTHON" generate_salaries.py
      "$PYTHON" generate_advanced.py
      ;;
    jogos)
      "$PYTHON" coletar_todos_jogos.py
      "$PYTHON" corrigir_starter.py
      ;;
    free-agents)
      # atualizar_free_agents.sh chama "python" internamente — precisa do venv ativado
      source "$REPO_DIR/venv/bin/activate"
      bash atualizar_free_agents.sh
      ;;
    playoffs)
      "$PYTHON" coletar_playoffs.py
      "$PYTHON" coletar_head2head.py
      ;;
  esac
}

log "rodando coletores..."
if ! run_collectors >> "$LOG_FILE" 2>&1; then
  log "ERRO: coleta falhou (modo $MODE) — não commitando"
  log "=== fim (modo: $MODE, falhou na coleta) ==="
  exit 1
fi

case "$MODE" in
  free-agents)
    git add data/free-agents/
    ;;
  *)
    git add -A
    ;;
esac

if git diff --staged --quiet; then
  log "sem mudanças nos dados — nada para commitar"
  log "=== fim (modo: $MODE, sem mudanças) ==="
  exit 0
fi

COMMIT_MSG="Atualização $MODE $(date -u '+%Y-%m-%d %H:%M') UTC"
git commit -m "$COMMIT_MSG" >> "$LOG_FILE" 2>&1
log "commit criado: $COMMIT_MSG"

PUSH_OK=0
for attempt in 1 2; do
  if git push >> "$LOG_FILE" 2>&1; then
    PUSH_OK=1
    break
  fi
  log "push rejeitado (tentativa $attempt) — sincronizando de novo"
  if ! pull_rebase; then
    break
  fi
done

if [ "$PUSH_OK" = "1" ]; then
  log "push concluído com sucesso"
else
  log "ERRO: push falhou após retries"
  log "=== fim (modo: $MODE, falhou no push) ==="
  exit 1
fi

log "=== fim (modo: $MODE) ==="
