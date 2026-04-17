import os
import requests
from functools import wraps
from datetime import datetime, timezone

from flask import (
    Flask,
    request,
    redirect,
    render_template,
    session,
    flash,
)

import bcrypt
from supabase import create_client

# =====================================================
# CONFIGURAÇÃO BASE
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

# Variáveis ambiente
FLASK_SECRET = os.getenv("FLASK_SECRET", "troque_esta_chave")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT", "")

app.secret_key = FLASK_SECRET

# Segurança de sessão
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =====================================================
# HELPERS
# =====================================================

def log_error(contexto, erro):
    print(f"[ERRO] {contexto}: {erro}")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def query_table(nome):
    return supabase.table(nome)


def get_users():
    try:
        return query_table("usuarios").select("*").execute().data or []
    except Exception as e:
        log_error("get_users", e)
        return []


def get_departamentos():
    try:
        return query_table("departamentos").select("*").order("nome").execute().data or []
    except Exception as e:
        log_error("get_departamentos", e)
        return []


def get_chamados():
    try:
        return (
            query_table("chamados")
            .select("*")
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
    except Exception as e:
        log_error("get_chamados", e)
        return []


def sistema_sem_usuarios():
    return len(get_users()) == 0


def buscar_usuario(username):
    try:
        res = (
            query_table("usuarios")
            .select("*")
            .eq("usuario", username)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        log_error("buscar_usuario", e)
        return None


def buscar_departamento(nome):
    try:
        res = (
            query_table("departamentos")
            .select("*")
            .eq("nome", nome)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        log_error("buscar_departamento", e)
        return None


def hash_password(senha):
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def check_password(senha, senha_hash):
    return bcrypt.checkpw(senha.encode(), senha_hash.encode())


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                return redirect("/")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def enviar_email_google_script(chamado):
    """
    Envia dados do chamado para Google Script.
    """
    if not URL_GOOGLE_SCRIPT:
        return

    try:
        requests.post(
            URL_GOOGLE_SCRIPT,
            json=chamado,
            timeout=10
        )
    except Exception as e:
        log_error("enviar_email_google_script", e)


# =====================================================
# HOME / LOGIN
# =====================================================

@app.route("/")
def home():
    if sistema_sem_usuarios():
        return redirect("/primeiro_acesso")

    if "user_id" in session:
        return redirect("/dashboard")

    return render_template("login.html")


@app.route("/primeiro_acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if not sistema_sem_usuarios():
        return redirect("/")

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not usuario or not senha:
            return render_template(
                "primeiro_acesso.html",
                erro="Preencha usuário e senha."
            )

        try:
            existe = buscar_usuario(usuario)

            if existe:
                return redirect("/")

            query_table("usuarios").insert({
                "usuario": usuario,
                "senha_hash": hash_password(senha),
                "role": "master",
                "setor": "Qualidade",
                "trocar_senha": False,
                "created_at": now_iso()
            }).execute()

            flash("Usuário master criado.")
            return redirect("/")

        except Exception as e:
            log_error("primeiro_acesso", e)

    return render_template("primeiro_acesso.html")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    senha = request.form.get("senha") or ""

    user = buscar_usuario(username)

    if not user:
        return render_template("login.html", erro="Usuário ou senha inválidos.")

    try:
        if not check_password(senha, user["senha_hash"]):
            return render_template("login.html", erro="Usuário ou senha inválidos.")

        session.clear()
        session["user_id"] = user["id"]
        session["user"] = user["usuario"]
        session["role"] = user.get("role", "usuario")
        session["setor"] = user.get("setor", "")

        return redirect("/dashboard")

    except Exception as e:
        log_error("login", e)
        return render_template("login.html", erro="Erro ao fazer login.")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =====================================================
# DASHBOARD
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():
    chamados = get_chamados()

    if session["role"] == "usuario":
        chamados = [
            c for c in chamados
            if c.get("usuario_id") == session["user_id"]
        ]

    return render_template(
        "dashboard.html",
        user=session["user"],
        role=session["role"],
        setor=session["setor"],
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"]),
    )


# =====================================================
# CHAMADOS
# =====================================================

@app.route("/abrir", methods=["GET", "POST"])
@login_required
def abrir_chamado():
    if request.method == "POST":
        titulo = request.form.get("titulo")
        descricao = request.form.get("descricao")
        setor = request.form.get("setor")
        prioridade = request.form.get("prioridade", "Normal")

        try:
            query_table("chamados").insert({
                "titulo": titulo,
                "descricao": descricao,
                "setor": setor,
                "prioridade": prioridade,
                "status": "Aberto",
                "usuario_id": session["user_id"],
                "created_at": now_iso()
            }).execute()

            departamento = buscar_departamento(setor)

            chamado_email = {
                "titulo": titulo,
                "descricao": descricao,
                "setor": setor,
                "prioridade": prioridade,
                "usuario": session["user"],
                "email_destino": departamento.get("email", "") if departamento else ""
            }

            enviar_email_google_script(chamado_email)

            return redirect("/chamados")

        except Exception as e:
            log_error("abrir_chamado", e)

    return render_template(
        "abrir_chamado.html",
        departamentos=get_departamentos()
    )


@app.route("/chamados")
@login_required
def chamados():
    lista = get_chamados()

    if session["role"] == "usuario":
        lista = [
            c for c in lista
            if c.get("usuario_id") == session["user_id"]
        ]

    return render_template(
        "chamados.html",
        chamados=lista,
        role=session["role"]
    )


@app.route("/alterar_status/<id_chamado>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def alterar_status(id_chamado):
    try:
        query_table("chamados").update({
            "status": request.form.get("status")
        }).eq("id", id_chamado).execute()
    except Exception as e:
        log_error("alterar_status", e)

    return redirect("/chamados")


# =====================================================
# ADMIN
# =====================================================

@app.route("/admin")
@login_required
@roles_required("admin", "master")
def admin():
    return render_template(
        "admin.html",
        usuarios=get_users(),
        departamentos=get_departamentos(),
        role=session["role"]
    )


@app.route("/admin/criar_usuario", methods=["POST"])
@login_required
@roles_required("admin", "master")
def criar_usuario():
    username = (request.form.get("username") or "").strip().lower()

    if not username:
        return redirect("/admin")

    try:
        existe = buscar_usuario(username)

        if existe:
            flash("Usuário já existe.")
            return redirect("/admin")

        query_table("usuarios").insert({
            "usuario": username,
            "senha_hash": hash_password("123456"),
            "role": request.form.get("role", "usuario"),
            "setor": request.form.get("setor", ""),
            "trocar_senha": True,
            "created_at": now_iso()
        }).execute()

    except Exception as e:
        log_error("criar_usuario", e)

    return redirect("/admin")


@app.route("/admin/excluir_usuario/<usuario>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def excluir_usuario(usuario):
    try:
        if usuario != session["user"]:
            query_table("usuarios").delete().eq("usuario", usuario).execute()
    except Exception as e:
        log_error("excluir_usuario", e)

    return redirect("/admin")


# =====================================================
# DEPARTAMENTOS
# =====================================================

@app.route("/admin/criar_departamento", methods=["POST"])
@login_required
@roles_required("admin", "master")
def criar_departamento():
    nome = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip()

    if not nome:
        return redirect("/admin")

    try:
        existe = buscar_departamento(nome)

        if not existe:
            query_table("departamentos").insert({
                "nome": nome,
                "email": email
            }).execute()

    except Exception as e:
        log_error("criar_departamento", e)

    return redirect("/admin")


@app.route("/admin/excluir_departamento/<nome>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def excluir_departamento(nome):
    try:
        query_table("departamentos").delete().eq("nome", nome).execute()
    except Exception as e:
        log_error("excluir_departamento", e)

    return redirect("/admin")


# =====================================================
# HEALTH
# =====================================================

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)