PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razao_social TEXT NOT NULL,
    nome_fantasia TEXT,
    cnpj TEXT UNIQUE NOT NULL,
    email_contato TEXT,
    telefone TEXT,
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresas(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL DEFAULT 'cliente' CHECK (papel IN ('admin', 'cliente')),
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresas(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS centros_custo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS formas_pagamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS lancamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    centro_custo_id INTEGER REFERENCES centros_custo(id),
    forma_pagamento_id INTEGER REFERENCES formas_pagamento(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    descricao TEXT NOT NULL,
    valor REAL NOT NULL CHECK (valor > 0),
    data_lancamento TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmado' CHECK (status IN ('pendente', 'confirmado', 'cancelado')),
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS lancamentos_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lancamento_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    acao TEXT NOT NULL CHECK (acao IN ('criado', 'editado', 'cancelado')),
    dados_anteriores TEXT,
    dados_novos TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lancamentos_empresa_data ON lancamentos(empresa_id, data_lancamento);
CREATE INDEX IF NOT EXISTS idx_lancamentos_categoria ON lancamentos(categoria_id);

CREATE VIEW IF NOT EXISTS vw_fluxo_caixa_mensal AS
SELECT empresa_id, strftime('%Y-%m', data_lancamento) AS mes,
       SUM(CASE WHEN tipo = 'receita' THEN valor ELSE 0 END) AS total_receitas,
       SUM(CASE WHEN tipo = 'despesa' THEN valor ELSE 0 END) AS total_despesas,
       SUM(CASE WHEN tipo = 'receita' THEN valor ELSE -valor END) AS saldo
FROM lancamentos WHERE status = 'confirmado'
GROUP BY empresa_id, strftime('%Y-%m', data_lancamento);

CREATE VIEW IF NOT EXISTS vw_totais_por_categoria AS
SELECT l.empresa_id, c.nome AS categoria, c.tipo,
       strftime('%Y-%m', l.data_lancamento) AS mes, SUM(l.valor) AS total
FROM lancamentos l JOIN categorias c ON c.id = l.categoria_id
WHERE l.status = 'confirmado'
GROUP BY l.empresa_id, c.nome, c.tipo, strftime('%Y-%m', l.data_lancamento);

INSERT OR IGNORE INTO formas_pagamento(nome) VALUES
    ('Dinheiro'), ('Pix'), ('Débito'), ('Crédito'), ('Boleto'), ('Cartão'), ('Transferência');

INSERT INTO categorias(empresa_id, nome, tipo)
SELECT NULL, 'Vendas', 'receita'
WHERE NOT EXISTS (SELECT 1 FROM categorias WHERE empresa_id IS NULL AND nome = 'Vendas' AND tipo = 'receita');

INSERT INTO categorias(empresa_id, nome, tipo)
SELECT NULL, 'Fornecedores', 'despesa'
WHERE NOT EXISTS (SELECT 1 FROM categorias WHERE empresa_id IS NULL AND nome = 'Fornecedores' AND tipo = 'despesa');
