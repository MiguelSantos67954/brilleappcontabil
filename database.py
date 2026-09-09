"""
Conexão e inicialização do banco de dados SQLite.
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sistema_contabil.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
MIGRATIONS_PATH = os.path.join(BASE_DIR, "migrations.sql")


def get_conn():
    """Abre uma conexão com o banco, retornando linhas como dicionários."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Cria o banco a partir do schema.sql, caso ainda não exista."""
    banco_novo = not os.path.exists(DB_PATH)
    if banco_novo:
        conn = get_conn()
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print(f"Banco de dados criado em: {DB_PATH}")

    migrar_db()


def migrar_db():
    """
    Aplica alterações novas de estrutura (tabelas/colunas criadas em versões
    mais recentes do sistema) sem apagar os dados já existentes no banco.
    Seguro rodar toda vez que o servidor sobe.
    """
    conn = get_conn()

    if os.path.exists(MIGRATIONS_PATH):
        with open(MIGRATIONS_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())

    _adicionar_colunas_se_faltando(conn, "produtos_servicos", {
        "codigo": "TEXT",
        "unidade": "TEXT NOT NULL DEFAULT 'un'",
        "estoque_atual": "REAL NOT NULL DEFAULT 0",
    })

    # índice único de código só é criado depois que a coluna já existe garantidamente
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_produtos_codigo_unico
        ON produtos_servicos(empresa_id, codigo) WHERE codigo IS NOT NULL AND codigo != ''
    """)

    conn.commit()
    conn.close()


def _adicionar_colunas_se_faltando(conn, tabela, colunas):
    """Adiciona colunas a uma tabela existente, caso ainda não existam (idempotente)."""
    existentes = {linha["name"] for linha in conn.execute(f"PRAGMA table_info({tabela})")}
    for nome, definicao in colunas.items():
        if nome not in existentes:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")
