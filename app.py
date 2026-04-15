from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time, threading
import requests
from supabase import create_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = os.getenv("FLASK_SECRET", "super_secret_key_123")

# ======================
# SUPABASE CONFIG
# ======================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado com sucesso")
    except Exception as e:
        print("❌ Erro ao conectar Supabase:", e)
else:
    print("❌ SUPABASE_URL ou SUPABASE_KEY não definidos")

# ======================
# GOOGLE SCRIPT
# ======================
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT")

# ======================
# UPLOAD
# ======================
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ======================
# HELPERS
# ======================
def get_users():
    try:
        return supabase.table("usuarios").select("*").execute().data or []
    except:
        return []

def get_chamados():
    try:
        return supabase.table("chamados").select("*").execute().data or []
    except:
        return []

def get_departamentos():
    try:
        return supabase.table("departamentos").select("*").execute().data or []
    except:
        return []

# ======================
# EMAIL
# ======================
def enviar_email(destino, assunto, corpo, nome_usuario):
    try:
        if not URL_GOOGLE_SCRIPT:
            return

        payload = {
            "nome": nome_usuario,
            "assunto": assunto,
            "mensagem": corpo,
            "destinatario": destino
        }

        requests.post(URL_GOOGLE_SCRIPT, data=json.dumps(payload), timeout=10)

    except Exception as e:
        print("Erro email:", e)


def enviar_email_async(destino, assunto, corpo, nome_usuario):
    threading.Thread(
        target=enviar_email,
        args=(destino, assunto, corpo, nome_usuario),
        daemon=True
    ).start()

# ======================
# HOME
# ======================
@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

# ======================
# LOGIN (COM TROCA DE SENHA)
# ======================
@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").lower().strip()
    senha = request.form.get("senha") or ""

    users = get_users()
    print("USUARIOS:", users)

    for u in users:
        if u.get("usuario", "").lower() == username:
            try:
                if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):

                    session["user"] = u["usuario"]
                    session["role"] = u.get("role", "usuario")
                    session["setor"] = u.get("setor", "")

                    # 🔥 NOVO: TROCA DE SENHA OBRIGATÓRIA
                    if u.get("trocar_senha") == True:
                        return redirect("/alterar_senha_obrigatoria")

                    return redirect("/dashboard")

            except Exception as e:
                print("Erro login:", e)

    return render_template("login.html", erro="Usuário ou senha inválidos")

# ======================
# ALTERAR SENHA
# ======================
@app.route("/alterar_senha_obrigatoria", methods=["GET", "POST"])
def alterar_senha_obrigatoria():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        nova_senha = request.form.get("nova_senha")

        try:
            hash_novo = bcrypt.hashpw(nova_senha.encode(), bcrypt.gensalt()).decode()

            supabase.table("usuarios").update({
                "senha_hash": hash_novo,
                "trocar_senha": False
            }).eq("usuario", session["user"]).execute()

            return redirect("/dashboard")

        except Exception as e:
            print("Erro alterar senha:", e)
            return render_template("trocar_senha.html", erro="Erro ao atualizar senha")

    return render_template("trocar_senha.html")

# ======================
# LOGOUT
# ======================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ======================
# DASHBOARD
# ======================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    role = session.get("role", "usuario")
    user = session.get("user")
    setor = session.get("setor", "")

    chamados = get_chamados()

    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]
    elif role != "master":
        chamados = [c for c in chamados if c.get("setor", "") == setor]

    return render_template(
        "dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"])
    )

# ======================
# ABRIR CHAMADO
# ======================
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session:
        return redirect("/")

    titulo = request.form.get("titulo")
    descricao = request.form.get("descricao")
    prioridade = (request.form.get("prioridade") or "Normal").upper()
    setor_nome = (request.form.get("setor") or "").strip().lower()

    emails_destino = []

    for d in get_departamentos():
        if d.get("nome", "").strip().lower() == setor_nome:
            emails_destino = d.get("emails", [])
            break

    novo = {
        "id": str(uuid.uuid4()),
        "titulo": f"[{prioridade}] {titulo}",
        "descricao": descricao,
        "setor": setor_nome,
        "prioridade": prioridade,
        "status": "Aberto",
        "criador": session["user"],
        "created_at": time.time()
    }

    try:
        supabase.table("chamados").insert(novo).execute()
    except Exception as e:
        print("Erro insert chamado:", e)

    for email in emails_destino:
        enviar_email_async(email, novo["titulo"], descricao, session["user"])

    return redirect("/dashboard")

# ======================
# CHAMADOS
# ======================
@app.route("/chamados")
def chamados_view():
    if "user" not in session:
        return redirect("/")

    chamados = get_chamados()
    return render_template("chamados.html", chamados=chamados, role=session.get("role"))

# ======================
# ADMIN
# ======================
@app.route("/admin/criar_usuario", methods=["POST"])
def admin_criar_usuario():
    try:
        hash_padrao = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()

        novo = {
            "usuario": request.form.get("username"),
            "senha_hash": hash_padrao,
            "role": request.form.get("role"),
            "setor": request.form.get("setor"),
            "trocar_senha": True   # 🔥 NOVO USUÁRIO FORÇA TROCA
        }

        supabase.table("usuarios").insert(novo).execute()

    except Exception as e:
        print("Erro criar usuário:", e)

    return redirect("/admin")

# ======================
# RUN
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)