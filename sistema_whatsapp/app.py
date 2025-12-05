import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import datetime

app = Flask(__name__)
app.secret_key = "TROQUE-ESSA-CHAVE-POR-UMA-SECRETA"
DATABASE = "avaliacao_entregadores.db"

# ---------------- BANCO DE DADOS ----------------

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    # Tabela usuarios
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            role TEXT NOT NULL, -- superadmin, admin, caixa
            ativo INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # Tabela entregadores
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entregadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone_whatsapp TEXT NOT NULL,
            link_avaliacao_base TEXT, -- se quiser um link específico por entregador
            ativo INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # Tabela mensagens modelo
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mensagens_modelo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            corpo_texto TEXT NOT NULL,
            ativa INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # Tabela configuracoes (API, links gerais, etc.)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave TEXT NOT NULL UNIQUE,
            valor TEXT NOT NULL
        );
        """
    )

    # Tabela de envios de WhatsApp
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS envios_whatsapp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario INTEGER,
            id_entregador INTEGER,
            nome_cliente TEXT,
            telefone_cliente TEXT,
            mensagem_enviada TEXT,
            data_hora TEXT,
            status TEXT,
            retorno_api TEXT
        );
        """
    )

    conn.commit()

    # Cria superadmin padrão se não existir
    cur.execute("SELECT id FROM usuarios WHERE role = 'superadmin' LIMIT 1;")
    row = cur.fetchone()
    if not row:
        senha_hash = generate_password_hash("admin")
        cur.execute(
            """
            INSERT INTO usuarios (nome, login, senha_hash, role, ativo)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Super Administrador", "admin", senha_hash, "superadmin", 1),
        )
        print("Usuário superadmin criado. Login: admin / Senha: admin")

    conn.commit()
    conn.close()


# ---------------- DECORATORS DE LOGIN E PERMISSÃO ----------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_role" not in session:
                return redirect(url_for("login"))
            if session["user_role"] not in roles:
                flash("Você não tem permissão para acessar essa página.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper


# ---------------- FUNÇÃO FICTÍCIA DE ENVIO WHATSAPP ----------------

def enviar_whatsapp(telefone, mensagem):
    """
    Aqui você integra com a API que escolher (WhatsApp Cloud API, Twilio, Zenvia etc.)

    Por enquanto, só vamos simular o envio, imprimindo no console.
    Depois você troca por uma chamada real com 'requests.post(...)'
    """
    print("=== ENVIO WHATSAPP SIMULADO ===")
    print(f"Para: {telefone}")
    print("Mensagem:")
    print(mensagem)
    print("================================")

    # Exemplo de retorno de sucesso
    return True, "simulado OK"


# ---------------- ROTAS DE AUTENTICAÇÃO ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_user = request.form.get("login")
        senha = request.form.get("senha")

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM usuarios WHERE login = ? AND ativo = 1",
            (login_user,),
        )
        user = cur.fetchone()

        if user and check_password_hash(user["senha_hash"], senha):
            session["user_id"] = user["id"]
            session["user_name"] = user["nome"]
            session["user_role"] = user["role"]
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for("index"))
        else:
            flash("Login ou senha inválidos.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("login"))


# ---------------- ROTAS PRINCIPAIS ----------------

@app.route("/")
@login_required
def index():
    role = session.get("user_role")
    if role == "superadmin":
        return render_template("dashboard_superadmin.html")
    elif role == "admin":
        # Pode criar um dashboard específico de admin se quiser
        return redirect(url_for("listar_entregadores"))
    else:
        # caixa
        return redirect(url_for("caixa_enviar"))


# ---------------- GESTÃO DE USUÁRIOS (SUPERADMIN) ----------------

@app.route("/superadmin/usuarios")
@login_required
@role_required("superadmin")
def listar_usuarios():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM usuarios")
    usuarios = cur.fetchall()
    return render_template("usuarios_listar.html", usuarios=usuarios)


@app.route("/superadmin/usuarios/novo", methods=["GET", "POST"])
@login_required
@role_required("superadmin")
def novo_usuario():
    if request.method == "POST":
        nome = request.form.get("nome")
        login_user = request.form.get("login")
        senha = request.form.get("senha")
        role = request.form.get("role")

        if not nome or not login_user or not senha or not role:
            flash("Preencha todos os campos.", "danger")
            return redirect(url_for("novo_usuario"))

        senha_hash = generate_password_hash(senha)
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                """
                INSERT INTO usuarios (nome, login, senha_hash, role, ativo)
                VALUES (?, ?, ?, ?, 1)
                """,
                (nome, login_user, senha_hash, role),
            )
            db.commit()
            flash("Usuário criado com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Já existe um usuário com esse login.", "danger")

        return redirect(url_for("listar_usuarios"))

    return render_template("usuarios_novo.html")


# ---------------- GESTÃO DE ENTREGADORES (ADMIN + SUPERADMIN) ----------------

@app.route("/admin/entregadores")
@login_required
@role_required("admin", "superadmin")
def listar_entregadores():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM entregadores WHERE ativo = 1")
    entregadores = cur.fetchall()
    return render_template("entregadores_listar.html", entregadores=entregadores)


@app.route("/admin/entregadores/novo", methods=["GET", "POST"])
@login_required
@role_required("admin", "superadmin")
def novo_entregador():
    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        link_avaliacao_base = request.form.get("link_avaliacao_base")

        if not nome or not telefone:
            flash("Nome e telefone são obrigatórios.", "danger")
            return redirect(url_for("novo_entregador"))

        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO entregadores (nome, telefone_whatsapp, link_avaliacao_base, ativo)
            VALUES (?, ?, ?, 1)
            """,
            (nome, telefone, link_avaliacao_base),
        )
        db.commit()
        flash("Entregador cadastrado com sucesso!", "success")
        return redirect(url_for("listar_entregadores"))

    return render_template("entregadores_novo.html")


# ---------------- GESTÃO DE MENSAGENS (ADMIN + SUPERADMIN) ----------------

@app.route("/admin/mensagens")
@login_required
@role_required("admin", "superadmin")
def listar_mensagens():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM mensagens_modelo WHERE ativa = 1")
    mensagens = cur.fetchall()
    return render_template("mensagens_listar.html", mensagens=mensagens)


@app.route("/admin/mensagens/novo", methods=["GET", "POST"])
@login_required
@role_required("admin", "superadmin")
def nova_mensagem():
    if request.method == "POST":
        titulo = request.form.get("titulo")
        corpo_texto = request.form.get("corpo_texto")

        if not titulo or not corpo_texto:
            flash("Preencha título e corpo da mensagem.", "danger")
            return redirect(url_for("nova_mensagem"))

        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO mensagens_modelo (titulo, corpo_texto, ativa)
            VALUES (?, ?, 1)
            """,
            (titulo, corpo_texto),
        )
        db.commit()
        flash("Mensagem modelo cadastrada!", "success")
        return redirect(url_for("listar_mensagens"))

    return render_template("mensagens_novo.html")


# ---------------- TELA DO CAIXA (ENVIO) ----------------

@app.route("/caixa/enviar", methods=["GET", "POST"])
@login_required
@role_required("caixa", "admin", "superadmin")
def caixa_enviar():
    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        nome_cliente = request.form.get("nome_cliente")
        telefone_cliente = request.form.get("telefone_cliente")
        id_entregador = request.form.get("id_entregador")
        id_mensagem = request.form.get("id_mensagem")

        if not nome_cliente or not telefone_cliente or not id_entregador or not id_mensagem:
            flash("Preencha todos os campos.", "danger")
            return redirect(url_for("caixa_enviar"))

        # Busca entregador
        cur.execute("SELECT * FROM entregadores WHERE id = ? AND ativo = 1", (id_entregador,))
        entregador = cur.fetchone()
        if not entregador:
            flash("Entregador inválido.", "danger")
            return redirect(url_for("caixa_enviar"))

        # Busca mensagem modelo
        cur.execute("SELECT * FROM mensagens_modelo WHERE id = ? AND ativa = 1", (id_mensagem,))
        msg_modelo = cur.fetchone()
        if not msg_modelo:
            flash("Mensagem inválida.", "danger")
            return redirect(url_for("caixa_enviar"))

        nome_entregador = entregador["nome"]
        # Link de avaliação: se tiver específico no entregador, usa. Senão, poderia usar um padrão
        link_avaliacao = entregador["link_avaliacao_base"] or "https://seusite.com/avaliar"

        # Monta a mensagem
        corpo = msg_modelo["corpo_texto"]
        mensagem_final = (
            corpo.replace("{{nome_cliente}}", nome_cliente)
                 .replace("{{nome_entregador}}", nome_entregador)
                 .replace("{{link_avaliacao}}", link_avaliacao)
        )

        # Envia WhatsApp (simulado)
        sucesso, retorno = enviar_whatsapp(telefone_cliente, mensagem_final)

        # Salva log
        data_hora = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
        cur.execute(
            """
            INSERT INTO envios_whatsapp
            (id_usuario, id_entregador, nome_cliente, telefone_cliente,
             mensagem_enviada, data_hora, status, retorno_api)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.get("user_id"),
                id_entregador,
                nome_cliente,
                telefone_cliente,
                mensagem_final,
                data_hora,
                "enviado" if sucesso else "erro",
                retorno,
            ),
        )
        db.commit()

        if sucesso:
            flash("Mensagem enviada com sucesso!", "success")
        else:
            flash("Erro ao enviar a mensagem.", "danger")

        return redirect(url_for("caixa_enviar"))

    # GET - carrega lista de entregadores e mensagens
    cur.execute("SELECT * FROM entregadores WHERE ativo = 1")
    entregadores = cur.fetchall()
    cur.execute("SELECT * FROM mensagens_modelo WHERE ativa = 1")
    mensagens = cur.fetchall()

    return render_template(
        "caixa_enviar.html",
        entregadores=entregadores,
        mensagens=mensagens,
    )


# ---------------- RELATÓRIO DE ENVIOS (SUPERADMIN + ADMIN) ----------------

@app.route("/relatorios/envios")
@login_required
@role_required("admin", "superadmin")
def relatorios_envios():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT e.*, u.nome AS nome_usuario, d.nome AS nome_entregador
        FROM envios_whatsapp e
        LEFT JOIN usuarios u ON u.id = e.id_usuario
        LEFT JOIN entregadores d ON d.id = e.id_entregador
        ORDER BY e.id DESC
        LIMIT 200
        """
    )
    envios = cur.fetchall()
    return render_template("relatorios_envios.html", envios=envios)


# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
