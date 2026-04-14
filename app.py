from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time, threading
from werkzeug.utils import secure_filename
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "super_secret_key_123"

# URL do Google Apps Script
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ARQ_USUARIOS = os.path.join(BASE_DIR, "usuarios.json")
ARQ_CHAMADOS = os.path.join(BASE_DIR, "chamados.json")
ARQ_DEPARTAMENTOS = os.path.join(BASE_DIR, "departamentos.json")

# ======================
# FUNÇÕES DE APOIO E EMAIL
# ======================
def enviar_email(destino, assunto, corpo, nome_usuario):
    try:
        if not URL_GOOGLE_SCRIPT: return
        payload = {"nome": nome_usuario, "assunto": assunto, "mensagem": corpo, "destinatario": destino}
        requests.post(URL_GOOGLE_SCRIPT, data=json.dumps(payload), allow_redirects=True)
    except Exception as e:
        print(f"[ERRO EMAIL]: {e}")

def enviar_email_async(destino, assunto, corpo, nome_usuario):
    threading.Thread(target=enviar_email, args=(destino, assunto, corpo, nome_usuario), daemon=True).start()

def load(file):
    if not os.path.exists(file): return {"usuarios": []} if "usuarios" in file else []
    try:
        with open(file, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"usuarios": []} if "usuarios" in file else []

def save(file, data):
    with open(file, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_users():
    data = load(ARQ_USUARIOS)
    return data.get("usuarios", []) if isinstance(data, dict) else []

def set_users(users): save(ARQ_USUARIOS, {"usuarios": users})

def get_chamados(): return load(ARQ_CHAMADOS)

def set_chamados(data): save(ARQ_CHAMADOS, data)

def get_departamentos(): return load(ARQ_DEPARTAMENTOS)

def pode_gerenciar(alvo_role):
    meu_role = session.get("role")
    if meu_role == "master": return True
    if meu_role == "admin" and alvo_role == "usuario": return True
    return False

# ======================
# LOGIN E TROCA DE SENHA
# ======================
@app.route("/")
def home():
    if "user" in session: return redirect("/dashboard")
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").lower().strip()
    senha = request.form.get("senha")
    users = get_users()
    for u in users:
        if u.get("usuario", "").lower() == username:
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                if u.get("trocar_senha"):
                    session["temp_user"] = u["usuario"]
                    return render_template("trocar_senha.html")
                session["user"] = u["usuario"]; session["role"] = u["role"]; session["setor"] = u["setor"]
                return redirect("/dashboard")
    return "Login inválido"

@app.route("/alterar_senha_obrigatoria", methods=["POST"])
def alterar_senha_obrigatoria():
    username = session.get("temp_user")
    nova_senha = request.form.get("nova_senha")
    if not username or not nova_senha: return redirect("/")
    users = get_users()
    for u in users:
        if u["usuario"] == username:
            u["senha_hash"] = bcrypt.hashpw(nova_senha.encode(), bcrypt.gensalt()).decode()
            u["trocar_senha"] = False
            break
    set_users(users); session.clear()
    return "Senha alterada com sucesso! Faça login <a href='/'>aqui</a>."

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ======================
# DASHBOARD E CHAMADOS
# ======================
@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    role, user, setor = session["role"], session["user"], session.get("setor", "")
    chamados = get_chamados()
    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]
    elif role != "master":
        chamados = [c for c in chamados if c.get("setor", "").strip().lower() == setor.strip().lower()]
    return render_template("dashboard.html", user=user, role=role, setor=setor, total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"]))

@app.route("/abrir")
def abrir():
    if "user" not in session: return redirect("/")
    return render_template("abrir_chamado.html", departamentos=get_departamentos())

@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session: return redirect("/")
    chamados = get_chamados(); titulo = request.form.get("titulo")
    descricao = request.form.get("descricao"); setor_nome = (request.form.get("setor") or "").strip().lower()
    emails_destino = []
    for d in get_departamentos():
        if d.get("nome", "").strip().lower() == setor_nome:
            emails_destino = d.get("emails", [])
            break
    novo = {"id": str(uuid.uuid4()), "titulo": titulo, "descricao": descricao, "setor": setor_nome, "status": "Aberto", "criador": session["user"], "created_at": time.time()}
    chamados.append(novo); set_chamados(chamados)
    for email in emails_destino:
        enviar_email_async(email, f"Novo Chamado: {titulo}", descricao, session["user"])
    return redirect("/dashboard")

@app.route("/chamados")
def chamados_view():
    if "user" not in session: return redirect("/")
    role, user, setor = session["role"], session["user"], session.get("setor", "")
    chamados = get_chamados()
    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]
    elif role != "master":
        chamados = [c for c in chamados if c.get("setor", "").strip().lower() == setor.strip().lower()]
    return render_template("chamados.html", chamados=chamados, role=role)

# ======================
# PAINEL ADMIN CENTRALIZADO
# ======================
@app.route("/admin")
def painel_admin():
    if session.get("role") not in ["master", "admin"]: return redirect("/")
    return render_template("painel_admin.html", 
                           usuarios=get_users(), 
                           departamentos=get_departamentos(), 
                           role=session.get("role"))

@app.route("/admin/criar_usuario", methods=["POST"])
def admin_criar_usuario():
    if session.get("role") not in ["master", "admin"]: return redirect("/")
    target_role = request.form.get("role")
    if not pode_gerenciar(target_role): return "Sem permissão", 403
    users = get_users()
    hash_padrao = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()
    novo = {"usuario": request.form.get("username").strip(), "senha_hash": hash_padrao, "role": target_role, "setor": request.form.get("setor"), "trocar_senha": True}
    users.append(novo); set_users(users)
    return redirect("/admin")

@app.route("/admin/excluir_usuario/<nome>")
def excluir_usuario(nome):
    users = get_users()
    for u in users:
        if u["usuario"] == nome and pode_gerenciar(u["role"]):
            users = [user for user in users if user["usuario"] != nome]
            set_users(users); break
    return redirect("/admin")

@app.route("/admin/resetar_senha/<nome>")
def resetar_senha(nome):
    users = get_users()
    for u in users:
        if u["usuario"] == nome and pode_gerenciar(u["role"]):
            u["senha_hash"] = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()
            u["trocar_senha"] = True; break
    set_users(users)
    return redirect("/admin")

@app.route("/admin/criar_setor", methods=["POST"])
def admin_criar_setor():
    if session.get("role") != "master": return "Apenas Master", 403
    deps = get_departamentos()
    novo = {"nome": request.form.get("nome").strip().lower(), "emails": [e.strip() for e in request.form.get("emails").split(",")]}
    deps.append(novo); save(ARQ_DEPARTAMENTOS, deps)
    return redirect("/admin")

@app.route("/admin/excluir_setor/<nome>")
def excluir_setor(nome):
    if session.get("role") == "master":
        deps = [d for d in get_departamentos() if d["nome"] != nome]
        save(ARQ_DEPARTAMENTOS, deps)
    return redirect("/admin")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
