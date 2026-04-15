from flask import Flask, request, redirect, render_template, session
import bcrypt, os, time
from supabase import create_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

# Use uma variável de ambiente no Render para o secret_key
app.secret_key = os.getenv("FLASK_SECRET", "chave_mestra_saas_123")

# ======================
# CONEXÃO SUPABASE
# ======================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================
# FUNÇÕES DE APOIO (HELPERS)
# ======================
def get_users():
    try:
        return supabase.table("usuarios").select("*").execute().data or []
    except: return []

def get_chamados():
    try:
        return supabase.table("chamados").select("*").execute().data or []
    except: return []

def get_departamentos():
    try:
        return supabase.table("departamentos").select("*").execute().data or []
    except: return []

def sistema_sem_usuarios():
    return len(get_users()) == 0

# ======================
# ROTAS DE ACESSO E LOGIN
# ======================

@app.route("/")
def home():
    if sistema_sem_usuarios():
        return redirect("/primeiro_acesso")
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/primeiro_acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if not sistema_sem_usuarios() and request.method == "GET":
        return redirect("/")
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")
        hash_senha = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
        master = {
            "usuario": usuario,
            "senha_hash": hash_senha,
            "role": "master",
            "setor": "admin",
            "trocar_senha": False
        }
        supabase.table("usuarios").insert(master).execute()
        return redirect("/")
    return render_template("primeiro_acesso.html")

@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").lower().strip()
    senha = request.form.get("senha") or ""
    users = get_users()
    for u in users:
        if u.get("usuario", "").lower() == username:
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                # IMPORTANTE: Guardamos o UUID para vincular os chamados
                session["user_id"] = u.get("id") 
                session["user"] = u["usuario"]
                session["role"] = u.get("role", "usuario")
                session["setor"] = u.get("setor", "")
                return redirect("/dashboard")
    return render_template("login.html", erro="Usuário ou senha inválidos")

@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    chamados = get_chamados()
    # Filtro: Usuário comum só vê os dele. Master/Admin vê tudo.
    if session["role"] == "usuario":
        chamados = [c for c in chamados if c.get("usuario_id") == session.get("user_id")]
    
    return render_template("dashboard.html", 
        user=session["user"], role=session["role"], setor=session["setor"],
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"])
    )

# ======================
# ROTAS DE CHAMADOS
# ======================

@app.route("/abrir", methods=["GET", "POST"])
def abrir_chamado():
    if "user" not in session: return redirect("/")
    if request.method == "POST":
        novo = {
            "titulo": request.form.get("titulo"),
            "descricao": request.form.get("descricao"),
            "setor": request.form.get("setor"),
            "prioridade": request.form.get("prioridade", "Normal"),
            "status": "Aberto",
            "usuario_id": session.get("user_id"),
            "created_at": int(time.time())
        }
        supabase.table("chamados").insert(novo).execute()
        return redirect("/chamados")
    
    return render_template("abrir_chamado.html", departamentos=get_departamentos())

@app.route("/chamados")
def chamados():
    if "user" not in session: return redirect("/")
    lista = get_chamados()
    if session["role"] == "usuario":
        lista = [c for c in lista if c.get("usuario_id") == session.get("user_id")]
    return render_template("chamados.html", chamados=lista, role=session["role"])

@app.route("/alterar_status/<id_chamado>", methods=["POST"])
def alterar_status(id_chamado):
    if session.get("role") not in ["admin", "master"]: return redirect("/")
    novo_status = request.form.get("status")
    supabase.table("chamados").update({"status": novo_status}).eq("id", id_chamado).execute()
    return redirect("/chamados")

# ======================
# PAINEL ADMINISTRATIVO
# ======================

@app.route("/admin")
def admin():
    if session.get("role") not in ["admin", "master"]: return redirect("/")
    return render_template("admin.html", 
                         usuarios=get_users(), 
                         departamentos=get_departamentos(), 
                         role=session["role"])

@app.route("/admin/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") not in ["admin", "master"]: return redirect("/")
    username = request.form.get("username").lower().strip()
    senha_hash = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()
    novo = {
        "usuario": username, "senha_hash": senha_hash,
        "role": request.form.get("role"), "setor": request.form.get("setor"),
        "trocar_senha": True
    }
    supabase.table("usuarios").insert(novo).execute()
    return redirect("/admin")

@app.route("/admin/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    if session.get("role") in ["admin", "master"]:
        supabase.table("usuarios").delete().eq("usuario", usuario).execute()
    return redirect("/admin")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    # Render usa a variável de ambiente PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
