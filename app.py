from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_session import Session
import sqlite3
import requests
import urllib.parse
from datetime import datetime, timedelta
import threading
import time
from functools import wraps

app = Flask(__name__)
app.secret_key = 'chave_super_secreta'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

DATABASE = 'database.db'

# ----------------------------- DB -----------------------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS instagram_oauth_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                client_secret TEXT NOT NULL,
                redirect_uri TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS instagram_oauth (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ig_user_id TEXT,
                ig_username TEXT,
                access_token TEXT,
                token_expires_at TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')
        conn.execute("INSERT OR IGNORE INTO users (id, username, password) VALUES (1, ?, ?)", ('admin', 'admin123'))
        count = conn.execute('SELECT COUNT(*) as count FROM instagram_oauth_config').fetchone()['count']
        if count == 0:
            conn.execute("INSERT INTO instagram_oauth_config (client_id, client_secret, redirect_uri) VALUES (?, ?, ?)",
                         ('', '', ''))
        conn.commit()
    finally:
        conn.close()

init_db()

# ----------------------------- LOG -----------------------------
def log(level, message):
    conn = get_db_connection()
    conn.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
                 (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), level, message))
    conn.commit()
    conn.close()

# ----------------------------- Decorator -----------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ----------------------------- HELPERS -----------------------------
def get_instagram_oauth_config():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM instagram_oauth_config LIMIT 1').fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_oauth_status():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM instagram_oauth LIMIT 1').fetchone()
    conn.close()
    if not row:
        return ('not_connected', None)
    if not row['access_token']:
        return ('not_connected', None)
    return ('connected', dict(row))

# ----------------------------- ROTAS -----------------------------

@app.route('/')
@login_required
def dashboard():
    status, token_data = get_oauth_status()
    return render_template('dashboard.html', oauth_status=status, token_data=token_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (u, p)).fetchone()
        conn.close()
        if user:
            session['user'] = u
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha incorretos!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/instagram_oauth_config', methods=['GET', 'POST'])
@login_required
def instagram_oauth_config():
    conn = get_db_connection()
    if request.method == 'POST':
        client_id = request.form['client_id'].strip()
        client_secret = request.form['client_secret'].strip()
        redirect_uri = request.form['redirect_uri'].strip()
        conn.execute('UPDATE instagram_oauth_config SET client_id = ?, client_secret = ?, redirect_uri = ? WHERE id = 1',
                     (client_id, client_secret, redirect_uri))
        conn.commit()
        flash('Configurações salvas com sucesso!', 'success')
        log('INFO', 'Configurações OAuth atualizadas')
        return redirect(url_for('dashboard'))
    row = conn.execute('SELECT * FROM instagram_oauth_config LIMIT 1').fetchone()
    conn.close()
    return render_template('instagram_oauth_config.html', config=row)

@app.route('/instagram_oauth_start')
@login_required
def instagram_oauth_start():
    config = get_instagram_oauth_config()
    if not config:
        flash('Configuração OAuth não encontrada!', 'error')
        return redirect(url_for('dashboard'))
    auth_url = (
        'https://api.instagram.com/oauth/authorize'
        '?client_id={client_id}&redirect_uri={redirect_uri}&scope=user_profile,user_media&response_type=code'
    ).format(
        client_id=urllib.parse.quote(config['client_id']),
        redirect_uri=urllib.parse.quote(config['redirect_uri'])
    )
    return redirect(auth_url)

@app.route('/instagram_oauth_callback')
@login_required
def instagram_oauth_callback():
    code = request.args.get('code')
    if not code:
        flash('Erro: código OAuth não recebido', 'error')
        return redirect(url_for('dashboard'))

    config = get_instagram_oauth_config()
    token_url = 'https://api.instagram.com/oauth/access_token'
    data = {
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'grant_type': 'authorization_code',
        'redirect_uri': config['redirect_uri'],
        'code': code
    }
    resp = requests.post(token_url, data=data)
    if resp.status_code != 200:
        flash('Erro ao trocar código por token', 'error')
        log('ERROR', 'Falha OAuth: ' + resp.text)
        return redirect(url_for('dashboard'))

    token_data = resp.json()
    access_token = token_data.get('access_token')
    user_id = token_data.get('user_id')
    if not access_token:
        flash('Token não recebido!', 'error')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    conn.execute('DELETE FROM instagram_oauth')
    conn.execute('INSERT INTO instagram_oauth (ig_user_id, access_token) VALUES (?, ?)',
                 (user_id, access_token))
    conn.commit()
    conn.close()
    flash('Conta conectada com sucesso via OAuth!', 'success')
    log('INFO', 'Token OAuth salvo com sucesso')
    return redirect(url_for('dashboard'))

@app.route('/logs')
@login_required
def logs():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 100').fetchall()
    conn.close()
    return render_template('logs.html', logs=rows)

@app.route('/logs/delete', methods=['POST'])
@login_required
def delete_logs():
    conn = get_db_connection()
    conn.execute('DELETE FROM logs')
    conn.commit()
    conn.close()
    flash('Logs apagados com sucesso!', 'success')
    return redirect(url_for('logs'))

# ----------------------------- Run -----------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
