from flask import Flask, request, jsonify
from flask_cors import CORS
import pusher
import mysql.connector
import os

app = Flask(__name__)
CORS(app)

# --- Configuración de Pusher ---
pusher_client = pusher.Pusher(
    app_id='2064483',
    key='ebff80d16de6cdb1443e',
    secret='b1ae5b9b7f6a2365b73c',
    cluster='us2',
    ssl=True
)

# --- Configuración de la base de datos (AlwaysData) ---
db_config = {
    'host': 'mysql-chatpy.alwaysdata.net',  # cambia por tu host exacto
    'user': 'chat_user',                    # tu usuario MySQL
    'password': 'TU_CONTRASEÑA',            # tu contraseña
    'database': 'chatpy_db'                 # nombre de la BD
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

# --- Ruta para enviar mensaje ---
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    message = data.get('message')
    sender_id = data.get('senderId')

    if not message or not sender_id:
        return jsonify({'error': 'Datos incompletos'}), 400

    # Guardar mensaje en la base de datos
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (sender_id, message) VALUES (%s, %s)", (sender_id, message))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Enviar mensaje por Pusher
    pusher_client.trigger('my-channel', 'my-event', {'message': message, 'senderId': sender_id})

    return jsonify({'status': 'success'})

# --- Ruta para obtener mensajes anteriores ---
@app.route('/get_messages', methods=['GET'])
def get_messages():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM messages ORDER BY timestamp ASC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
