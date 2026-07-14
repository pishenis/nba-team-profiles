#!/bin/bash
# ─────────────────────────────────────────────────────────
# Bola Presa Stats — Orquestrador de coleta (roda via cron no servidor)
#
# Uso: ./cron_stats.sh <diario|jogos|free-agents|playoffs>
#
#   diario       coletar_todos_jogos.py + corrigir_starter.py (cadência diária)
#   jogos        os mesmos coletores acima, em alta frequência no horário de jogos
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

resolve_and_continue() {
  while [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; do
    UNRESOLVED=$(git diff --name-only --diff-filter=U 2>/dev/null || true)
    if [ -n "$UNRESOLVED" ]; then
      UNKNOWN=""
      for f in $UNRESOLVED; do
        KNOWN=0
        for auto in "${AUTO_RESOLVE_THEIRS[@]}"; do
          if [ "$f" = "$auto" ]; then
            git checkout --theirs "$f" 2>/dev/null && git add "$f"
            KNOWN=1
            break
          fi
        done
        [ "$KNOWN" = "0" ] && UNKNOWN="$UNKNOWN $f"
      done
      if [ -n "$UNKNOWN" ]; then
        log "conflitos em arquivos não previstos:$UNKNOWN"
        return 1
      fi
    fi
    GIT_EDITOR=true git rebase --continue >> "$LOG_FILE" 2>&1 || true
  done
  return 0
}

# git pull --rebase --autostash, resolvendo conflitos conhecidos.
# Retorna 1 em falha real (conflito não resolvido ou erro de rede/auth).
pull_rebase() {
  git pull --rebase --autostash >> "$LOG_FILE" 2>&1
  local status=$?
  if [ $status -ne 0 ]; then
    if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
      log "conflito no pull — resolvendo arquivos conhecidos"
      if ! resolve_and_continue; then
        git rebase --abort 2>/dev/null || true
        log "ERRO: conflito não resolvido automaticamente — abortando"
        return 1
      fi
      if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
        git rebase --abort 2>/dev/null || true
        log "ERRO: rebase não terminou de resolver — abortando"
        return 1
      fi
    else
      log "ERRO: git pull --rebase falhou sem conflito (rede/auth?) — abortando"
      return 1
    fi
  fi
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
    diario|jogos)
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
