"""Conexão SQLite local ou Turso remoto para ambientes serverless."""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sistema_contabil.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
MIGRATIONS_PATH = os.path.join(BASE_DIR, "migrations.sql")


class _LinhaCompativel:
    """Linha libSQL compatível com sqlite3.Row (índice, chave e dict())."""
    def __init__(self, colunas, valores):
        self._colunas = tuple(colunas)
        self._valores = tuple(valores)
        self._por_nome = dict(zip(self._colunas, self._valores))

    def keys(self):
        return self._colunas

    def __getitem__(self, chave):
        if isinstance(chave, int):
            return self._valores[chave]
        return self._por_nome[chave]

    def __iter__(self):
        return iter(self._valores)

    def __len__(self):
        return len(self._valores)


class _CursorCompativel:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def _converter(self, linha):
        if linha is None:
            return None
        descricao = self._cursor.description or ()
        colunas = [coluna[0] for coluna in descricao]
        return _LinhaCompativel(colunas, linha)

    def fetchone(self):
        return self._converter(self._cursor.fetchone())

    def fetchall(self):
        return [self._converter(linha) for linha in self._cursor.fetchall()]

    def __iter__(self):
        for linha in self._cursor:
            yield self._converter(linha)


class _ConexaoCompativel:
    def __init__(self, conexao):
        self._conexao = conexao

    def execute(self, sql, params=()):
        return _CursorCompativel(self._conexao.execute(sql, params))

    def executescript(self, sql):
        return self._conexao.executescript(sql)

    def commit(self):
        return self._conexao.commit()

    def rollback(self):
        return self._conexao.rollback()

    def close(self):
        return self._conexao.close()


def get_conn():
    """Abre uma conexão com o banco, retornando linhas como dicionários."""
    turso_url = os.environ.get("TURSO_DATABASE_URL")
    if turso_url:
        import libsql
        conn = libsql.connect(
            database=turso_url,
            auth_token=os.environ.get("TURSO_AUTH_TOKEN", ""),
        )
        conn = _ConexaoCompativel(conn)
    else:
        if os.environ.get("VERCEL"):
            raise RuntimeError(
                "Banco persistente não configurado. Defina TURSO_DATABASE_URL "
                "e TURSO_AUTH_TOKEN nas variáveis da Vercel."
            )
        conn = sqlite3.connect(DB_PATH)
    if not turso_url:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Cria o banco a partir do schema.sql, caso ainda não exista."""
    banco_novo = bool(os.environ.get("TURSO_DATABASE_URL")) or not os.path.exists(DB_PATH)
    if banco_novo:
        conn = get_conn()
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print("Estrutura do banco verificada com sucesso")

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
