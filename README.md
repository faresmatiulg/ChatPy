# Chat en Tiempo Real - Backend


###  Base de Datos (nuevo esquema de sesiones y chats)
```sql
USE sistemasic_chat_python;

-- Usuarios (login por nombre)
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    role ENUM('admin','user') DEFAULT 'user',
    estado VARCHAR(50) DEFAULT 'N/D',
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chats (general o dm)
CREATE TABLE IF NOT EXISTS chats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type ENUM('general','dm') NOT NULL,
    name VARCHAR(120),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Participantes del chat
CREATE TABLE IF NOT EXISTS chat_participants (
    chat_id INT NOT NULL,
    user_id INT NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_chat_user (chat_id, user_id),
    INDEX idx_user (user_id)
);

-- Mensajes v2 (por chat)
CREATE TABLE IF NOT EXISTS mensajes_v2 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chat_id INT NOT NULL,
    sender_id INT NOT NULL,
    contenido TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_chat_time (chat_id, timestamp)
);

-- Chat general (semilla)
INSERT INTO chats (type, name)
SELECT 'general','General' WHERE NOT EXISTS (SELECT 1 FROM chats WHERE type='general');

-- Esquema anterior (legacy) – opcional mantener para histórico
-- Crear tabla de mensajes (legacy)
CREATE TABLE IF NOT EXISTS mensajes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    mensaje TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT,
    tipo_usuario VARCHAR(20) DEFAULT 'cliente', -- 'cliente' o 'admin'
    destinatario VARCHAR(100) NULL
);

CREATE OR REPLACE VIEW mensajes_recientes AS
SELECT 
    id,
    usuario,
    mensaje,
    timestamp,
    DATE_FORMAT(timestamp, '%H:%i:%s') as hora
FROM mensajes 
ORDER BY timestamp DESC 
LIMIT 50;

-- Crear índices legacy
CREATE INDEX idx_timestamp ON mensajes(timestamp DESC);
CREATE INDEX idx_usuario ON mensajes(usuario);

-- Migraciones rápidas si ya tienes la tabla mensajes sin columna tipo_usuario
-- (ejecuta solo si la columna no existe)
-- ALTER TABLE mensajes ADD COLUMN tipo_usuario VARCHAR(20) DEFAULT 'cliente' AFTER user_agent;
-- Para conversaciones privadas (si la columna no existe)
-- ALTER TABLE mensajes ADD COLUMN destinatario VARCHAR(100) NULL AFTER tipo_usuario;
```


## 📝 Notas

- El chat funciona con o sin Pusher
- Si Pusher no está disponible, usa polling cada 3 segundos
- La zona horaria está configurada para Lima, Perú
- Los mensajes se almacenan en MySQL con charset utf8mb4
- Cuando un usuario envía su primer mensaje, se inserta automáticamente en `usuarios`
- Para conversaciones privadas del admin: usa `destinatario` y filtra con `GET /api/messages?usuario=<nombre>`
- Nuevo flujo recomendado: usar `usuarios`, `chats`, `chat_participants` y `mensajes_v2` para bandeja y DMs

### Endpoints (nuevo flujo)

Autenticación sin contraseña:
- POST `/api/login` { username } → crea/retorna usuario (admin si username='admin')
- GET `/api/me` ?username=… o header `X-Username`
- POST `/api/logout` → stateless (frontend limpia sesión)

Chats y bandeja:
- GET `/api/chats` ?username=… →
  - admin: [General + DM con cada usuario]
  - user: [General + DM con admin]
- POST `/api/chats/dm` { username, with_username }

Mensajes por chat:
- GET `/api/messages?chat_id=ID` → lista mensajes del chat (v2)
- POST `/api/messages` { chat_id, contenido, username } → agrega mensaje v2

Compatibilidad (legacy):
- GET `/api/messages` sin `chat_id` devuelve el chat General (v2)
- GET `/api/messages?usuario=nombre` resuelve el chat DM entre `username` (en query o header) y `nombre`
- POST `/api/send` guarda en el chat General (v2) usando el `usuario` legacy
