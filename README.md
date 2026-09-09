# Sistema de Lançamentos Financeiros — Consultoria Contábil

API para clientes de consultoria contábil lançarem receitas/despesas e
gerarem relatórios (fluxo de caixa, DRE simplificado). Banco de dados
SQLite (arquivo local, sem instalação de servidor).

## Como rodar

```bash
pip install -r requirements.txt --break-system-packages
python app.py
```

O servidor sobe em `http://localhost:5000`. Na primeira execução, o
arquivo `sistema_contabil.db` é criado automaticamente a partir do
`schema.sql`.

## Criar o primeiro usuário admin

O cadastro de empresas exige um usuário admin, mas não existe rota
pública para criar o primeiro admin (por segurança). Rode uma vez:

```bash
python -c "
from database import init_db, get_conn
from werkzeug.security import generate_password_hash
init_db()
conn = get_conn()
conn.execute(
    \"INSERT INTO usuarios (empresa_id, nome, email, senha_hash, papel) \"
    \"VALUES (NULL, 'Admin', 'admin@suaconsultoria.com', ?, 'admin')\",
    (generate_password_hash('TROQUE_ESTA_SENHA'),)
)
conn.commit()
conn.close()
print('Admin criado')
"
```

## Fluxo de uso

1. **Login do admin**: `POST /api/auth/login` → recebe um token
2. **Cadastrar empresa cliente**: `POST /api/empresas`
3. **Criar usuário de login para o cliente**: `POST /api/empresas/<id>/usuarios`
4. **Cliente faz login**: `POST /api/auth/login` → recebe seu próprio token
5. **Cliente lança receitas/despesas**: `POST /api/lancamentos`
6. **Cliente consulta relatórios**: `GET /api/relatorios/fluxo-caixa`, `GET /api/relatorios/dre`

Todas as rotas (exceto login) exigem o header:
`Authorization: Bearer <token>`

## Rotas principais

| Método | Rota | Descrição |
|---|---|---|
| POST | /api/auth/login | Login (retorna token) |
| GET/POST | /api/empresas | Listar/criar empresas (admin) |
| POST | /api/empresas/\<id\>/usuarios | Criar usuário cliente (admin) |
| GET/POST | /api/categorias | Listar/criar categorias |
| GET/POST | /api/lancamentos | Listar/criar lançamentos |
| PUT/DELETE | /api/lancamentos/\<id\> | Editar / cancelar lançamento |
| GET | /api/relatorios/fluxo-caixa | Fluxo de caixa mensal |
| GET | /api/relatorios/dre | DRE simplificado por categoria |
| GET | /api/relatorios/extrato | Extrato com filtros (data, tipo, categoria) |

## Frontend

Está em `index.html` — um arquivo único (HTML+CSS/JS puro,
sem build). Para usar:

1. Suba a API (`python app.py`)
2. Abra `index.html` direto no navegador (duplo clique)
3. Na tela de login, clique em "trocar endereço" se a API não estiver
   em `http://localhost:5000`
4. Faça login com o usuário admin para cadastrar empresas e criar
   acessos de clientes; os clientes fazem login com o e-mail/senha
   criados para lançar receitas/despesas e ver os relatórios

## Segurança — antes de usar de verdade

- Defina `APP_CONTABIL_SECRET_KEY` com uma chave longa e aleatória
- Configure CORS se o frontend rodar em outro domínio (`flask-cors`)
- Use HTTPS em produção

## Publicação na Vercel

A interface e a API são servidas pelo mesmo domínio. Como as funções da
Vercel não mantêm arquivos SQLite locais, conecte um banco Turso pelo
Marketplace da Vercel e configure estas variáveis no projeto:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `APP_CONTABIL_SECRET_KEY` (uma chave longa, aleatória e permanente)

Depois de salvar as variáveis, faça um novo deploy. A estrutura do banco é
criada automaticamente na primeira inicialização.
