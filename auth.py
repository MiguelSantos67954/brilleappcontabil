"""
Autenticação simples baseada em token JWT.
"""
import jwt
import datetime
import os
import secrets
import warnings
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

SECRET_KEY = os.environ.get("APP_CONTABIL_SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)
    warnings.warn(
        "APP_CONTABIL_SECRET_KEY não definida; foi criada uma chave temporária. "
        "Defina a variável para manter sessões após reiniciar o servidor.",
        RuntimeWarning,
    )
TOKEN_EXP_HORAS = 8


def gerar_token(usuario):
    payload = {
        "usuario_id": usuario["id"],
        "empresa_id": usuario["empresa_id"],
        "papel": usuario["papel"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXP_HORAS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decodificar_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def login_required(f):
    """Exige um token válido no header Authorization: Bearer <token>."""
    @wraps(f)
    def decorador(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"erro": "Token não fornecido"}), 401
        token = auth_header.split(" ", 1)[1]
        dados = decodificar_token(token)
        if not dados:
            return jsonify({"erro": "Token inválido ou expirado"}), 401
        # Nunca confia em papel/empresa vindos apenas do token. Isso também
        # revoga imediatamente sessões de usuários removidos ou desativados.
        from database import get_conn
        conn = get_conn()
        usuario = conn.execute(
            "SELECT id, empresa_id, papel FROM usuarios WHERE id = ? AND ativo = 1",
            (dados.get("usuario_id"),),
        ).fetchone()
        conn.close()
        if not usuario:
            return jsonify({"erro": "Usuário inexistente ou desativado"}), 401
        g.usuario_id = usuario["id"]
        g.empresa_id = usuario["empresa_id"]
        g.papel = usuario["papel"]
        return f(*args, **kwargs)
    return decorador


def admin_required(f):
    """Exige que o usuário logado seja admin da consultoria."""
    @wraps(f)
    def decorador(*args, **kwargs):
        if g.get("papel") != "admin":
            return jsonify({"erro": "Acesso restrito ao administrador"}), 403
        return f(*args, **kwargs)
    return decorador


def empresa_permitida(empresa_id_solicitado):
    """
    Verifica se o usuário logado pode acessar dados da empresa solicitada.
    Admin acessa qualquer empresa; cliente só acessa a própria.
    """
    if g.papel == "admin":
        return True
    return g.empresa_id == empresa_id_solicitado


# Reexporta para uso nas rotas de cadastro/login
__all__ = [
    "gerar_token", "decodificar_token", "login_required", "admin_required",
    "empresa_permitida", "generate_password_hash", "check_password_hash",
]
