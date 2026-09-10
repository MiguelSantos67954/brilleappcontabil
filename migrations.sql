-- ============================================================
-- MIGRAÇÃO: Produtos/Serviços e Vendas
-- Roda automaticamente toda vez que o servidor sobe (idempotente,
-- não apaga nem altera dados já existentes).
-- ============================================================

-- ------------------------------------------------------------
-- PRODUTOS E SERVIÇOS (catálogo de cada empresa cliente)
-- categoria_id: categoria de RECEITA usada no lançamento automático
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS produtos_servicos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id      INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('produto', 'servico')),
    nome            TEXT NOT NULL,
    descricao       TEXT,
    preco           REAL NOT NULL CHECK (preco >= 0),
    categoria_id    INTEGER REFERENCES categorias(id),
    ativo           INTEGER NOT NULL DEFAULT 1,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- VENDAS / PRESTAÇÕES DE SERVIÇO
-- Cada venda gera automaticamente um lançamento de receita
-- (lancamento_id aponta para o lançamento criado)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id          INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    produto_servico_id  INTEGER NOT NULL REFERENCES produtos_servicos(id),
    quantidade          REAL NOT NULL DEFAULT 1 CHECK (quantidade > 0),
    valor_unitario       REAL NOT NULL CHECK (valor_unitario >= 0),
    valor_total          REAL NOT NULL CHECK (valor_total >= 0),
    cliente_nome        TEXT,
    forma_pagamento_id  INTEGER REFERENCES formas_pagamento(id),
    data_venda          TEXT NOT NULL,
    lancamento_id       INTEGER REFERENCES lancamentos(id),
    status              TEXT NOT NULL DEFAULT 'confirmada' CHECK (status IN ('confirmada', 'cancelada')),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_produtos_servicos_empresa ON produtos_servicos(empresa_id);
CREATE INDEX IF NOT EXISTS idx_vendas_empresa_data ON vendas(empresa_id, data_venda);
CREATE INDEX IF NOT EXISTS idx_vendas_produto ON vendas(produto_servico_id);

-- ------------------------------------------------------------
-- ENTRADAS DE ESTOQUE (compra de mercadorias)
-- Cada entrada gera automaticamente um lançamento de DESPESA
-- e soma a quantidade ao estoque_atual do item.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entradas_estoque (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id          INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    produto_servico_id  INTEGER NOT NULL REFERENCES produtos_servicos(id),
    quantidade          REAL NOT NULL CHECK (quantidade > 0),
    valor_unitario       REAL NOT NULL CHECK (valor_unitario >= 0),
    valor_total          REAL NOT NULL CHECK (valor_total >= 0),
    fornecedor          TEXT,
    categoria_id        INTEGER REFERENCES categorias(id),
    data_entrada         TEXT NOT NULL,
    lancamento_id       INTEGER REFERENCES lancamentos(id),
    status              TEXT NOT NULL DEFAULT 'confirmada' CHECK (status IN ('confirmada', 'cancelada')),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entradas_estoque_empresa_data ON entradas_estoque(empresa_id, data_entrada);
CREATE INDEX IF NOT EXISTS idx_entradas_estoque_produto ON entradas_estoque(produto_servico_id);

-- ------------------------------------------------------------
-- MAQUININHAS E TAXAS DE PAGAMENTO
-- As taxas usadas em cada venda também ficam gravadas na própria venda,
-- preservando o histórico caso o cadastro seja alterado futuramente.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS maquininhas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id      INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    taxa_debito     REAL NOT NULL DEFAULT 0 CHECK (taxa_debito >= 0),
    taxa_credito    REAL NOT NULL DEFAULT 0 CHECK (taxa_credito >= 0),
    taxa_pix        REAL NOT NULL DEFAULT 0 CHECK (taxa_pix >= 0),
    ativo           INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_maquininhas_empresa ON maquininhas(empresa_id);

CREATE TABLE IF NOT EXISTS taxas_maquininha_credito (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    maquininha_id   INTEGER NOT NULL REFERENCES maquininhas(id) ON DELETE CASCADE,
    parcelas        INTEGER NOT NULL CHECK (parcelas BETWEEN 1 AND 24),
    taxa            REAL NOT NULL DEFAULT 0 CHECK (taxa >= 0 AND taxa <= 100),
    UNIQUE (maquininha_id, parcelas)
);

INSERT OR IGNORE INTO taxas_maquininha_credito(maquininha_id, parcelas, taxa)
SELECT id, 1, taxa_credito FROM maquininhas;

INSERT INTO categorias(empresa_id, nome, tipo)
SELECT NULL, 'Taxas de maquininha', 'despesa'
WHERE NOT EXISTS (
    SELECT 1 FROM categorias
    WHERE empresa_id IS NULL AND nome = 'Taxas de maquininha' AND tipo = 'despesa'
);

INSERT OR IGNORE INTO formas_pagamento(nome) VALUES
    ('Dinheiro'), ('Pix'), ('Débito'), ('Crédito');
