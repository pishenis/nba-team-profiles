#!/bin/bash
# ─────────────────────────────────────────────────────────
# Bola Presa Stats — Publicar com segurança (resolve sozinho)
# Uso: ./publicar.sh "mensagem do commit"
# ─────────────────────────────────────────────────────────

set -e

MSG="${1:-Atualização $(date +%Y-%m-%d_%H:%M)}"

# Arquivos que SEMPRE devem ficar com a versão do GitHub em caso de conflito
# (são gerados pelo GitHub Actions, não editados localmente)
#
# ATENÇÃO — pegadinha do rebase:
# Durante `git rebase`, --ours e --theirs ficam INVERTIDOS em relação ao merge:
#   --ours   = o branch de destino (origin/main) = versão do GitHub  ← queremos esta
#   --theirs = os commits locais sendo reaplicados                    ← NÃO queremos esta
# Em merge normal seria o contrário. Por isso usamos --ours aqui.
AUTO_RESOLVE_OURS=(
  "head2head.json"
  "jogos_playoffs.json"
  "atualizar.log"
)

# Resolve todos os conflitos conhecidos e continua o rebase até o fim.
# Suporta múltiplos commits conflitantes em sequência.
resolve_and_continue() {
  while [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; do
    UNRESOLVED=$(git diff --name-only --diff-filter=U 2>/dev/null || true)

    if [ -n "$UNRESOLVED" ]; then
      echo "🔧 Conflito detectado — resolvendo arquivos conhecidos..."
      UNKNOWN=""
      for f in $UNRESOLVED; do
        KNOWN=0
        for auto in "${AUTO_RESOLVE_OURS[@]}"; do
          if [ "$f" = "$auto" ]; then
            git checkout --ours "$f" 2>/dev/null && git add "$f"
            KNOWN=1
            break
          fi
        done
        [ "$KNOWN" = "0" ] && UNKNOWN="$UNKNOWN $f"
      done

      if [ -n "$UNKNOWN" ]; then
        echo ""
        echo "❌ Conflitos em arquivos não previstos:$UNKNOWN"
        echo ""
        echo "Resolva manualmente com:"
        echo "  git checkout --theirs ARQUIVO   (ou --ours)"
        echo "  git add ARQUIVO"
        echo "  git rebase --continue"
        exit 1
      fi
    fi

    # Tenta continuar; se houver novo conflito no próximo commit, o loop volta
    GIT_EDITOR=true git rebase --continue 2>/dev/null || true
  done
}

echo "🏀 Publicando mudanças..."
echo "─────────────────────────"

if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
  echo "⚠️  Havia um rebase travado — abortando para recomeçar limpo."
  git rebase --abort 2>/dev/null || true
fi

CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "⚠️  Não estava no branch main — corrigindo."
  git checkout main
fi

STASHED=0
if [ -n "$(git status --porcelain)" ]; then
  git stash
  STASHED=1
fi

echo "⬇️  Sincronizando com o GitHub..."
git pull --rebase || resolve_and_continue

if [ "$STASHED" = "1" ]; then
  git stash pop
fi

if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -m "$MSG"
else
  echo "ℹ️  Nada novo para commitar."
fi

echo "📤 Enviando para o GitHub..."
if ! git push; then
  echo "⚠️  Push rejeitado — sincronizando de novo..."
  git pull --rebase || resolve_and_continue
  git push
fi

echo ""
echo "✅ Publicado com sucesso!"
