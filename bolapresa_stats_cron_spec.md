# Bola Presa Stats — Migração da coleta para cron no servidor

Especificação para Claude Code, executando **no servidor Hetzner** (`ssh root@5.78.86.87`). Objetivo: a coleta de dados do Stats (times, jogadores, salários, box scores, advanced, free agents) passa a rodar por **cron no servidor**, direto na pasta servida pelo nginx, eliminando a dependência dos agendamentos do GitHub Actions.

Ler `ARQUITETURA.md` na raiz do repo antes de começar.

---

## 1. Estado atual (não recriar, entender)

- `/var/www/bolapresa-stats` = clone de `pishenis/nba-team-profiles`, servido pelo nginx em `stats.bolapresa.com.br` (protegido por login)
- Cron existente: `git pull --ff-only` a cada 5 min nessa pasta (traz commits das Actions e do Mac de Denis)
- GitHub Actions (`.github/workflows/atualizar.yml`) roda os scripts de coleta: diário às 11:00 UTC (8h Brasília) + alta frequência (a cada 15 min) no horário de jogos + rotina de free agents. **Ler o workflow para extrair a lista exata de scripts, ordem, argumentos e variáveis** — o cron deve replicar fielmente o que ele faz hoje
- Scripts usam `BDL_API_KEY` (no Actions, via Secrets; no servidor ainda não existe)
- `publicar.sh` no repo contém a lógica de resolução de conflitos conhecidos (`head2head.json`, `jogos_playoffs.json`, `atualizar.log` com `--theirs`) — reaproveitar a lógica

## 2. O novo desenho

```
cron (servidor) → roda coletores Python em /var/www/bolapresa-stats
               → dados ficam servidos imediatamente (mesma pasta)
               → git commit + push ao GitHub (backup + sync com o Mac)
```

O GitHub deixa de ser canal de publicação e vira espelho. O Mac de Denis continua fonte de mudanças de **código** (páginas, scripts); o servidor vira a única fonte automática de **dados**.

## 3. Implementação

### 3.1 Ambiente Python
- Criar venv em `/var/www/bolapresa-stats/venv`; instalar dependências dos scripts (ler imports/requirements do repo)
- Denis criará manualmente o `.env` com `BDL_API_KEY` na raiz do clone (instruí-lo; não pedir a chave no chat; `chmod 600`). Conferir que `.env` já está no `.gitignore` do repo
- Python 3 do sistema (Ubuntu 26.04) — atenção: alguns scripts foram escritos para compatibilidade com Python 3.8; rodar todos uma vez manualmente e corrigir o que quebrar em versão nova

### 3.2 Push do servidor para o GitHub
- Gerar deploy key SSH: `ssh-keygen -t ed25519 -f /root/.ssh/bp_stats_deploy -N ""` e configurar `/root/.ssh/config` para usá-la com github.com
- Denis adiciona a chave pública em GitHub → repo `nba-team-profiles` → Settings → Deploy keys → **com write access** (instruí-lo, mostrando a chave pública)
- Trocar o remote do clone para SSH (`git@github.com:pishenis/nba-team-profiles.git`)
- Configurar `git config user.name "BP Stats Bot (servidor)"` e `user.email "bolapresa@gmail.com"` no clone

### 3.3 Script orquestrador `cron_stats.sh` (versionado no repo)
Um único script com modos (`diario`, `jogos`, `free-agents` — conforme o que o workflow atual tiver), que:
1. Usa `flock` num lockfile (`/tmp/bp-stats.lock`) para nunca haver duas execuções simultâneas — **o cron de `git pull` de 5 min deve passar a usar o mesmo lock**
2. `git pull --rebase --autostash` antes de coletar (com a resolução de conflitos conhecidos do `publicar.sh`)
3. Roda os coletores do modo (mesma ordem/argumentos do workflow atual), com `venv/bin/python3`
4. `git add` dos arquivos de dados → commit (mensagem com timestamp e modo) → push; em rejeição, pull --rebase e tenta de novo (máx. 2 tentativas)
5. Loga em `/var/log/bp-stats/<modo>.log` com rotação simples (truncar >1 MB); nunca logar a chave

### 3.4 Crontab (horários em UTC; replicar as cadências do workflow atual)
- Diário 11:00 UTC → `cron_stats.sh diario`
- A cada 15 min no horário de jogos (janela igual à do workflow, ex.: 0–4 UTC) → `cron_stats.sh jogos`
- Free agents: mesma cadência do workflow atual, se a rotina ainda estiver ativa
- Manter/ajustar o pull de 5 min com o lock compartilhado

### 3.5 Teste do stats.nba.com (curiosidade com valor)
Testar uma chamada de `nba_api` do servidor. Se funcionar, anotar no ARQUITETURA.md que o Hetzner não é bloqueado (abre a porta para automatizar `nba_player_ids.json`). Se falhar (esperado), nada muda: continua tarefa manual no Mac, 1x por temporada.

### 3.6 Desativar os agendamentos do Actions (SÓ após validação)
Após 48h de cron rodando limpo: editar `.github/workflows/atualizar.yml` removendo os `schedule:` e mantendo `workflow_dispatch:` (execução manual como plano B). Commit com mensagem explicando. NÃO apagar o workflow.

### 3.7 Atualizar `ARQUITETURA.md`
Refletir o estado final (cron ativo, Actions só manual, resultado do teste 3.5).

## 4. Testes de aceitação
1. `cron_stats.sh diario` manual → dados atualizados na pasta, site refletindo na hora, commit aparece no GitHub
2. `cron_stats.sh jogos` manual → idem para box scores
3. Rodar duas instâncias ao mesmo tempo → a segunda espera ou sai (lock funciona)
4. Commit de código feito no Mac + push → próximo ciclo do servidor faz rebase limpo e não sobrescreve
5. Simular conflito num arquivo conhecido → resolução automática `--theirs` funciona
6. Log legível, sem chave vazada (`grep -i` pela chave nos logs → nada)
7. Cron de verdade: conferir execução automática no horário (via log) por 1 dia antes do passo 3.6

## 5. Fora de escopo
- Mudar qualquer lógica dos coletores (é migração de onde rodam, não do que fazem)
- Arquivamento da temporada 25-26 / preparação da 26-27 (projeto separado)
