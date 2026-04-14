from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time, threading
from werkzeug.utils import secure_filename
import requests  # Importante: instalou com pip install requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "super_secret_key_123"

# URL do Google Apps Script que você gerou
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ARQ_USUARIOS = os.path.join(BASE_DIR, "usuarios.json")
ARQ_CHAMADOS = os.path.join(BASE_DIR, "chamados.json")
ARQ_DEPARTAMENTOS = os.path.join(BASE_DIR, "departamentos.json")

# ======================
# NOVA FUNÇÃO DE EMAIL (GOOGLE TUNNEL)
# ======================
def enviar_email(destino, assunto, corpo, nome_usuario):
    try:
        payload = {
            "nome": nome_usuario,
            "assunto": assunto,
            "mensagem": corpo,
            "destinatario": destino # Opcional se você quiser mudar o destino no script
        }
        
        # O Google exige allow_redirects=True
        response = requests.post(URL_GOOGLE_SCRIPT, data=json.dumps(payload), allow_redirects=True)
        
        if response.status_code == 200:
            print(f"[OK] Email enviado via Google para {destino}")
        else:
            print(f"[ERRO] Falha no Google Script: {response.status_code}")

    except Exception as e:
        print("[ERRO EMAIL GOOGLE]:", e)

def enviar_email_async(destino, assunto, corpo, nome_usuario):
    thread = threading.Thread(
        target=enviar_email,
        args=(destino, assunto, corpo, nome_usuario),
        daemon=True
    )
    thread.start()

# ... (Mantive suas funções auxiliares load, save, get_users, etc igual) ...

def load(file):
    if not os.path.exists(file):
        return {"usuarios": []} if "usuarios" in file else []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"usuarios": []} if "usuarios" in file else []

def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_users():
    data = load(ARQ_USUARIOS)
    return data.get("usuarios", []) if isinstance(data, dict) else []

def get_chamados():
    data = load(ARQ_CHAMADOS)
    return data if isinstance(data, list) else []

def set_chamados(data):
    save(ARQ_CHAMADOS, data)

def get_departamentos():
    data = load(ARQ_DEPARTAMENTOS)
    return data if isinstance(data, list) else []

def auth(user, senha):
    for u in get_users():
        if isinstance(u, dict) and u.get("usuario", "").lower() == user.lower():
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                return u
    return None

# ======================
# ROTAS (AJUSTADAS)
# ======================

@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    u = auth(request.form.get("username"), request.form.get("senha"))
    if u:
        session["user"] = u["usuario"]
        session["role"] = u["role"]
        session["setor"] = u["setor"]
        return redirect("/dashboard")
    return "Login inválido"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    role, user, setor = session["role"], session["user"], session.get("setor", "")
    chamados = get_chamados()
    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]
    elif role == "admin":
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
    chamados = get_chamados()
    file = request.files.get("anexo")
    filename = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    prioridade = request.form.get("prioridade", "Normal")
    titulo = request.form.get("titulo")
    descricao = request.form.get("descricao")
    setor_nome = (request.form.get("setor") or "").strip().lower()

    emails_destino = []
    for d in get_departamentos():
        if isinstance(d, dict) and d.get("nome", "").strip().lower() == setor_nome:
            emails_destino = d.get("emails", [])
            break

    assunto = f"[{prioridade.upper()}] {titulo}"
    
    novo_chamado = {
        "id": str(uuid.uuid4()),
        "titulo": assunto,
        "descricao": descricao,
        "setor": setor_nome,
        "prioridade": prioridade,
        "status": "Aberto",
        "criador": session["user"],
        "anexo": filename,
        "respostas": [],
        "created_at": time.time()
    }

    chamados.append(novo_chamado)
    set_chamados(chamados)

    # ENVIO VIA GOOGLE TUNNEL
    corpo_html = f"O setor {setor_nome} recebeu um novo chamado: <br><b>{descricao}</b>"
    
    for email in emails_destino:
        if email:
            enviar_email_async(email, assunto, corpo_html, session["user"])

    return redirect("/dashboard")

@app.route("/chamados")
def chamados_view():
    if "user" not in session: return redirect("/")
    role, user, setor = session["role"], session["user"], session.get("setor", "")
    chamados = get_chamados()
    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]
    elif role == "admin":
        chamados = [c for c in chamados if c.get("setor", "").strip().lower() == setor.strip().lower()]
    return render_template("chamados.html", chamados=chamados, role=role)

@app.route("/atender/<id>")
def atender(id):
    chamados = get_chamados()
    for c in chamados:
        if c["id"] == id: c["status"] = "Em andamento"
    set_chamados(chamados)
    return redirect("/chamados")

@app.route("/finalizar/<id>")
def finalizar(id):
    chamados = get_chamados()
    for c in chamados:
        if c["id"] == id: c["status"] = "Finalizado"
    set_chamados(chamados)
    return redirect("/chamados")
if __name__ == "__main__":
    # Garante que o app use a porta correta do Render e aceite conexões externas
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

