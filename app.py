from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
import os
from datetime import datetime
import pytz
import pusher
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

peru_tz = pytz.timezone('America/Lima')

# Configuración de Pusher para tiempo real
pusher_client = None
pusher_enabled = False

pusher_app_id = os.environ.get('PUSHER_APP_ID')
pusher_key = os.environ.get('PUSHER_KEY')
pusher_secret = os.environ.get('PUSHER_SECRET')
pusher_cluster = os.environ.get('PUSHER_CLUSTER', 'us2')

if pusher_app_id and pusher_key and pusher_secret and pusher_app_id != 'your_app_id':
    pusher_client = pusher.Pusher(
        app_id=pusher_app_id,
        key=pusher_key,
        secret=pusher_secret,
        cluster=pusher_cluster,
        ssl=True
    )
    pusher_enabled = True

def get_db_connection():
    connection = mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'mysql-sistemasic.alwaysdata.net'),
        database=os.environ.get('DB_NAME', 'sistemasic_chat-python'),
        user=os.environ.get('DB_USER', '436286'),
        password=os.environ.get('DB_PASS', 'brayan933783039'),
        port=int(os.environ.get('DB_PORT', '3306')),
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci'
    )
    
    cursor = connection.cursor()
    cursor.execute("SET time_zone = '-05:00'")
    cursor.close()
    return connection

def ensure_schema():
    connection = get_db_connection()
    cursor = connection.cursor()
    # Crear tablas si no existen (usuarios, chats, chat_participants, mensajes_v2)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            role ENUM('admin','user') DEFAULT 'user',
            estado VARCHAR(50) DEFAULT 'N/D',
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id INT AUTO_INCREMENT PRIMARY KEY,
            type ENUM('general','dm') NOT NULL,
            name VARCHAR(120),
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_participants (
            chat_id INT NOT NULL,
            user_id INT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_chat_user (chat_id, user_id),
            INDEX idx_user (user_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mensajes_v2 (
            id INT AUTO_INCREMENT PRIMARY KEY,
            chat_id INT NOT NULL,
            sender_id INT NOT NULL,
            contenido TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_chat_time (chat_id, timestamp)
        )
        """
    )

    # Crear chat general si no existe
    cursor.execute("SELECT id FROM chats WHERE type='general' LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO chats (type, name) VALUES ('general', 'General')")
        connection.commit()

    cursor.close()
    connection.close()

ensure_schema()

def get_or_create_user(username: str):
    username = (username or '').strip()
    if not username:
        return None
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    role = 'admin' if username.lower() == 'admin' else 'user'
    # upsert
    cursor.execute("SELECT id, username, role FROM usuarios WHERE username=%s", (username,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO usuarios (username, role) VALUES (%s, %s)", (username, role))
        connection.commit()
        user_id = cursor.lastrowid
        row = {'id': user_id, 'username': username, 'role': role}
    else:
        # elevar a admin si corresponde
        if role == 'admin' and row.get('role') != 'admin':
            cursor.execute("UPDATE usuarios SET role='admin' WHERE id=%s", (row['id'],))
            connection.commit()
            row['role'] = 'admin'
    cursor.close()
    connection.close()
    return row

def get_general_chat_id():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM chats WHERE type='general' LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO chats (type, name) VALUES ('general', 'General')")
        connection.commit()
        chat_id = cursor.lastrowid
    else:
        chat_id = row[0]
    cursor.close()
    connection.close()
    return chat_id

def get_user_by_username(username: str):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, username, role FROM usuarios WHERE username=%s", (username,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    return row

def get_or_create_dm_chat(user_a_id: int, user_b_id: int):
    if not user_a_id or not user_b_id:
        return None
    if user_a_id == user_b_id:
        return None
    a, b = sorted([user_a_id, user_b_id])
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    # Buscar chat dm que contenga a ambos
    cursor.execute(
        """
        SELECT c.id FROM chats c
        JOIN chat_participants p1 ON p1.chat_id=c.id AND p1.user_id=%s
        JOIN chat_participants p2 ON p2.chat_id=c.id AND p2.user_id=%s
        WHERE c.type='dm' LIMIT 1
        """,
        (a, b)
    )
    row = cursor.fetchone()
    if row:
        chat_id = row['id']
    else:
        cursor.execute("INSERT INTO chats (type, name) VALUES ('dm', NULL)")
        connection.commit()
        chat_id = cursor.lastrowid
        cursor.execute("INSERT IGNORE INTO chat_participants (chat_id, user_id) VALUES (%s, %s)", (chat_id, a))
        cursor.execute("INSERT IGNORE INTO chat_participants (chat_id, user_id) VALUES (%s, %s)", (chat_id, b))
        connection.commit()
    cursor.close()
    connection.close()
    return chat_id

@app.route('/api/chats', methods=['GET'])
def list_chats():
    current_username = (request.args.get('username') or request.headers.get('X-Username') or '').strip()
    if not current_username:
        return jsonify({'error': 'username requerido'}), 400
    current_user = get_or_create_user(current_username)
    general_id = get_general_chat_id()
    chats = [{ 'id': general_id, 'type': 'general', 'name': 'General' }]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if current_user['role'] == 'admin':
        # Obtener todos los usuarios excepto admin y crear dm si no existe
        cursor.execute("SELECT id, username FROM usuarios WHERE username <> 'admin' ORDER BY username ASC")
        users = cursor.fetchall()
        for u in users:
            dm_id = get_or_create_dm_chat(current_user['id'], u['id'])
            chats.append({ 'id': dm_id, 'type': 'dm', 'name': u['username'] })
    else:
        # Asegurar dm con admin
        cursor.execute("SELECT id FROM usuarios WHERE username='admin' LIMIT 1")
        admin_row = cursor.fetchone()
        if admin_row:
            dm_id = get_or_create_dm_chat(current_user['id'], admin_row['id'])
            chats.append({ 'id': dm_id, 'type': 'dm', 'name': 'Administrador' })

    cursor.close()
    connection.close()
    return jsonify({'chats': chats}), 200

@app.route('/api/chats/dm', methods=['POST'])
def create_dm():
    data = request.get_json() or {}
    current_username = (data.get('username') or request.headers.get('X-Username') or '').strip()
    with_username = (data.get('with_username') or '').strip()
    if not current_username or not with_username:
        return jsonify({'error': 'username y with_username requeridos'}), 400
    current_user = get_or_create_user(current_username)
    other_user = get_or_create_user(with_username)
    chat_id = get_or_create_dm_chat(current_user['id'], other_user['id'])
    return jsonify({'chat': { 'id': chat_id, 'type': 'dm', 'name': other_user['username'] }}), 200

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({'error': 'username requerido'}), 400
    user = get_or_create_user(username)
    return jsonify({'user': user}), 200

@app.route('/api/me', methods=['GET'])
def api_me():
    username = (request.args.get('username') or request.headers.get('X-Username') or '').strip()
    if not username:
        return jsonify({'user': None}), 200
    user = get_or_create_user(username)
    return jsonify({'user': user}), 200

@app.route('/api/logout', methods=['POST'])
def api_logout():
    # Stateless: el frontend limpia localStorage
    return jsonify({'success': True}), 200

@app.route('/api/send', methods=['POST'])
def send_message():
    # Compatibilidad: si llaman este endpoint legacy, guardar en chat general en v2
    data = request.get_json() or {}
    usuario = (data.get('usuario') or '').strip()
    mensaje = (data.get('mensaje') or '').strip()
    if not usuario or not mensaje:
        return jsonify({'error': 'usuario y mensaje requeridos'}), 400

    user = get_or_create_user(usuario)
    chat_id = get_general_chat_id()

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO mensajes_v2 (chat_id, sender_id, contenido) VALUES (%s, %s, %s)",
        (chat_id, user['id'], mensaje)
    )
    connection.commit()
    message_id = cursor.lastrowid
    cursor.close()
    connection.close()

    if pusher_enabled and pusher_client:
        pusher_client.trigger('chat', 'new-message', {
            'id': message_id,
            'usuario': user['username'],
            'mensaje': mensaje,
            'chat_id': chat_id,
            'tipo_usuario': 'admin' if user['role']=='admin' else 'cliente'
        })

    return jsonify({'success': True, 'id': message_id}), 200

@app.route('/api/messages', methods=['GET'])
def get_messages():
    # Nuevo flujo por chat_id (v2)
    chat_id = request.args.get('chat_id', default=None, type=int)
    usuario_filtro = request.args.get('usuario', default=None, type=str)

    # Compat: si viene ?usuario, mapear al DM correspondiente
    if not chat_id and usuario_filtro:
        # Resolver usuario actual (si se envía por header/query)
        current_username = (request.args.get('username') or request.headers.get('X-Username') or '').strip()
        other_username = usuario_filtro.strip()
        if current_username and other_username:
            me = get_or_create_user(current_username)
            other = get_or_create_user(other_username)
            chat_id = get_or_create_dm_chat(me['id'], other['id'])

    if chat_id:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT sender_id, contenido as mensaje, timestamp, sender_id FROM mensajes_v2 WHERE chat_id=%s ORDER BY timestamp ASC LIMIT 500",
            (chat_id,)
        )
        rows = cursor.fetchall()
        # Mapear sender_id -> username
        sender_ids = list({ r['sender_id'] for r in rows }) or [0]
        format_ids = ','.join(['%s'] * len(sender_ids))
        cursor.execute(f"SELECT id, username FROM usuarios WHERE id IN ({format_ids})", tuple(sender_ids))
        id_to_username = { r['id']: r['username'] for r in cursor.fetchall() }
        mensajes = []
        for r in rows:
            ts = r['timestamp'].replace(tzinfo=pytz.UTC).astimezone(peru_tz).strftime('%I:%M %p') if r['timestamp'] else ''
            mensajes.append({
                'usuario': id_to_username.get(r['sender_id'], 'Desconocido'),
                'mensaje': r['mensaje'],
                'timestamp': ts,
                'tipo_usuario': 'admin' if id_to_username.get(r['sender_id'], '').lower() == 'admin' else 'cliente'
            })
        cursor.close()
        connection.close()
        return jsonify({'messages': mensajes}), 200

    # Legacy sin chat_id: devolver chat general (v2)
    general_id = get_general_chat_id()
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT sender_id, contenido as mensaje, timestamp, sender_id FROM mensajes_v2 WHERE chat_id=%s ORDER BY timestamp ASC LIMIT 500",
        (general_id,)
    )
    rows = cursor.fetchall()
    sender_ids = list({ r['sender_id'] for r in rows }) or [0]
    format_ids = ','.join(['%s'] * len(sender_ids))
    cursor.execute(f"SELECT id, username FROM usuarios WHERE id IN ({format_ids})", tuple(sender_ids))
    id_to_username = { r['id']: r['username'] for r in cursor.fetchall() }
    mensajes = []
    for r in rows:
        ts = r['timestamp'].replace(tzinfo=pytz.UTC).astimezone(peru_tz).strftime('%I:%M %p') if r['timestamp'] else ''
        mensajes.append({
            'usuario': id_to_username.get(r['sender_id'], 'Desconocido'),
            'mensaje': r['mensaje'],
            'timestamp': ts,
            'tipo_usuario': 'admin' if id_to_username.get(r['sender_id'], '').lower() == 'admin' else 'cliente'
        })
    cursor.close()
    connection.close()
    return jsonify({'messages': mensajes}), 200

@app.route('/api/messages', methods=['POST'])
def post_message_v2():
    data = request.get_json() or {}
    chat_id = data.get('chat_id')
    contenido = (data.get('contenido') or data.get('mensaje') or '').strip()
    username = (data.get('username') or data.get('usuario') or '').strip()
    if chat_id:
        user = get_or_create_user(username)
        if not user:
            return jsonify({'error': 'usuario requerido'}), 400
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO mensajes_v2 (chat_id, sender_id, contenido) VALUES (%s, %s, %s)", (chat_id, user['id'], contenido))
        connection.commit()
        msg_id = cursor.lastrowid
        cursor.close()
        connection.close()

        if pusher_enabled and pusher_client:
            pusher_client.trigger('chat', 'new-message', {
                'id': msg_id,
                'usuario': user['username'],
                'mensaje': contenido,
                'chat_id': chat_id,
                'tipo_usuario': 'admin' if user['role']=='admin' else 'cliente'
            })
        return jsonify({'success': True, 'id': msg_id}), 200

    # Si no hay chat_id, redirigir al legacy /api/send
    return send_message()

# Endpoint para listar usuarios (desde tabla usuarios si existe; si no, DISTINCT de mensajes)
@app.route('/api/users', methods=['GET'])
def list_users():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    usuarios = []
    try:
        # Intentar leer desde tabla usuarios estándar
        cursor.execute("SELECT id, nombre, estado FROM usuarios ORDER BY nombre ASC")
        usuarios = cursor.fetchall()
        # Normalizar claves si es necesario
        usuarios = [
            {
                'id': u.get('id'),
                'nombre': u.get('nombre'),
                'estado': u.get('estado') or 'Desconocido'
            }
            for u in usuarios
        ]
    except Exception:
        # Fallback: derivar de mensajes
        try:
            cursor2 = connection.cursor()
            cursor2.execute("SELECT DISTINCT usuario FROM mensajes WHERE usuario IS NOT NULL AND usuario <> '' ORDER BY usuario ASC LIMIT 200")
            nombres = [row[0] for row in cursor2.fetchall()]
            cursor2.close()
            usuarios = [
                {'id': idx + 1, 'nombre': nombre, 'estado': 'N/D'}
                for idx, nombre in enumerate(nombres)
            ]
        finally:
            pass
    finally:
        cursor.close()
        connection.close()

    return jsonify({'users': usuarios}), 200

@app.route('/api/pusher/config', methods=['GET'])
def pusher_config():
    if pusher_enabled:
        return jsonify({
            'enabled': True,
            'key': pusher_key,
            'cluster': pusher_cluster
        })
    else:
        return jsonify({'enabled': False})

@app.route('/api/pusher/auth', methods=['POST'])
def pusher_authentication():
    socket_id = request.form['socket_id']
    channel_name = request.form['channel_name']
    
    auth = pusher_client.authenticate(channel=channel_name, socket_id=socket_id)
    return jsonify(auth)

# Endpoint para limpiar todos los mensajes
@app.route('/api/clear-messages', methods=['POST'])
def clear_messages():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM mensajes")
    connection.commit()
    
    deleted_count = cursor.rowcount
    cursor.close()
    connection.close()
    
    return jsonify({
        'success': True, 
        'message': f'Deleted {deleted_count} messages',
        'deleted_count': deleted_count
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'OK', 'message': 'Server running'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
