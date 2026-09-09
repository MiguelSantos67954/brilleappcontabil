"""
API do sistema de lançamentos financeiros para clientes de consultoria contábil.

Rodar com:  python app.py
Servidor sobe em: http://localhost:5000
"""
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
import os
from datetime import datetime
from datetime import date
from calendar import monthrange
from database import get_conn, init_db
from auth import (
    gerar_token, login_required, admin_required, empresa_permitida,
    generate_password_hash, check_password_hash,
)

app = Flask(__name__)
CORS(app, origins=[
    "null",  # index.html aberto diretamente como arquivo local
    r"^http://localhost(?::\d+)?$",
    r"^http://127\.0\.0\.1(?::\d+)?$",
])


@app.get("/")
@app.get("/index.html")
def frontend():
    return send_from_directory(app.root_path, "index.html")


@app.get("/Brille.png")
def logo_png():
    return send_from_directory(app.root_path, "Brille.png")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.root_path, "Brille.ico")


def _json():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return None
    return dados


def _data_iso(valor, campo):
    try:
        datetime.strptime(str(valor), "%Y-%m-%d")
        return None
    except (TypeError, ValueError):
        return jsonify({"erro": f"{campo} deve estar no formato AAAA-MM-DD"}), 400


def _referencia_da_empresa(conn, tabela, registro_id, empresa_id, tipo=None):
    if registro_id is None:
        return True
    query = f"SELECT 1 FROM {tabela} WHERE id = ? AND (empresa_id IS NULL OR empresa_id = ?)"
    params = [registro_id, empresa_id]
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)
    return conn.execute(query, params).fetchone() is not None


def mesAtualISO_backend():
    """Retorna o mês atual no formato 'AAAA-MM', usado como padrão dos relatórios sem filtro."""
    hoje = date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def _ultimo_dia_do_mes(data_inicio_str):
    """A partir de 'AAAA-MM-DD' ou 'AAAA-MM', devolve o último dia daquele mês em 'AAAA-MM-DD'."""
    partes = data_inicio_str.split("-")
    ano, mes = int(partes[0]), int(partes[1])
    ultimo_dia = monthrange(ano, mes)[1]
    return f"{ano:04d}-{mes:02d}-{ultimo_dia:02d}"


# ============================================================
# AUTENTICAÇÃO
# ============================================================

@app.post("/api/auth/login")
def login():
    dados = _json()
    if dados is None:
        return jsonify({"erro": "Corpo JSON inválido"}), 400
    email = dados.get("email", "").strip().lower()
    senha = dados.get("senha", "")

    conn = get_conn()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE email = ? AND ativo = 1", (email,)
    ).fetchone()
    conn.close()

    if not usuario or not check_password_hash(usuario["senha_hash"], senha):
        return jsonify({"erro": "E-mail ou senha inválidos"}), 401

    token = gerar_token(usuario)
    return jsonify({
        "token": token,
        "usuario": {
            "id": usuario["id"], "nome": usuario["nome"], "email": usuario["email"],
            "papel": usuario["papel"], "empresa_id": usuario["empresa_id"],
        },
    })


@app.get("/api/auth/me")
@login_required
def me():
    conn = get_conn()
    usuario = conn.execute(
        "SELECT id, nome, email, papel, empresa_id FROM usuarios WHERE id = ?", (g.usuario_id,)
    ).fetchone()
    empresa = None
    if usuario["empresa_id"]:
        empresa = conn.execute(
            "SELECT id, razao_social, nome_fantasia FROM empresas WHERE id = ?",
            (usuario["empresa_id"],),
        ).fetchone()
    conn.close()
    return jsonify({
        "usuario": dict(usuario),
        "empresa": dict(empresa) if empresa else None,
    })


# ============================================================
# EMPRESAS  (somente admin cadastra/gerencia)
# ============================================================

@app.get("/api/empresas")
@login_required
@admin_required
def listar_empresas():
    conn = get_conn()
    linhas = conn.execute("SELECT * FROM empresas ORDER BY razao_social").fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.post("/api/empresas")
@login_required
@admin_required
def criar_empresa():
    d = request.get_json(force=True)
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO empresas (razao_social, nome_fantasia, cnpj, email_contato, telefone)
           VALUES (?, ?, ?, ?, ?)""",
        (d["razao_social"], d.get("nome_fantasia"), d["cnpj"],
         d.get("email_contato"), d.get("telefone")),
    )
    conn.commit()
    empresa_id = cur.lastrowid
    conn.close()
    return jsonify({"id": empresa_id}), 201


@app.post("/api/empresas/<int:empresa_id>/usuarios")
@login_required
@admin_required
def criar_usuario_cliente(empresa_id):
    """Cria o usuário de login para um cliente de uma empresa específica."""
    d = request.get_json(force=True)
    email = d["email"].strip().lower()
    conn = get_conn()

    existe = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
    if existe:
        conn.close()
        return jsonify({"erro": "Este e-mail já está em uso por outro usuário"}), 400

    senha_hash = generate_password_hash(d["senha"])
    cur = conn.execute(
        """INSERT INTO usuarios (empresa_id, nome, email, senha_hash, papel)
           VALUES (?, ?, ?, ?, 'cliente')""",
        (empresa_id, d["nome"], email, senha_hash),
    )
    conn.commit()
    usuario_id = cur.lastrowid
    conn.close()
    return jsonify({"id": usuario_id}), 201


@app.get("/api/empresas/<int:empresa_id>/usuarios")
@login_required
@admin_required
def listar_usuarios_empresa(empresa_id):
    """Lista os usuários (logins) cadastrados para uma empresa cliente."""
    conn = get_conn()
    linhas = conn.execute(
        "SELECT id, nome, email, papel, ativo, criado_em FROM usuarios WHERE empresa_id = ? ORDER BY nome",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.put("/api/usuarios/<int:usuario_id>")
@login_required
@admin_required
def editar_usuario(usuario_id):
    """Altera nome, e-mail e/ou senha de um usuário cliente."""
    conn = get_conn()
    atual = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({"erro": "Usuário não encontrado"}), 404

    d = request.get_json(force=True)
    campos = {}
    if "nome" in d:
        campos["nome"] = d["nome"]
    if "email" in d:
        novo_email = d["email"].strip().lower()
        existe = conn.execute(
            "SELECT id FROM usuarios WHERE email = ? AND id != ?", (novo_email, usuario_id)
        ).fetchone()
        if existe:
            conn.close()
            return jsonify({"erro": "Este e-mail já está em uso por outro usuário"}), 400
        campos["email"] = novo_email
    if "senha" in d and d["senha"]:
        campos["senha_hash"] = generate_password_hash(d["senha"])

    if not campos:
        conn.close()
        return jsonify({"erro": "Nenhum campo para atualizar"}), 400

    set_clause = ", ".join(f"{c} = ?" for c in campos)
    valores = list(campos.values()) + [usuario_id]
    conn.execute(f"UPDATE usuarios SET {set_clause} WHERE id = ?", valores)
    conn.commit()
    conn.close()
    return jsonify({"status": "atualizado"})


@app.put("/api/usuarios/<int:usuario_id>/status")
@login_required
@admin_required
def alterar_status_usuario(usuario_id):
    """Ativa ou desativa o login de um cliente (bloqueia/libera o acesso)."""
    d = request.get_json(force=True)
    ativo = 1 if d.get("ativo") else 0
    conn = get_conn()
    resultado = conn.execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (ativo, usuario_id))
    conn.commit()
    encontrado = resultado.rowcount > 0
    conn.close()
    if not encontrado:
        return jsonify({"erro": "Usuário não encontrado"}), 404
    return jsonify({"status": "ativo" if ativo else "desativado"})


# ============================================================
# CATEGORIAS
# ============================================================

@app.get("/api/categorias")
@login_required
def listar_categorias():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    conn = get_conn()
    linhas = conn.execute(
        "SELECT * FROM categorias WHERE empresa_id IS NULL OR empresa_id = ? ORDER BY tipo, nome",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.post("/api/categorias")
@login_required
def criar_categoria():
    """Cliente ou admin pode criar categoria própria para a empresa."""
    d = request.get_json(force=True)
    empresa_id = d.get("empresa_id") or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO categorias (empresa_id, nome, tipo) VALUES (?, ?, ?)",
        (empresa_id, d["nome"], d["tipo"]),
    )
    conn.commit()
    categoria_id = cur.lastrowid
    conn.close()
    return jsonify({"id": categoria_id}), 201


# ============================================================
# LANÇAMENTOS
# ============================================================

@app.get("/api/lancamentos")
@login_required
def listar_lancamentos():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    filtros = ["l.empresa_id = ?"]
    params = [empresa_id]

    if data_inicio := request.args.get("data_inicio"):
        filtros.append("l.data_lancamento >= ?")
        params.append(data_inicio)
    if data_fim := request.args.get("data_fim"):
        filtros.append("l.data_lancamento <= ?")
        params.append(data_fim)
    if tipo := request.args.get("tipo"):
        filtros.append("l.tipo = ?")
        params.append(tipo)
    if categoria_id := request.args.get("categoria_id", type=int):
        filtros.append("l.categoria_id = ?")
        params.append(categoria_id)

    where = " AND ".join(filtros)
    conn = get_conn()
    linhas = conn.execute(
        f"""SELECT l.*, c.nome AS categoria_nome, fp.nome AS forma_pagamento_nome
            FROM lancamentos l
            JOIN categorias c ON c.id = l.categoria_id
            LEFT JOIN formas_pagamento fp ON fp.id = l.forma_pagamento_id
            WHERE {where}
            ORDER BY l.data_lancamento DESC, l.id DESC""",
        params,
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.post("/api/lancamentos")
@login_required
def criar_lancamento():
    d = _json()
    if d is None:
        return jsonify({"erro": "Corpo JSON inválido"}), 400
    empresa_id = d.get("empresa_id") or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    campos_obrigatorios = ["categoria_id", "tipo", "descricao", "valor", "data_lancamento"]
    faltando = [c for c in campos_obrigatorios if c not in d]
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    if d["tipo"] not in ("receita", "despesa"):
        return jsonify({"erro": "tipo deve ser 'receita' ou 'despesa'"}), 400
    try:
        valor = float(d["valor"])
    except (TypeError, ValueError, OverflowError):
        return jsonify({"erro": "valor deve ser numérico"}), 400
    if valor <= 0:
        return jsonify({"erro": "valor deve ser maior que zero"}), 400
    if erro := _data_iso(d["data_lancamento"], "data_lancamento"):
        return erro

    conn = get_conn()
    if not _referencia_da_empresa(conn, "categorias", d["categoria_id"], empresa_id, d["tipo"]):
        conn.close()
        return jsonify({"erro": "Categoria inválida para esta empresa e tipo"}), 400
    if not _referencia_da_empresa(conn, "centros_custo", d.get("centro_custo_id"), empresa_id):
        conn.close()
        return jsonify({"erro": "Centro de custo inválido para esta empresa"}), 400
    cur = conn.execute(
        """INSERT INTO lancamentos
           (empresa_id, usuario_id, categoria_id, centro_custo_id, forma_pagamento_id,
            tipo, descricao, valor, data_lancamento, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (empresa_id, g.usuario_id, d["categoria_id"], d.get("centro_custo_id"),
         d.get("forma_pagamento_id"), d["tipo"], d["descricao"], valor,
         d["data_lancamento"], d.get("status", "confirmado")),
    )
    lancamento_id = cur.lastrowid
    conn.execute(
        """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao, dados_novos)
           VALUES (?, ?, 'criado', ?)""",
        (lancamento_id, g.usuario_id, str(d)),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": lancamento_id}), 201


@app.put("/api/lancamentos/<int:lancamento_id>")
@login_required
def editar_lancamento(lancamento_id):
    conn = get_conn()
    atual = conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lancamento_id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({"erro": "Lançamento não encontrado"}), 404
    if not empresa_permitida(atual["empresa_id"]):
        conn.close()
        return jsonify({"erro": "Acesso negado"}), 403
    vinculado = conn.execute(
        "SELECT 1 FROM vendas WHERE lancamento_id = ? UNION ALL "
        "SELECT 1 FROM entradas_estoque WHERE lancamento_id = ? LIMIT 1",
        (lancamento_id, lancamento_id),
    ).fetchone()
    if vinculado:
        conn.close()
        return jsonify({"erro": "Lançamento automático deve ser alterado pela operação de origem"}), 409

    d = request.get_json(force=True)
    campos = ["categoria_id", "centro_custo_id", "forma_pagamento_id", "tipo",
              "descricao", "valor", "data_lancamento", "status"]
    atualizacoes = {c: d[c] for c in campos if c in d}
    if not atualizacoes:
        conn.close()
        return jsonify({"erro": "Nenhum campo para atualizar"}), 400

    set_clause = ", ".join(f"{c} = ?" for c in atualizacoes)
    valores = list(atualizacoes.values()) + [lancamento_id]
    conn.execute(
        f"UPDATE lancamentos SET {set_clause}, atualizado_em = datetime('now') WHERE id = ?",
        valores,
    )
    conn.execute(
        """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao, dados_anteriores, dados_novos)
           VALUES (?, ?, 'editado', ?, ?)""",
        (lancamento_id, g.usuario_id, str(dict(atual)), str(atualizacoes)),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "atualizado"})


@app.delete("/api/lancamentos/<int:lancamento_id>")
@login_required
def cancelar_lancamento(lancamento_id):
    """Cancela (soft delete) em vez de apagar — mantém histórico financeiro."""
    conn = get_conn()
    atual = conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lancamento_id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({"erro": "Lançamento não encontrado"}), 404
    if not empresa_permitida(atual["empresa_id"]):
        conn.close()
        return jsonify({"erro": "Acesso negado"}), 403
    vinculado = conn.execute(
        "SELECT 1 FROM vendas WHERE lancamento_id = ? UNION ALL "
        "SELECT 1 FROM entradas_estoque WHERE lancamento_id = ? LIMIT 1",
        (lancamento_id, lancamento_id),
    ).fetchone()
    if vinculado:
        conn.close()
        return jsonify({"erro": "Cancele a venda ou entrada que originou este lançamento"}), 409

    conn.execute("UPDATE lancamentos SET status = 'cancelado' WHERE id = ?", (lancamento_id,))
    conn.execute(
        """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao)
           VALUES (?, ?, 'cancelado')""",
        (lancamento_id, g.usuario_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "cancelado"})


# ============================================================
# PRODUTOS E SERVIÇOS
# ============================================================

@app.get("/api/produtos-servicos")
@login_required
def listar_produtos_servicos():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    apenas_ativos = request.args.get("ativos") == "1"
    conn = get_conn()
    query = """SELECT ps.*, c.nome AS categoria_nome
               FROM produtos_servicos ps
               LEFT JOIN categorias c ON c.id = ps.categoria_id
               WHERE ps.empresa_id = ?"""
    if apenas_ativos:
        query += " AND ps.ativo = 1"
    query += " ORDER BY ps.tipo, ps.nome"
    linhas = conn.execute(query, (empresa_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.post("/api/produtos-servicos")
@login_required
def criar_produto_servico():
    d = request.get_json(force=True)
    empresa_id = d.get("empresa_id") or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    campos_obrigatorios = ["tipo", "nome", "preco"]
    faltando = [c for c in campos_obrigatorios if c not in d]
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    if d["tipo"] not in ("produto", "servico"):
        return jsonify({"erro": "tipo deve ser 'produto' ou 'servico'"}), 400
    try:
        preco = float(d["preco"])
        estoque_inicial = float(d.get("estoque_inicial", 0))
    except (TypeError, ValueError, OverflowError):
        return jsonify({"erro": "Preço e estoque devem ser numéricos"}), 400
    if preco < 0 or estoque_inicial < 0:
        return jsonify({"erro": "preco não pode ser negativo"}), 400

    conn = get_conn()

    if not _referencia_da_empresa(conn, "categorias", d.get("categoria_id"), empresa_id, "receita"):
        conn.close()
        return jsonify({"erro": "Categoria de receita inválida para esta empresa"}), 400

    codigo = (d.get("codigo") or "").strip() or None
    if codigo:
        conflito = conn.execute(
            "SELECT id FROM produtos_servicos WHERE empresa_id = ? AND codigo = ?",
            (empresa_id, codigo),
        ).fetchone()
        if conflito:
            conn.close()
            return jsonify({"erro": "Já existe um item com esse código"}), 400

    cur = conn.execute(
        """INSERT INTO produtos_servicos
           (empresa_id, tipo, codigo, nome, descricao, unidade, preco, categoria_id, estoque_atual)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (empresa_id, d["tipo"], codigo, d["nome"], d.get("descricao"),
         d.get("unidade") or "un", preco, d.get("categoria_id"), estoque_inicial),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return jsonify({"id": novo_id}), 201


@app.put("/api/produtos-servicos/<int:item_id>")
@login_required
def editar_produto_servico(item_id):
    conn = get_conn()
    atual = conn.execute("SELECT * FROM produtos_servicos WHERE id = ?", (item_id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({"erro": "Item não encontrado"}), 404
    if not empresa_permitida(atual["empresa_id"]):
        conn.close()
        return jsonify({"erro": "Acesso negado"}), 403

    d = request.get_json(force=True)

    if "codigo" in d:
        novo_codigo = (d["codigo"] or "").strip() or None
        if novo_codigo:
            conflito = conn.execute(
                "SELECT id FROM produtos_servicos WHERE empresa_id = ? AND codigo = ? AND id != ?",
                (atual["empresa_id"], novo_codigo, item_id),
            ).fetchone()
            if conflito:
                conn.close()
                return jsonify({"erro": "Já existe um item com esse código"}), 400
        d["codigo"] = novo_codigo

    campos = ["codigo", "nome", "descricao", "unidade", "preco", "categoria_id", "ativo"]
    atualizacoes = {c: d[c] for c in campos if c in d}
    if not atualizacoes:
        conn.close()
        return jsonify({"erro": "Nenhum campo para atualizar"}), 400

    set_clause = ", ".join(f"{c} = ?" for c in atualizacoes)
    valores = list(atualizacoes.values()) + [item_id]
    conn.execute(f"UPDATE produtos_servicos SET {set_clause} WHERE id = ?", valores)
    conn.commit()
    conn.close()
    return jsonify({"status": "atualizado"})



@app.delete("/api/produtos-servicos/<int:item_id>")
@login_required
def desativar_produto_servico(item_id):
    """Desativa (soft delete) — não apaga, para preservar o histórico de vendas."""
    conn = get_conn()
    atual = conn.execute("SELECT * FROM produtos_servicos WHERE id = ?", (item_id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({"erro": "Item não encontrado"}), 404
    if not empresa_permitida(atual["empresa_id"]):
        conn.close()
        return jsonify({"erro": "Acesso negado"}), 403
    conn.execute("UPDATE produtos_servicos SET ativo = 0 WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "desativado"})


# ============================================================
# VENDAS / PRESTAÇÕES DE SERVIÇO
# Ao registrar, gera automaticamente o lançamento de receita
# correspondente no fluxo de caixa.
# ============================================================

@app.get("/api/vendas")
@login_required
def listar_vendas():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    conn = get_conn()
    linhas = conn.execute(
        """SELECT v.*, ps.nome AS produto_servico_nome, ps.tipo AS produto_servico_tipo
           FROM vendas v
           JOIN produtos_servicos ps ON ps.id = v.produto_servico_id
           WHERE v.empresa_id = ?
           ORDER BY v.data_venda DESC, v.id DESC""",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.post("/api/vendas")
@login_required
def criar_venda():
    d = request.get_json(force=True)
    empresa_id = d.get("empresa_id") or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    campos_obrigatorios = ["produto_servico_id", "data_venda"]
    faltando = [c for c in campos_obrigatorios if c not in d]
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400

    conn = get_conn()
    item = conn.execute(
        "SELECT * FROM produtos_servicos WHERE id = ? AND empresa_id = ?",
        (d["produto_servico_id"], empresa_id),
    ).fetchone()
    if not item:
        conn.close()
        return jsonify({"erro": "Produto/serviço não encontrado"}), 404
    if not item["ativo"]:
        conn.close()
        return jsonify({"erro": "Produto/serviço está desativado"}), 400

    try:
        quantidade = float(d.get("quantidade", 1))
        valor_unitario = float(d.get("valor_unitario", item["preco"]))
    except (TypeError, ValueError, OverflowError):
        conn.close()
        return jsonify({"erro": "Quantidade e valor unitário devem ser numéricos"}), 400
    valor_total = round(quantidade * valor_unitario, 2)
    if quantidade <= 0 or valor_unitario < 0:
        conn.close()
        return jsonify({"erro": "Quantidade e valor unitário devem ser válidos"}), 400
    if erro := _data_iso(d["data_venda"], "data_venda"):
        conn.close()
        return erro

    if item["tipo"] == "produto" and item["estoque_atual"] < quantidade:
        conn.close()
        return jsonify({
            "erro": f"Estoque insuficiente. Disponível: {item['estoque_atual']:g} {item['unidade']}"
        }), 400

    # categoria do lançamento: a do produto/serviço, ou a categoria "Vendas" como padrão
    categoria_id = item["categoria_id"]
    if not categoria_id:
        padrao = conn.execute(
            "SELECT id FROM categorias WHERE tipo = 'receita' AND (empresa_id IS NULL OR empresa_id = ?) "
            "ORDER BY empresa_id IS NULL LIMIT 1",
            (empresa_id,),
        ).fetchone()
        categoria_id = padrao["id"] if padrao else None
    if not categoria_id:
        conn.close()
        return jsonify({"erro": "Nenhuma categoria de receita disponível para gerar o lançamento"}), 400

    verbo = "Serviço prestado" if item["tipo"] == "servico" else "Venda"
    descricao = f"{verbo}: {item['nome']}" + (f" ({quantidade:g}x)" if quantidade != 1 else "")
    if d.get("cliente_nome"):
        descricao += f" — {d['cliente_nome']}"

    try:
        # cria o lançamento de receita automaticamente
        cur_lanc = conn.execute(
            """INSERT INTO lancamentos
               (empresa_id, usuario_id, categoria_id, forma_pagamento_id,
                tipo, descricao, valor, data_lancamento, status)
               VALUES (?, ?, ?, ?, 'receita', ?, ?, ?, 'confirmado')""",
            (empresa_id, g.usuario_id, categoria_id, d.get("forma_pagamento_id"),
             descricao, valor_total, d["data_venda"]),
        )
        lancamento_id = cur_lanc.lastrowid

        cur_venda = conn.execute(
            """INSERT INTO vendas
               (empresa_id, usuario_id, produto_servico_id, quantidade, valor_unitario,
                valor_total, cliente_nome, forma_pagamento_id, data_venda, lancamento_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (empresa_id, g.usuario_id, item["id"], quantidade, valor_unitario,
             valor_total, d.get("cliente_nome"), d.get("forma_pagamento_id"),
             d["data_venda"], lancamento_id),
        )
        venda_id = cur_venda.lastrowid

        if item["tipo"] == "produto":
            atualizado = conn.execute(
                "UPDATE produtos_servicos SET estoque_atual = estoque_atual - ? "
                "WHERE id = ? AND estoque_atual >= ?",
                (quantidade, item["id"], quantidade),
            )
            if atualizado.rowcount != 1:
                raise ValueError("Estoque alterado por outra operação; tente novamente")

        conn.execute(
            """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao, dados_novos)
               VALUES (?, ?, 'criado', ?)""",
            (lancamento_id, g.usuario_id, f"Gerado automaticamente pela venda #{venda_id}"),
        )
        conn.commit()
    except ValueError as exc:
        conn.rollback()
        conn.close()
        return jsonify({"erro": str(exc)}), 409
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return jsonify({"id": venda_id, "lancamento_id": lancamento_id, "valor_total": valor_total}), 201


@app.delete("/api/vendas/<int:venda_id>")
@login_required
def cancelar_venda(venda_id):
    """Cancela a venda, cancela o lançamento de receita gerado e devolve o estoque."""
    conn = get_conn()
    venda = conn.execute("SELECT * FROM vendas WHERE id = ?", (venda_id,)).fetchone()
    if not venda:
        conn.close()
        return jsonify({"erro": "Venda não encontrada"}), 404
    if not empresa_permitida(venda["empresa_id"]):
        conn.close()
        return jsonify({"erro": "Acesso negado"}), 403
    if venda["status"] == "cancelada":
        conn.close()
        return jsonify({"erro": "Esta venda já está cancelada"}), 400

    item = conn.execute(
        "SELECT tipo FROM produtos_servicos WHERE id = ?", (venda["produto_servico_id"],)
    ).fetchone()

    conn.execute("UPDATE vendas SET status = 'cancelada' WHERE id = ?", (venda_id,))
    if item and item["tipo"] == "produto":
        conn.execute(
            "UPDATE produtos_servicos SET estoque_atual = estoque_atual + ? WHERE id = ?",
            (venda["quantidade"], venda["produto_servico_id"]),
        )
    if venda["lancamento_id"]:
        conn.execute(
            "UPDATE lancamentos SET status = 'cancelado' WHERE id = ?", (venda["lancamento_id"],)
        )
        conn.execute(
            """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao)
               VALUES (?, ?, 'cancelado')""",
            (venda["lancamento_id"], g.usuario_id),
        )
    conn.commit()
    conn.close()
    return jsonify({"status": "cancelado"})


# ============================================================
# ENTRADA DE MERCADORIAS (compras)
# Ao registrar, gera automaticamente o lançamento de DESPESA
# correspondente e soma a quantidade ao estoque do item.
# ============================================================

@app.get("/api/entradas-estoque")
@login_required
def listar_entradas_estoque():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    conn = get_conn()
    linhas = conn.execute(
        """SELECT ee.*, ps.nome AS produto_servico_nome, ps.codigo AS produto_servico_codigo,
                  ps.unidade AS produto_servico_unidade
           FROM entradas_estoque ee
           JOIN produtos_servicos ps ON ps.id = ee.produto_servico_id
           WHERE ee.empresa_id = ?
           ORDER BY ee.data_entrada DESC, ee.id DESC""",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.post("/api/entradas-estoque")
@login_required
def criar_entrada_estoque():
    d = request.get_json(force=True)
    empresa_id = d.get("empresa_id") or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    campos_obrigatorios = ["produto_servico_id", "quantidade", "valor_unitario", "data_entrada"]
    faltando = [c for c in campos_obrigatorios if c not in d]
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400

    conn = get_conn()
    item = conn.execute(
        "SELECT * FROM produtos_servicos WHERE id = ? AND empresa_id = ?",
        (d["produto_servico_id"], empresa_id),
    ).fetchone()
    if not item:
        conn.close()
        return jsonify({"erro": "Item não encontrado"}), 404
    if item["tipo"] != "produto":
        conn.close()
        return jsonify({"erro": "Só é possível dar entrada em itens do tipo 'produto'"}), 400

    try:
        quantidade = float(d["quantidade"])
        valor_unitario = float(d["valor_unitario"])
    except (TypeError, ValueError, OverflowError):
        conn.close()
        return jsonify({"erro": "Quantidade e valor unitário devem ser numéricos"}), 400
    if quantidade <= 0 or valor_unitario < 0:
        conn.close()
        return jsonify({"erro": "Quantidade e valor unitário devem ser válidos"}), 400
    if erro := _data_iso(d["data_entrada"], "data_entrada"):
        conn.close()
        return erro
    valor_total = round(quantidade * valor_unitario, 2)

    categoria_id = d.get("categoria_id")
    if categoria_id and not _referencia_da_empresa(conn, "categorias", categoria_id, empresa_id, "despesa"):
        conn.close()
        return jsonify({"erro": "Categoria de despesa inválida para esta empresa"}), 400
    if not categoria_id:
        padrao = conn.execute(
            "SELECT id FROM categorias WHERE tipo = 'despesa' AND (empresa_id IS NULL OR empresa_id = ?) "
            "AND nome = 'Fornecedores' ORDER BY empresa_id IS NULL LIMIT 1",
            (empresa_id,),
        ).fetchone() or conn.execute(
            "SELECT id FROM categorias WHERE tipo = 'despesa' AND (empresa_id IS NULL OR empresa_id = ?) "
            "ORDER BY empresa_id IS NULL LIMIT 1",
            (empresa_id,),
        ).fetchone()
        categoria_id = padrao["id"] if padrao else None
    if not categoria_id:
        conn.close()
        return jsonify({"erro": "Nenhuma categoria de despesa disponível para gerar o lançamento"}), 400

    descricao = f"Entrada de mercadoria: {item['nome']} ({quantidade:g} {item['unidade']})"
    if d.get("fornecedor"):
        descricao += f" — {d['fornecedor']}"

    try:
        cur_lanc = conn.execute(
            """INSERT INTO lancamentos
               (empresa_id, usuario_id, categoria_id, forma_pagamento_id,
                tipo, descricao, valor, data_lancamento, status)
               VALUES (?, ?, ?, ?, 'despesa', ?, ?, ?, 'confirmado')""",
            (empresa_id, g.usuario_id, categoria_id, d.get("forma_pagamento_id"),
             descricao, valor_total, d["data_entrada"]),
        )
        lancamento_id = cur_lanc.lastrowid

        cur_entrada = conn.execute(
            """INSERT INTO entradas_estoque
               (empresa_id, usuario_id, produto_servico_id, quantidade, valor_unitario,
                valor_total, fornecedor, data_entrada, lancamento_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (empresa_id, g.usuario_id, item["id"], quantidade, valor_unitario,
             valor_total, d.get("fornecedor"), d["data_entrada"], lancamento_id),
        )
        entrada_id = cur_entrada.lastrowid

        conn.execute(
            "UPDATE produtos_servicos SET estoque_atual = estoque_atual + ? WHERE id = ?",
            (quantidade, item["id"]),
        )
        conn.execute(
            """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao, dados_novos)
               VALUES (?, ?, 'criado', ?)""",
            (lancamento_id, g.usuario_id, f"Gerado automaticamente pela entrada de estoque #{entrada_id}"),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return jsonify({"id": entrada_id, "lancamento_id": lancamento_id, "valor_total": valor_total}), 201


@app.delete("/api/entradas-estoque/<int:entrada_id>")
@login_required
def cancelar_entrada_estoque(entrada_id):
    """Cancela a entrada, cancela o lançamento de despesa e retira do estoque."""
    conn = get_conn()
    entrada = conn.execute("SELECT * FROM entradas_estoque WHERE id = ?", (entrada_id,)).fetchone()
    if not entrada:
        conn.close()
        return jsonify({"erro": "Entrada não encontrada"}), 404
    if not empresa_permitida(entrada["empresa_id"]):
        conn.close()
        return jsonify({"erro": "Acesso negado"}), 403
    if entrada["status"] == "cancelada":
        conn.close()
        return jsonify({"erro": "Esta entrada já está cancelada"}), 400

    item = conn.execute(
        "SELECT estoque_atual FROM produtos_servicos WHERE id = ?", (entrada["produto_servico_id"],)
    ).fetchone()
    if item and item["estoque_atual"] < entrada["quantidade"]:
        conn.close()
        return jsonify({
            "erro": "Não é possível cancelar: o estoque atual é menor que a quantidade desta entrada "
                    "(parte já foi vendida)"
        }), 400

    conn.execute("UPDATE entradas_estoque SET status = 'cancelada' WHERE id = ?", (entrada_id,))
    conn.execute(
        "UPDATE produtos_servicos SET estoque_atual = estoque_atual - ? WHERE id = ?",
        (entrada["quantidade"], entrada["produto_servico_id"]),
    )
    if entrada["lancamento_id"]:
        conn.execute(
            "UPDATE lancamentos SET status = 'cancelado' WHERE id = ?", (entrada["lancamento_id"],)
        )
        conn.execute(
            """INSERT INTO lancamentos_log (lancamento_id, usuario_id, acao)
               VALUES (?, ?, 'cancelado')""",
            (entrada["lancamento_id"], g.usuario_id),
        )
    conn.commit()
    conn.close()
    return jsonify({"status": "cancelado"})


# ============================================================
# ESTOQUE
# ============================================================

@app.get("/api/estoque")
@login_required
def listar_estoque():
    """Lista os itens do tipo 'produto' com a quantidade atual em estoque."""
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    conn = get_conn()
    linhas = conn.execute(
        """SELECT id, codigo, nome, unidade, estoque_atual, preco, ativo
           FROM produtos_servicos
           WHERE empresa_id = ? AND tipo = 'produto'
           ORDER BY nome""",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])



# ============================================================
# RELATÓRIOS
# ============================================================

@app.get("/api/relatorios/fluxo-caixa")
@login_required
def relatorio_fluxo_caixa():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")

    conn = get_conn()
    if data_inicio or data_fim:
        # com filtro de período: agrupa direto da tabela de lançamentos
        filtros = ["empresa_id = ?", "status = 'confirmado'"]
        params = [empresa_id]
        if data_inicio:
            filtros.append("data_lancamento >= ?")
            params.append(data_inicio)
        if data_fim:
            filtros.append("data_lancamento <= ?")
            params.append(data_fim)
        where = " AND ".join(filtros)
        linhas = conn.execute(
            f"""SELECT empresa_id, strftime('%Y-%m', data_lancamento) AS mes,
                       SUM(CASE WHEN tipo = 'receita' THEN valor ELSE 0 END) AS total_receitas,
                       SUM(CASE WHEN tipo = 'despesa' THEN valor ELSE 0 END) AS total_despesas,
                       SUM(CASE WHEN tipo = 'receita' THEN valor ELSE -valor END) AS saldo
                FROM lancamentos WHERE {where}
                GROUP BY strftime('%Y-%m', data_lancamento)
                ORDER BY mes""",
            params,
        ).fetchall()
    else:
        linhas = conn.execute(
            "SELECT * FROM vw_fluxo_caixa_mensal WHERE empresa_id = ? ORDER BY mes",
            (empresa_id,),
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.get("/api/relatorios/dre")
@login_required
def relatorio_dre():
    """Demonstrativo de Resultado simplificado: totais por categoria e por mês (histórico completo)."""
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403
    conn = get_conn()
    linhas = conn.execute(
        "SELECT * FROM vw_totais_por_categoria WHERE empresa_id = ? ORDER BY mes, tipo, categoria",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.get("/api/relatorios/dre-completo")
@login_required
def relatorio_dre_completo():
    """
    DRE no formato contábil: receitas por categoria, despesas por categoria,
    totais e margem de lucro — filtrável por período.
    """
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    data_inicio = request.args.get("data_inicio") or mesAtualISO_backend() + "-01"
    data_fim = request.args.get("data_fim") or _ultimo_dia_do_mes(data_inicio)

    conn = get_conn()
    receitas = conn.execute(
        """SELECT c.nome AS categoria, SUM(l.valor) AS total
           FROM lancamentos l JOIN categorias c ON c.id = l.categoria_id
           WHERE l.empresa_id = ? AND l.tipo = 'receita' AND l.status = 'confirmado'
             AND l.data_lancamento >= ? AND l.data_lancamento <= ?
           GROUP BY c.nome ORDER BY total DESC""",
        (empresa_id, data_inicio, data_fim),
    ).fetchall()
    despesas = conn.execute(
        """SELECT c.nome AS categoria, SUM(l.valor) AS total
           FROM lancamentos l JOIN categorias c ON c.id = l.categoria_id
           WHERE l.empresa_id = ? AND l.tipo = 'despesa' AND l.status = 'confirmado'
             AND l.data_lancamento >= ? AND l.data_lancamento <= ?
           GROUP BY c.nome ORDER BY total DESC""",
        (empresa_id, data_inicio, data_fim),
    ).fetchall()
    conn.close()

    total_receitas = sum(r["total"] for r in receitas)
    total_despesas = sum(d["total"] for d in despesas)
    resultado_liquido = round(total_receitas - total_despesas, 2)
    margem_lucro = round((resultado_liquido / total_receitas) * 100, 2) if total_receitas > 0 else None

    return jsonify({
        "periodo": {"inicio": data_inicio, "fim": data_fim},
        "receitas": [dict(r) for r in receitas],
        "despesas": [dict(d) for d in despesas],
        "total_receitas": round(total_receitas, 2),
        "total_despesas": round(total_despesas, 2),
        "resultado_liquido": resultado_liquido,
        "margem_lucro": margem_lucro,
    })


@app.get("/api/relatorios/maiores-despesas")
@login_required
def relatorio_maiores_despesas():
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    data_inicio = request.args.get("data_inicio") or mesAtualISO_backend() + "-01"
    data_fim = request.args.get("data_fim") or _ultimo_dia_do_mes(data_inicio)
    limite = request.args.get("limit", default=8, type=int)

    conn = get_conn()
    linhas = conn.execute(
        """SELECT c.nome AS categoria, SUM(l.valor) AS total
           FROM lancamentos l JOIN categorias c ON c.id = l.categoria_id
           WHERE l.empresa_id = ? AND l.tipo = 'despesa' AND l.status = 'confirmado'
             AND l.data_lancamento >= ? AND l.data_lancamento <= ?
           GROUP BY c.nome ORDER BY total DESC LIMIT ?""",
        (empresa_id, data_inicio, data_fim, limite),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.get("/api/relatorios/mais-vendidos")
@login_required
def relatorio_mais_vendidos():
    """Produtos ou serviços mais vendidos no período, por valor total faturado."""
    empresa_id = request.args.get("empresa_id", type=int) or g.empresa_id
    if not empresa_permitida(empresa_id):
        return jsonify({"erro": "Acesso negado a esta empresa"}), 403

    data_inicio = request.args.get("data_inicio") or mesAtualISO_backend() + "-01"
    data_fim = request.args.get("data_fim") or _ultimo_dia_do_mes(data_inicio)
    tipo = request.args.get("tipo")  # 'produto' | 'servico' | None (ambos)
    limite = request.args.get("limit", default=8, type=int)

    filtros = ["v.empresa_id = ?", "v.status = 'confirmada'",
               "v.data_venda >= ?", "v.data_venda <= ?"]
    params = [empresa_id, data_inicio, data_fim]
    if tipo in ("produto", "servico"):
        filtros.append("ps.tipo = ?")
        params.append(tipo)
    where = " AND ".join(filtros)

    conn = get_conn()
    linhas = conn.execute(
        f"""SELECT ps.id AS produto_servico_id, ps.codigo, ps.nome, ps.tipo,
                   SUM(v.quantidade) AS quantidade_total, SUM(v.valor_total) AS valor_total
            FROM vendas v JOIN produtos_servicos ps ON ps.id = v.produto_servico_id
            WHERE {where}
            GROUP BY ps.id ORDER BY valor_total DESC LIMIT ?""",
        params + [limite],
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in linhas])


@app.get("/api/relatorios/extrato")
@login_required
def relatorio_extrato():
    """Alias de /api/lancamentos, pensado para exportação/impressão do extrato."""
    return listar_lancamentos()


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/status")
def status():
    return jsonify({"status": "ok"})


if os.environ.get("TURSO_DATABASE_URL"):
    init_db()


if __name__ == "__main__":
    init_db()
    app.run(
        debug=os.environ.get("APP_CONTABIL_DEBUG") == "1",
        port=int(os.environ.get("APP_CONTABIL_PORT", "5000")),
        host=os.environ.get("APP_CONTABIL_HOST", "127.0.0.1"),
    )
