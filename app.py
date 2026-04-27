import os
import requests
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, request, redirect, render_template, session
import bcrypt
from supabase import create_client

# =====================================================
# CONFIG
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.secret_key = os.getenv("FLASK_SECRET", "troque_esta_chave")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT", "")

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SENHA_PADRAO = "123456"

# =====================================================
# HELPERS
# =====================================================

def log_error(ctx, err):
    print(f"[ERRO] {ctx}: {err}")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def enviar_email_google_script(payload):
    if not URL_GOOGLE_SCRIPT:
        print("[EMAIL] URL não configurada")
        return

    try:
        response = requests.post(URL_GOOGLE_SCRIPT, json=payload, timeout=10)
        print("[EMAIL] status:", response.status_code)
        print("[EMAIL] resposta:", response.text)
    except Exception as e:
        log_error("email_google_script", e)

def table(name):
    return supabase.table(name)

def hash_password(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_password(pw, hashed):
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def get_users():
    try:
        return table("usuarios").select("*").execute().data or []
    except Exception as e:
        log_error("get_users", e)
        return []

def get_departamentos():
    try:
        return table("departamentos").select("*").order("nome").execute().data or []
    except Exception as e:
        log_error("get_departamentos", e)
        return []

def get_chamados():
    try:
        return table("chamados").select("*").order("created_at", desc=True).execute().data or []
    except Exception as e:
        log_error("get_chamados", e)
        return []

def buscar_usuario(username):
    try:
        res = table("usuarios").select("*").eq("usuario", username).limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        log_error("buscar_usuario", e)
        return None

def buscar_departamento(nome):
    try:
        res = table("departamentos").select("*").eq("nome", nome).limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        log_error("buscar_departamento", e)
        return None

# =====================================================
# AUTH
# =====================================================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            role = (session.get("role") or "").lower()
            if role not in roles:
                return redirect("/dashboard")
            return f(*args, **kwargs)
        return wrapper
    return decorator

# =====================================================
# LOGIN
# =====================================================
@app.route("/")
def home():
    return redirect("/dashboard") if session.get("user_id") else render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    senha = request.form.get("senha") or ""

    user = buscar_usuario(username)

    if not user:
        return render_template("login.html", erro="Usuário inválido")

    if not user.get("ativo", True):
        return render_template("login.html", erro="Usuário bloqueado")
 
    if not check_password(senha, user["senha_hash"]):
        return render_template("login.html", erro="Senha inválida")

    session.clear()
    session["user_id"] = user["id"]
    session["user"] = user["usuario"]
    session["role"] = (user.get("role") or "usuario").lower()
    session["setor"] = user.get("setor", "")

    if user.get("trocar_senha"):
        return redirect("/trocar_senha")

    return redirect("/dashboard")

@app.route("/trocar_senha", methods=["GET", "POST"])
@login_required
def trocar_senha():

    if request.method == "POST":

        nova = (request.form.get("nova_senha") or "").strip()
        confirmar = (request.form.get("confirmar_senha") or "").strip()

        if len(nova) < 6:
            return render_template(
                "trocar_senha.html",
                erro="A senha precisa ter no mínimo 6 caracteres."
            )

        if nova != confirmar:
            return render_template(
                "trocar_senha.html",
                erro="As senhas não coincidem."
            )

        if nova == "123456":
            return render_template(
                "trocar_senha.html",
                erro="Escolha uma senha diferente da padrão."
            )

        table("usuarios").update({
            "senha_hash": hash_password(nova),
            "trocar_senha": False
        }).eq("id", session["user_id"]).execute()

        return redirect("/dashboard")

    return render_template("trocar_senha.html")
@app.route("/admin/alterar_setor/<usuario>", methods=["POST"])
@login_required
@roles_required("master")
def alterar_setor(usuario):
    novo_setor = request.form.get("setor")

    table("usuarios").update({
        "setor": novo_setor
    }).eq("usuario", usuario).execute()

    return redirect("/admin")

# =====================================================
# CHAMADOS
# =====================================================


@app.route("/abrir", methods=["GET", "POST"])
@login_required
def abrir():
    if request.method == "POST":
        titulo = (request.form.get("titulo") or "").strip()
        descricao = (request.form.get("descricao") or "").strip()
        setor = (request.form.get("setor") or "").strip()
        prioridade = (request.form.get("prioridade") or "Normal").upper()

        arquivo = request.files.get("arquivo")
        url_arquivo = None

        if arquivo and arquivo.filename:
            pasta = os.path.join(BASE_DIR, "uploads")
            os.makedirs(pasta, exist_ok=True)

            nome_arquivo = f"{datetime.now().timestamp()}_{arquivo.filename}"
            caminho = os.path.join(pasta, nome_arquivo)
            arquivo.save(caminho)

            url_arquivo = f"/uploads/{nome_arquivo}"

        table("chamados").insert({
            "titulo": titulo,
            "descricao": descricao,
            "setor": setor,
            "prioridade": prioridade,
            "status": "Aberto",
            "usuario_id": session["user_id"],
            "usuario_nome": session["user"],
            "usuario_setor": session["setor"],
            "created_at": now_iso(),
            "anexo": url_arquivo
        }).execute()

        dep = buscar_departamento(setor)

        assunto_formatado = f"[{prioridade}] {titulo}"
        solicitante = f"{session['user'].upper()} - SETOR {session['setor'].upper()}"

        enviar_email_google_script({
            "destinatario": dep.get("email", "") if dep else "",
            "assunto": assunto_formatado,
            "nome": solicitante,
            "mensagem": descricao
        })

        return redirect("/chamados")

    return render_template(
        "abrir_chamado.html",
        departamentos=get_departamentos(),
        role=session.get("role", "usuario")
    )

@app.route("/chamados")
@login_required
def chamados():
    lista = get_chamados()

    role = session["role"]
    user_id = session["user_id"]
    setor = session["setor"]

    if role == "usuario":
        lista = [c for c in lista if c.get("usuario_id") == user_id]

    elif role == "admin":
        lista = [
            c for c in lista
            if c.get("setor") == setor
            or c.get("usuario_id") == user_id
        ]

    mensagens = table("mensagens_chamado")\
        .select("*")\
        .order("created_at")\
        .execute().data or []

    for c in lista:
        c["respostas"] = [
            m for m in mensagens
            if str(m["chamado_id"]) == str(c["id"])
        ]

        # compatibilidade html novo
        c["usuario_setor"] = c.get("usuario_setor", "")

    return render_template(
        "chamados.html",
        chamados=lista,
        role=role
    )
# =====================================================
# ADMIN PANEL
# =====================================================

@app.route("/admin")
@login_required
@roles_required("admin", "master")
def admin():
    return render_template(
        "admin.html",
        usuarios=get_users(),
        departamentos=get_departamentos(),
        role=session["role"],
        user=session["user"]
    )

# -------------------------
# USUÁRIOS
# -------------------------

@app.route("/admin/criar_usuario", methods=["POST"])
@login_required
@roles_required("admin", "master")
def criar_usuario():
    username = request.form.get("username").strip().lower()

    if buscar_usuario(username):
        return redirect("/admin")

    table("usuarios").insert({
        "usuario": username,
        "senha_hash": hash_password(SENHA_PADRAO),
        "role": request.form.get("role", "usuario"),
        "setor": request.form.get("setor"),
        "ativo": True,
        "trocar_senha": True,
        "created_at": now_iso()
    }).execute()

    return redirect("/admin")

@app.route("/admin/bloquear_usuario/<usuario>", methods=["POST"])
@login_required
@roles_required("master")
def bloquear_usuario(usuario):

    if usuario == session["user"]:
        return redirect("/admin")

    table("usuarios").update({
        "ativo": False
    }).eq("usuario", usuario).execute()

    return redirect("/admin")


@app.route("/admin/desbloquear_usuario/<usuario>", methods=["POST"])
@login_required
@roles_required("master")
def desbloquear_usuario(usuario):

    table("usuarios").update({
        "ativo": True
    }).eq("usuario", usuario).execute()

    return redirect("/admin")


@app.route("/admin/resetar_senha/<usuario>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def reset_senha(usuario):
    table("usuarios").update({
        "senha_hash": hash_password(SENHA_PADRAO),
        "trocar_senha": True
    }).eq("usuario", usuario).execute()

    return redirect("/admin")

# -------------------------
# DEPARTAMENTOS
# -------------------------

@app.route("/admin/criar_departamento", methods=["POST"])
@login_required
@roles_required("master")
def criar_departamento():
    table("departamentos").insert({
        "nome": request.form.get("nome"),
        "email": request.form.get("email")
    }).execute()

    return redirect("/admin")


@app.route("/admin/excluir_departamento/<nome>", methods=["POST"])
@login_required
@roles_required("master")
def excluir_departamento(nome):
    table("departamentos").delete().eq("nome", nome).execute()
    return redirect("/admin")

@app.route("/chamados/responder/<chamado_id>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def responder_chamado(chamado_id):

    chamado = table("chamados")\
        .select("*")\
        .eq("id", chamado_id)\
        .limit(1)\
        .execute().data

    if chamado and chamado[0]["status"] == "Finalizado":
       return redirect("/chamados")

    mensagem = (request.form.get("mensagem") or "").strip()

    arquivo = request.files.get("arquivo")
    url_arquivo = None

    if arquivo and arquivo.filename:
       pasta = os.path.join(BASE_DIR, "uploads")
       os.makedirs(pasta, exist_ok=True)

       nome_arquivo = f"{datetime.now().timestamp()}_{arquivo.filename}"

       caminho = os.path.join(pasta, nome_arquivo)
       arquivo.save(caminho)

       url_arquivo = f"/uploads/{nome_arquivo}"
    if mensagem or url_arquivo:
        table("mensagens_chamado").insert({
            "chamado_id": chamado_id,
            "usuario_id": session["user_id"],
            "mensagem": mensagem,
            "anexo": url_arquivo,
            "created_at": now_iso()
        }).execute()

    return redirect("/chamados")

@app.route("/chamados/assumir/<chamado_id>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def assumir_chamado(chamado_id):
    table("chamados").update({
        "status": "Em andamento",
        "responsavel_id": session["user_id"],
        "responsavel_nome": session["user"],
        "assumido_em": now_iso()
    }).eq("id", chamado_id).execute()

    return redirect("/chamados")


@app.route("/chamados/finalizar/<chamado_id>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def finalizar_chamado(chamado_id):
    table("chamados").update({
        "status": "Finalizado",
        "finalizado_em": now_iso()
    }).eq("id", chamado_id).execute()

    return redirect("/chamados")


@app.route("/chamados/prioridade/<chamado_id>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def prioridade_chamado(chamado_id):
    prioridade = (request.form.get("prioridade") or "NORMAL").upper()

    table("chamados").update({
        "prioridade": prioridade
    }).eq("id", chamado_id).execute()

    return redirect("/chamados")

# =====================================================
# DASHBOARD
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():
    chamados = get_chamados()

    role = session["role"]
    user_id = session["user_id"]
    setor = session["setor"]

    if role == "usuario":
        chamados = [c for c in chamados if c.get("usuario_id") == user_id]

    elif role == "admin":
        chamados = [
            c for c in chamados
            if c.get("setor") == setor
            or c.get("usuario_id") == user_id
        ]

    return render_template(
        "dashboard.html",
        user=session["user"],
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"])
    )
# =====================================================
# HEALTH
# =====================================================

@app.route("/health")
def health():
    return {"status": "ok"}, 200

# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))