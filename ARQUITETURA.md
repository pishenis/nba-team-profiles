# Arquitetura do Ecossistema Bola Presa

Documento de referência. Qualquer sessão de Claude Code (ou humano) deve ler isto antes de mexer em qualquer parte do sistema. Atualizar este arquivo sempre que a arquitetura mudar.

Última atualização: julho/2026 (pós-migração da coleta do Stats para cron no servidor).

---

## Visão geral

O Bola Presa (podcast brasileiro de NBA, de Denis Botana e Danilo) mantém um ecossistema de sites e ferramentas para assinantes do Apoia-se, unificado sob o domínio `bolapresa.com.br` com **login único** (single sign-on via cookie no domínio raiz).

| Endereço | O que é | Hospedagem | Acesso |
|---|---|---|---|
| `bolapresa.com.br` (+ `www`) | Site principal (Next.js) | Netlify | Público (área de assinantes própria — ver Pendências) |
| `conta.bolapresa.com.br` | Serviço de conta: cadastro, login, sessão, painel de perguntas | Hetzner | Público (painel: só admin) |
| `stats.bolapresa.com.br` | Bola Presa Stats (site estático de estatísticas NBA) | Hetzner | Só assinantes |
| `oraculo.bolapresa.com.br` | Oráculo NBA (Q&A histórico) | Hetzner | Só assinantes |
| `jogos.bolapresa.com.br` | Bingo e jogos (em construção) | Hetzner | Só assinantes |

**DNS:** os quatro subdomínios são CNAMEs para `claude.bolapresa.com.br`, que aponta (registro A) para o IP do servidor. Para trocar de servidor, basta mudar esse único registro A. **Não apagar o registro `claude`** — tudo depende dele. O domínio raiz e `www` apontam para o Netlify.

## Servidor (Hetzner)

- IP `5.78.86.87`, Ubuntu 26.04 LTS, acesso `ssh root@5.78.86.87`
- **nginx** na frente de tudo (portas 80/443), HTTPS via certbot/Let's Encrypt (renovação automática). Config em `/etc/nginx/sites-enabled/`; snippet de proteção em `/etc/nginx/snippets/bp-auth.conf`
- Serviços internos (só escutam em 127.0.0.1):
  - **Oráculo**: gunicorn/Flask, porta 5000, systemd (serviço próprio)
  - **Serviço de conta**: gunicorn/Flask, porta 5001, systemd `bolapresa-auth`, pasta `/root/bolapresa-auth` — IMPORTANTE: gunicorn com `-w 1 -k gthread --threads 4` (um processo só; os rate limiters são em memória e não podem ter múltiplos processos)
- Stats servido como arquivos estáticos de `/var/www/bolapresa-stats` (clone do repo `pishenis/nba-team-profiles`)

## Autenticação (login único)

- Fluxo: assinante cria conta em `conta.bolapresa.com.br` (usuário + senha + e-mail do Apoia-se) → serviço confere na API do Apoia-se se o apoio do mês está pago → emite cookie JWT `bp_sessao` com `Domain=.bolapresa.com.br` (vale em todos os subdomínios), HttpOnly/Secure/SameSite=Lax, 7 dias
- nginx protege `stats.` / `oraculo.` / `jogos.` via `auth_request` → `GET /api/verificar` no serviço de conta (valida JWT **e** `ativo=1` no SQLite; nunca chama o Apoia-se — rápido)
- Sem login → redirect 302 para `conta.bolapresa.com.br/login?next=...`
- `revalidar.py` (cron diário) reconsulta o Apoia-se para todos os usuários; apoio atrasado corta acesso em até 24h
- Banco: SQLite `usuarios.db` em `/root/bolapresa-auth` (tabelas `usuarios` — com `is_admin` — e `perguntas`)
- Administração: `cd /root/bolapresa-auth && venv/bin/python3 admin.py <comando>` (usar o python do venv!) — comandos: `listar`, `revalidar`, `ativar`, `desativar`, `resetar-senha`, `promover`, `rebaixar`
- API do Apoia-se exige **chave + segredo** (headers `x-api-key` + `authorization: Bearer <segredo>`)

## Caixa de perguntas anônimas

- Formulário na homepage do site (Netlify) → `POST https://conta.bolapresa.com.br/api/pergunta` (CORS restrito às origens do site)
- Anti-bot em camadas: honeypot, tempo mínimo de 3s, rate limit 3/hora por hash de IP (só em memória), texto 10–8000 chars. Bots recebem sucesso falso
- **Anonimato:** nenhum IP/identificador é gravado — não adicionar colunas identificáveis à tabela `perguntas`
- Leitura: `conta.bolapresa.com.br/admin/perguntas` (login + `is_admin`)

## Bola Presa Stats — dados

- Repo `pishenis/nba-team-profiles` (GitHub). Fonte de dados: API BallDontLie (tier GOAT), chave `BDL_API_KEY` em `.env` (uma cópia no Mac para desenvolvimento, uma no clone do servidor para produção — nunca no Git; no servidor, `chmod 600`)
- **Coleta em produção: cron no servidor**, via `cron_stats.sh` (versionado no repo), rodando os scripts Python com `venv/bin/python3` direto em `/var/www/bolapresa-stats` (dado nasce onde é servido). Antes de coletar, faz `git pull --rebase --autostash` (resolvendo automaticamente conflitos em arquivos conhecidos gerados por coleta, sempre com a versão do GitHub); depois, `git add` + commit (só se o dado mudou) + push via deploy key SSH (`/root/.ssh/bp_stats_deploy`, configurada em `/root/.ssh/config` para `github.com`; remote do clone é `git@github.com:pishenis/nba-team-profiles.git`, com write access na Deploy Key do repo). `flock` em `/tmp/bp-stats.lock` (compartilhado com o `git pull` de 5 min) evita execuções simultâneas. Logs em `/var/log/bp-stats/<modo>.log`, com rotação simples (trunca acima de 1 MB)
  - Modos ativos no crontab: `diario` (`coletar_todos_jogos.py` + `corrigir_starter.py` + `generate_salaries.py` + `generate_advanced.py`, 11:00 UTC), `jogos` (só os dois primeiros coletores, a cada 15 min entre 0–4h UTC — horário de jogos), `free-agents` (`atualizar_free_agents.sh`, a cada 30 min)
  - Modo `playoffs` (`coletar_playoffs.py` + `coletar_head2head.py`) existe no `cron_stats.sh` mas **não está no crontab** — playoffs 2025-26 encerrados; reativar manualmente (`crontab -e`) só a partir de abril/2027
- GitHub Actions (`.github/workflows/atualizar.yml` e `atualizar_free_agents.yml`): **schedules ainda ATIVOS** durante a janela de validação de 48h do cron do servidor (rodam em paralelo, sem conflito real — o pior caso é um commit redundante, resolvido no próximo `git pull --rebase`). Pendência: desativar os `schedule:` (mantendo `workflow_dispatch:` como plano B manual) depois de confirmar 48h de cron limpo no servidor — ver Pendências
- `explorar_contratos_fa.py`, `coletar_agregados_fa.py`, `enriquecer_stats_free_agents.py`, `construir_comps_2025.py` e `aplicar_correcoes_manuais.py` carregavam o `.env` de um caminho fixo do Mac (`~/nba-team-profiles/.env`) — corrigido para o caminho do próprio script (`Path(__file__).resolve().parent`), funciona igual no Mac e no servidor
- `nba_player_ids.json` (fotos): testado em jul/2026 e **o Hetzner NÃO é bloqueado** pelo stats.nba.com (chamadas via `nba_api` responderam normalmente) — ainda gerado manualmente no Mac de Denis 1x por temporada e commitado, mas dá pra automatizar no servidor se algum dia valer a pena
- Desenvolvimento no Mac: pasta `~/nba-team-profiles`, publicação com `./publicar.sh` (resolve conflitos conhecidos automaticamente)

## Site principal (Netlify)

- Repo `pishenis/bolapresa-site` (Next.js 14, Pages Router). Push no GitHub = deploy automático
- Netlify Functions: `auth.js` (login antigo, a aposentar — ver Pendências) e `notion.js` (conteúdo do Quem Somos)
- Variáveis de ambiente no painel do Netlify

## Chaves e segredos — mapa

| Segredo | Onde vive |
|---|---|
| `BDL_API_KEY` | `~/nba-team-profiles/.env` (Mac) + `/var/www/bolapresa-stats/.env` (servidor, `chmod 600`) + Secrets do repo no GitHub (enquanto Actions com schedule existir) |
| `APOIASE_API_KEY` + `APOIASE_API_SECRET` | `/root/bolapresa-auth/.env` (servidor) + painel Netlify (login antigo) |
| `JWT_SECRET` | `/root/bolapresa-auth/.env` — NUNCA trocar sem planejar (invalida todas as sessões) |
| `ANTHROPIC_API_KEY` (Oráculo) | `.env` do Oráculo no servidor |
| Deploy key do Stats (push, write access) | `/root/.ssh/bp_stats_deploy` (+ `/root/.ssh/config`) do servidor + Deploy Keys do repo `nba-team-profiles` no GitHub |

Regra: cada `.env` vive ao lado do código que o usa e nunca vai para o Git.

## Pendências conhecidas

1. **Fechar acesso ao Oráculo por IP direto** (porta lateral sem login) — após confirmar que ninguém mais usa
2. **Desativar GitHub Pages do Stats** (versão sem proteção do mesmo conteúdo) — após validar o subdomínio
3. **Migrar login do site Netlify** (`auth.js`/`useAuth`) para o serviço central — aposenta o login duplicado
4. **Bingo novo** em `jogos.bolapresa.com.br` (hoje: placeholder "Em breve")
5. `.gitignore` do `bolapresa-site` (commitado, conferir push)
6. **Desativar os `schedule:` do GitHub Actions** (`atualizar.yml` e `atualizar_free_agents.yml`, mantendo `workflow_dispatch:`) — só depois de confirmar 48h de cron rodando limpo no servidor (ver logs em `/var/log/bp-stats/`)
7. **Reativar coleta de playoffs** (`cron_stats.sh playoffs` no crontab) a partir de abril/2027, quando a temporada 2026-27 entrar em playoffs
8. `contratos_raw.json` e `contratos_agregados_raw.json` continuam versionados no Git apesar de estarem no `.gitignore` (foram commitados antes da regra existir) — o `git add -A` dos modos `diario`/`jogos` pode ocasionalmente incluir suas mudanças (re-coleta de contratos rodada por `free-agents`) num commit de outro modo; inofensivo, mas deixa o histórico um pouco confuso. Rodar `git rm --cached` neles resolveria, se algum dia incomodar
