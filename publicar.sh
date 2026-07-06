#!/bin/bash
# ─────────────────────────────────────────────────────────
# Bola Presa Stats — Publicar com segurança (resolve sozinho)
# Uso: ./publicar.sh "mensagem do commit"
# ─────────────────────────────────────────────────────────

set -e

MSG="${1:-Atualização $(date +%Y-%m-%d_%H:%M)}"

# Arquivos que SEMPRE devem ficar com a versão do GitHub em caso de conflito
# (são gerados pelo GitHub Actions, não editados localmente)
AUTO_RESOLVE_THEIRS=(
  "head2head.json"
  "jogos_playoffs.json"
  "atualizar.log"
)

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
if ! git pull --rebase; then
  echo "🔧 Conflito detectado — resolvendo arquivos conhecidos automaticamente..."

  for f in "${AUTO_RESOLVE_THEIRS[@]}"; do
    if [ -f "$f" ]; then
      git checkout --theirs "$f" 2>/dev/null && git add "$f" || true
    fi
  done

  if [ -n "$(git diff --name-only --diff-filter=U)" ]; then
    echo ""
    echo "❌ Ainda há conflitos em arquivos não previstos:"
    git diff --name-only --diff-filter=U
    echo ""
    echo "Resolva manualmente com:"
    echo "  git checkout --theirs NOME_DO_ARQUIVO   (ou --ours, se for seu)"
    echo "  git add NOME_DO_ARQUIVO"
    echo "  git rebase --continue"
    exit 1
  fi

  GIT_EDITOR=true git rebase --continue
  echo "✅ Conflito resolvido automaticamente."
fi

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
  echo "⚠️  Push falhou de novo — rodando mais uma vez a sincronização..."
  git pull --rebase
  git push
fi

echo ""
echo "✅ Publicado com sucesso!"
