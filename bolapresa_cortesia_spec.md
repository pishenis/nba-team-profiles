# Spec — Contas Cortesia (acesso sem Apoia-se)

**Serviço:** `bolapresa-auth` (`/root/bolapresa-auth`, Flask + SQLite, porta 5001, systemd `bolapresa-auth`)
**Executor:** Claude Code no servidor, de forma autônoma
**Leia antes:** `ARQUITETURA.md` (seções Autenticação e Painel de administração de usuários) e `bolapresa_admin_painel_spec.md`, se estiverem nesta pasta

---

## 1. Contexto e objetivo

Hoje todo acesso ao ecossistema (Stats, Jogos, Oráculo, Bingo) depende de apoio pago no Apoia-se, em três pontos:

1. **Cadastro:** confere o e-mail na API do Apoia-se.
2. **`/login`:** sempre reconsulta o Apoia-se e sobrescreve o `ativo`.
3. **`revalidar.py`:** cron diário que corta quem não tem apoio em dia.

Precisamos liberar pessoas que **não são assinantes**: o sócio Danilo (permanente) e convidados de beta dos jogos (temporários). Elas devem ter **conta própria**, com usuário próprio, porque nos jogos cada pessoa precisa aparecer no ranking com o próprio nome.

**Solução:** um novo tipo de conta, a **cortesia**. Para contas cortesia, o sistema não consulta o Apoia-se em nenhum dos três pontos. O acesso passa a depender só do campo `ativo`, controlado pelo admin.

---

## 2. Regras de negócio

- **R1.** Uma conta cortesia tem `cortesia = 1`. Opcionalmente, tem uma data de validade em `cortesia_ate` (data `AAAA-MM-DD`, inclusiva, fuso `America/Sao_Paulo`). Se `cortesia_ate` for `NULL`, a cortesia é permanente.
- **R2.** Uma cortesia está **vigente** quando `cortesia = 1` e (`cortesia_ate` é `NULL` ou hoje ≤ `cortesia_ate`).
- **R3.** Para conta com cortesia vigente:
  - o `/login` **não** consulta o Apoia-se. Entra se a senha estiver correta e `ativo = 1`, e emite o cookie normalmente;
  - o `revalidar.py` **pula** a conta.
- **R4.** Para conta com cortesia vigente, o `ativo` é a única fonte de verdade. "Desativar" no painel **passa a ser definitivo**: o próximo login não desfaz.
- **R5. Vencimento:** quando `cortesia_ate` passa, a conta volta à regra normal. O `revalidar.py` (próxima execução) e o `/login` (próxima tentativa) consultam o Apoia-se como para qualquer usuário. Se a pessoa virou assinante, continua com acesso. Se não, é desativada como um assinante inadimplente. O `revalidar.py` também zera `cortesia` (com `cortesia_ate` preservado para histórico) e grava isso no `admin_log`.
- **R6.** `/api/verificar` **não muda**. Ele já valida o JWT e `ativo = 1` sem chamar o Apoia-se. Confirmar isso no código e não alterar.
- **R7.** A conta cortesia é criada **só pelo admin** (painel ou CLI). Não existe autocadastro de cortesia.
- **R8.** A criação gera uma senha temporária, exibida uma única vez, com `deve_trocar_senha = 1`. Usar o mesmo mecanismo do reset de senha que já existe. A senha nunca é gravada em log.
- **R9.** O e-mail é exigido se o schema atual exigir (NOT NULL ou UNIQUE). Nesse caso, usar o e-mail real da pessoa. Se o schema permitir `NULL`, o e-mail é opcional. Não inventar e-mail falso.
- **R10.** Toda ação de cortesia (criar, conceder, revogar, alterar validade, vencimento automático) vai para o `admin_log`, no padrão existente.
- **R11.** Uma conta comum existente pode virar cortesia, e vice-versa. Revogar a cortesia não desativa a conta na hora: ela volta à regra normal (R5).

---

## 3. Fases

### Fase 0 — Reconhecimento (não alterar nada)
1. Ler `app.py` (ou equivalente), `admin.py`, `revalidar.py` e o schema de `usuarios.db` (`sqlite3 usuarios.db ".schema usuarios"`).
2. Mapear **todos** os pontos que consultam o Apoia-se: cadastro, login, revalidação, o botão "revalidar" do painel e qualquer outro que aparecer.
3. Confirmar se `is_admin` hoje pula ou não a checagem do Apoia-se. Isso é só informativo: **não mudar** esse comportamento nesta spec.
4. Conferir se o Bingo (`/opt/bingo`) faz alguma checagem própria de assinatura além do JWT. Se fizer, registrar no relatório final e não alterar.
5. Escrever um resumo curto do que encontrou antes de seguir.

### Fase 1 — Backup e migração
1. Backup: `cp usuarios.db usuarios_backup_AAAAMMDD_HHMMSS.db`.
2. Migração idempotente, com checagem via `PRAGMA table_info` antes de cada `ALTER`:
   - `ALTER TABLE usuarios ADD COLUMN cortesia INTEGER NOT NULL DEFAULT 0`
   - `ALTER TABLE usuarios ADD COLUMN cortesia_ate TEXT` (nullable)
3. Uma função central, `cortesia_vigente(usuario) -> bool`, implementando R2. **Todos** os pontos de checagem usam essa função; nada de reimplementar a regra em cada lugar.

### Fase 2 — Login e revalidação
1. `/login`: depois de validar a senha, se `cortesia_vigente`, pular a consulta ao Apoia-se e seguir com `ativo` atual (R3, R4). Caso contrário, manter o fluxo exatamente como está.
2. `revalidar.py`: pular cortesias vigentes. Para cortesias vencidas, aplicar R5. Lembrar do `load_dotenv` com caminho explícito, porque roda em cron.
3. Botão "revalidar" do painel: para cortesia vigente, não consultar o Apoia-se; mostrar a mensagem "Conta cortesia — não depende do Apoia-se".

### Fase 3 — CLI (`admin.py`)
Novos comandos, no mesmo estilo dos existentes:
- `criar-cortesia <usuario> --email <email> [--ate AAAA-MM-DD]` → cria a conta ativa, com cortesia, `deve_trocar_senha = 1`, e imprime a senha temporária uma vez
- `cortesia <usuario> [--ate AAAA-MM-DD]` → transforma uma conta existente em cortesia (ou altera a validade) e garante `ativo = 1`
- `remover-cortesia <usuario>` → R11
- `listar` → passa a mostrar a coluna cortesia (e a validade, se houver)

### Fase 4 — Painel `/admin/usuarios`
- Selo "cortesia" na lista (com "até DD/MM/AAAA" se houver validade); cortesia vencida aparece como "cortesia vencida"
- Filtro "só cortesias"
- Formulário "Criar conta cortesia": usuário, e-mail e validade opcional. Mostra a senha temporária uma única vez, no mesmo padrão do reset de senha
- Na linha de cada usuário: "Conceder cortesia", "Remover cortesia" e "Alterar validade"
- Seguir o padrão existente: decorator `admin_requerido`, CSRF em todos os POSTs, visual do painel atual

### Fase 5 — Conta do Danilo
Perguntar a Denis o usuário e o e-mail desejados, a menos que já tenham sido informados na sessão. Criar com `criar-cortesia` **sem validade** e entregar a senha temporária a Denis.

### Fase 6 — Deploy
`systemctl restart bolapresa-auth` e `systemctl status bolapresa-auth`. Manter o gunicorn com `-w 1 -k gthread --threads 4` (regra do ecossistema; não mudar).

---

## 4. Critérios de aceite

1. Uma conta cortesia de teste (e-mail sem apoio no Apoia-se) consegue: logar, trocar a senha temporária, acessar `stats.`, `jogos.` e `oraculo.`.
2. **Teste de regressão crítico:** uma conta **comum** sem apoio pago continua **barrada** no login. O bypass não pode vazar para contas não-cortesia.
3. Uma conta comum com apoio pago continua funcionando como antes.
4. Cortesia desativada no painel continua desativada após nova tentativa de login (R4).
5. Rodar `revalidar.py` manualmente não altera cortesias vigentes.
6. Cortesia com `cortesia_ate` no passado: `revalidar.py` aplica R5 e grava no `admin_log`.
7. A migração é idempotente: rodar duas vezes não dá erro.
8. `admin_log` registra todas as ações de cortesia, e nenhuma senha aparece em log nenhum.
9. Apagar as contas de teste ao final, a menos que Denis peça para manter.

---

## 5. Fora de escopo

- Login do site Netlify (`auth.js`), que é pendência separada
- Mudar o comportamento de `is_admin` em relação ao Apoia-se
- "Banimento" independente do pagamento para contas comuns (funcionalidade diferente, ainda não especificada)
- Alterações no Bingo, no Oráculo ou nos jogos
- Avisos por e-mail de vencimento de cortesia

---

## 6. Ao terminar

1. Relatório curto para Denis: o que mudou, onde, resultado de cada critério de aceite e o que a Fase 0 encontrou (especialmente `is_admin` e Bingo).
2. Texto pronto para Denis colar no `ARQUITETURA.md`, seção "Autenticação" (ou "Painel de administração"), descrevendo as contas cortesia e as regras R3, R4 e R5. **Não** editar o `ARQUITETURA.md` daqui, porque ele vive no repo do Stats, no Mac.
