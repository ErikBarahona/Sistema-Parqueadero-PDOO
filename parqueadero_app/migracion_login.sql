-- =====================================================================
--  MIGRACIÓN: agrega el acceso con contraseña a la tabla usuario
--  Ejecutar UNA vez en la base que ya tienes (es seguro repetirla).
--  Usa un usuario con permiso ALTER (por ejemplo admin_parqueadero):
--     mariadb -h 135.148.46.133 -P 3306 -u admin_parqueadero -p parqueadero_db < migracion_login.sql
-- =====================================================================
USE parqueadero_db;

ALTER TABLE usuario
  ADD COLUMN IF NOT EXISTS password_hash     VARCHAR(255) NULL                AFTER rol,
  ADD COLUMN IF NOT EXISTS activo            TINYINT(1) NOT NULL DEFAULT 1    AFTER password_hash,
  ADD COLUMN IF NOT EXISTS intentos_fallidos INT UNSIGNED NOT NULL DEFAULT 0  AFTER activo,
  ADD COLUMN IF NOT EXISTS bloqueado_hasta   DATETIME NULL                    AFTER intentos_fallidos;

-- Después de esto, define la contraseña del administrador existente con:
--     python establecer_password.py
