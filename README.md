# Chat en Tiempo Real - Backend


###  Base de Datos
```sql
USE sistemasic_chat_python;

-- Crear tabla de mensajes
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

-- Crear índices
CREATE INDEX idx_timestamp ON mensajes(timestamp DESC);
CREATE INDEX idx_usuario ON mensajes(usuario);

-- Tabla de usuarios (para panel lateral de admin)
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    estado VARCHAR(50) DEFAULT 'N/D',
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
