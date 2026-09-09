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
