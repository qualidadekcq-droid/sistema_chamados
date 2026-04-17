import os
from functools import wraps
from datetime import datetime, timezone

from flask import (
    Flask,
    request,
    redirect,
    render_template,
    session,
    flash,
    abort,
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

# OBRIGATÓRIO no Render / produção
app.secret_key = os.environ["FLASK_SECRET"]

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

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
        res = query_table("usuarios").select("*").execute()
        return res.data or []
    except Exception as e:
        log_error("get_users", e)
        return []


def get_departamentos():
    try:
        res = query_table("departamentos").select("*").execute()
        return res.data or []
    except Exception as e:
        log_error("get_departamentos", e)
        return []


def get_chamados():
    try:
        res = (
            query_table("chamados")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        log_error("get_chamados", e)
        return []


def sistema_sem_usuarios():
    return len(get_users()) == 0


def buscar_usuario_por_login(username):
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
        log_error("buscar_usuario_por_login", e)
        return None


def hash_password(senha):
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def check_password(senha, senha_hash):
    return bcrypt.checkpw(senha.encode(), senha_hash.encode())


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                return redirect("/")
            return f(*args, **kwargs)
        return decorated
    return decorator


def is_admin():
    return session.get("role") in ["admin", "master"]


# =====================================================
# ROTAS GERAIS
# =====================================================

@app.route("/")
def home():
    if sistema_sem_usuarios():
        return redirect("/primeiro_acesso")

    if "user_id" in session:
        return redirect("/dashboard")

    return render_template("login.html")


# =====================================================
# PRIMEIRO ACESSO
# =====================================================

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
            query_table("usuarios").insert({
                "usuario": usuario,
                "senha_hash": hash_password(senha),
                "role": "master",
                "setor": "admin",
                "trocar_senha": False,
                "created_at": now_iso()
            }).execute()

            flash("Usuário master criado com sucesso.")
            return redirect("/")

        except Exception as e:
            log_error("primeiro_acesso", e)
            return render_template(
                "primeiro_acesso.html",
                erro="Erro ao criar usuário master."
            )

    return render_template("primeiro_acesso.html")


# =====================================================
# LOGIN / LOGOUT
# =====================================================

@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    senha = request.form.get("senha") or ""

    user = buscar_usuario_por_login(username)

    if not user:
        return render_template(
            "login.html",
            erro="Usuário ou senha inválidos."
        )

    try:
        if not check_password(senha, user["senha_hash"]):
            return render_template(
                "login.html",
                erro="Usuário ou senha inválidos."
            )

        session.clear()
        session["user_id"] = user["id"]
        session["user"] = user["usuario"]
        session["role"] = user.get("role", "usuario")
        session["setor"] = user.get("setor", "")

        return redirect("/dashboard")

    except Exception as e:
        log_error("login", e)
        return render_template(
            "login.html",
            erro="Erro ao realizar login."
        )


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
        try:
            query_table("chamados").insert({
                "titulo": request.form.get("titulo"),
                "descricao": request.form.get("descricao"),
                "setor": request.form.get("setor"),
                "prioridade": request.form.get("prioridade", "Normal"),
                "status": "Aberto",
                "usuario_id": session["user_id"],
                "created_at": now_iso()
            }).execute()

            return redirect("/chamados")

        except Exception as e:
            log_error("abrir_chamado", e)
            return render_template(
                "abrir_chamado.html",
                departamentos=get_departamentos(),
                erro="Erro ao abrir chamado."
            )

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
    novo_status = request.form.get("status")

    try:
        query_table("chamados").update({
            "status": novo_status
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
        existe = buscar_usuario_por_login(username)

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

        flash("Usuário criado com sucesso.")

    except Exception as e:
        log_error("criar_usuario", e)

    return redirect("/admin")


@app.route("/admin/excluir_usuario/<usuario>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def excluir_usuario(usuario):
    try:
        if usuario == session.get("user"):
            flash("Você não pode excluir a si mesmo.")
            return redirect("/admin")

        query_table("usuarios").delete().eq("usuario", usuario).execute()

    except Exception as e:
        log_error("excluir_usuario", e)

    return redirect("/admin")


# =====================================================
# HEALTHCHECK
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