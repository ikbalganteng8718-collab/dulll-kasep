from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import random
import string
import zipfile
import io
import hashlib
import time

app = Flask(__name__)
CORS(app)

TURSO_URL = "https://dulll-dull.aws-ap-southeast-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJleHAiOjE4MjU5NTgxNDAsImlhdCI6MTc5NDQyMjE0MCwiaWQiOiIwMWExY2I2Mi0yMjAxLTdlNjAtODM5NC01NTE1ZmY0YmIzNTAiLCJraWQiOiJEcnl5QVM3MGlIcVZ4YmZvcVkwcjhzaTRhcXUwQjlsVXhYbXl5X21oc1l3IiwicmlkIjoiMTYwMzczZjktOTg1MC00YWExLWJjOGQtMDU0ZDg1MDE4ZDJmIn0.ri6aHHSahAM3N23hUetTZN_bckNNbC9jaQHElGu5-Zws_Vsc2tXU6_IMXvkNRPOf4i3_UksLmourFOA_rngTDw"

NETLIFY_TOKEN = "nfp_MWXVdnz7ngVEHwD73Uoxs44ZmApjthQKd1eb" 

def _to_arg(v):
    if v is None: return {"type": "null"}
    if isinstance(v, int): return {"type": "integer", "value": str(v)}
    if isinstance(v, float): return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}

def execute_query(sql, args=None):
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    formatted_args = [_to_arg(a) for a in args] if args else []
    payload = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": formatted_args}}, {"type": "close"}]}
    response = requests.post(f"{TURSO_URL}/v2/pipeline", headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    try:
        # Tabel Users
        execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                is_admin INTEGER DEFAULT 0
            )
        """)
        # Tabel Visits (Log Masuk Web)
        execute_query("""
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                ip TEXT,
                device TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Tabel Chat
        execute_query("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        execute_query("CREATE TABLE IF NOT EXISTS public_servers (server_id TEXT PRIMARY KEY, api_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

        # Bikin Admin Default (admin / admin)
        res = execute_query("SELECT * FROM users WHERE username = 'admin'")
        if not res['results'][0]['response']['result']['rows']:
            execute_query("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)", ["admin", hash_password("admin")])
            
    except Exception as e: print(f"DB Error: {e}")

@app.route('/')
def home(): return render_template('index.html')

# === FITUR REGISTER ===
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password: return jsonify({"status": "error", "message": "Username/Password kosong"}), 400

    try:
        # Cek username udah ada apa belum
        res = execute_query("SELECT * FROM users WHERE username = ?", [username])
        if res['results'][0]['response']['result']['rows']:
            return jsonify({"status": "error", "message": "Username sudah dipakai!"}), 400

        execute_query("INSERT INTO users (username, password_hash) VALUES (?, ?)", [username, hash_password(password)])
        return jsonify({"status": "success", "message": "Registrasi berhasil! Silakan login."})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# === FITUR LOGIN ===
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    try:
        res = execute_query("SELECT username, password_hash, is_admin FROM users WHERE username = ?", [username])
        rows = res['results'][0]['response']['result']['rows']
        
        if not rows:
            return jsonify({"status": "error", "message": "Username tidak ditemukan!"}), 401
        
        db_user = rows[0][0]['value']
        db_pass = rows[0][1]['value']
        is_admin = rows[0][2]['value'] == '1'

        if hash_password(password) == db_pass:
            return jsonify({"status": "success", "username": db_user, "is_admin": is_admin})
        else:
            return jsonify({"status": "error", "message": "Password salah!"}), 401
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# === LOG VISIT (Catat yang masuk) ===
@app.route('/api/log_visit', methods=['POST'])
def log_visit():
    data = request.json
    username = data.get('username')
    ip = data.get('ip')
    device = data.get('device')
    try:
        execute_query("INSERT INTO visits (username, ip, device) VALUES (?, ?, ?)", [username, ip, device])
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error"}), 500

# === ADMIN ENDPOINTS ===
def check_admin():
    auth = request.headers.get('Authorization')
    if not auth: return False
    username = auth.replace('Bearer ', '')
    try:
        res = execute_query("SELECT is_admin FROM users WHERE username = ?", [username])
        rows = res['results'][0]['response']['result']['rows']
        return rows and rows[0][0]['value'] == '1'
    except: return False

@app.route('/api/admin/visits', methods=['GET'])
def admin_visits():
    if not check_admin(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        res = execute_query("SELECT username, ip, device, timestamp FROM visits ORDER BY id DESC LIMIT 50")
        rows = res['results'][0]['response']['result']['rows']
        data = [{"username": r[0]['value'], "ip": r[1]['value'], "device": r[2]['value'], "time": r[3]['value']} for r in rows]
        return jsonify({"status": "success", "data": data})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/chats', methods=['GET'])
def admin_chats():
    if not check_admin(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        res = execute_query("SELECT sender, message, created_at FROM chat_messages ORDER BY id DESC LIMIT 100")
        rows = res['results'][0]['response']['result']['rows']
        data = [{"sender": r[0]['value'], "message": r[1]['value'], "time": r[2]['value']} for r in rows]
        return jsonify({"status": "success", "data": data})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# === FITUR CHAT & LAINNYA (Sama kayak sebelumnya) ===
@app.route('/api/chat/send', methods=['POST'])
def send_chat():
    data = request.json
    sender = data.get('sender', 'Anonim')
    message = data.get('message', '')
    if not message: return jsonify({"status": "error"}), 400
    try:
        execute_query("INSERT INTO chat_messages (sender, message) VALUES (?, ?)", [sender, message])
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/chat/messages', methods=['GET'])
def get_chat():
    try:
        res = execute_query("SELECT sender, message, created_at FROM chat_messages ORDER BY id DESC LIMIT 50")
        rows = res['results'][0]['response']['result']['rows']
        messages = []
        for row in reversed(rows):
            messages.append({"sender": row[0]['value'], "message": row[1]['value'], "time": row[2]['value']})
        return jsonify({"status": "success", "messages": messages})
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/chat/users', methods=['GET'])
def get_chat_users():
    try:
        res = execute_query("SELECT DISTINCT sender FROM chat_messages")
        rows = res['results'][0]['response']['result']['rows']
        users = [{"username": row[0]['value']} for row in rows]
        return jsonify({"status": "success", "users": users})
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/create_server', methods=['POST'])
def create_server():
    data = request.json
    api_name = data.get('api_name', '').lower().replace(' ', '-')
    if not api_name: return jsonify({"status": "error"}), 400
    server_id = f"{api_name}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}"
    try:
        execute_query("INSERT INTO public_servers (server_id, api_name) VALUES (?, ?)", [server_id, api_name])
        return jsonify({"status": "success", "server_id": server_id})
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/public/<server_id>', methods=['GET'])
def public_api(server_id):
    try:
        res = execute_query("SELECT api_name FROM public_servers WHERE server_id = ?", [server_id])
        rows = res['results'][0]['response']['result']['rows']
        if rows: return jsonify({"status": "success", "creator": "Z×ice lanz dulll", "api_name": rows[0][0]['value']})
        return jsonify({"status": "error"}), 404
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/deploy_web', methods=['POST'])
def deploy_web():
    data = request.json
    subdomain = data.get('subdomain', '').lower().replace(' ', '-')
    html = data.get('html', '')
    if not subdomain or not html: return jsonify({"status": "error"}), 400
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('index.html', html) 
    zip_buffer.seek(0)
    headers_auth = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    try:
        site_res = requests.post("https://api.netlify.com/api/v1/sites", headers={**headers_auth, "Content-Type": "application/json"}, json={"name": subdomain})
        site_data = site_res.json()
        if site_res.status_code != 201: return jsonify({"status": "error", "message": "Nama subdomain dipakai."}), 400
        site_id = site_data['id']
        site_url = site_data['ssl_url'] 
        deploy_res = requests.post(f"https://api.netlify.com/api/v1/sites/{site_id}/deploys", headers={**headers_auth, "Content-Type": "application/zip"}, data=zip_buffer.getvalue())
        if deploy_res.status_code in [200, 201]: return jsonify({"status": "success", "url": site_url})
        else: return jsonify({"status": "error"}), 500
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/web_to_code', methods=['POST'])
def web_to_code():
    url = request.json.get('url')
    if not url: return jsonify({"status": "error"}), 400
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        return jsonify({"status": "success", "html": res.text})
    except Exception as e: return jsonify({"status": "error"}), 500

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
