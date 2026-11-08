-- =====================================================================
--  SISTEMA DE PARQUEADEROS MULTISEDES - Esquema para MariaDB (10.4+)
--  Generado a partir de las clases del proyecto parqueadero_app
-- =====================================================================
--  Ejecutar completo:
--     mariadb -h 135.148.46.133 -P 3306 -u admin_parqueadero -p < parqueadero_mariadb.sql
--  o abrirlo en HeidiSQL / DBeaver y ejecutarlo.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS parqueadero_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE parqueadero_db;

-- Orden de borrado inverso por las llaves foráneas (solo si quieres recrear todo)
-- DROP VIEW  IF EXISTS v_reporte_sedes;
-- DROP TABLE IF EXISTS factura, ingreso, tarifa, espacio, vehiculo, cliente, usuario, parqueadero;

-- ---------------------------------------------------------------------
-- PARQUEADERO (sede)
-- ---------------------------------------------------------------------
CREATE TABLE parqueadero (
  id_parqueadero INT UNSIGNED NOT NULL AUTO_INCREMENT,
  razon_social   VARCHAR(120) NOT NULL,
  ubicacion      VARCHAR(200) NOT NULL,
  capacidad      INT UNSIGNED NOT NULL,
  telefono       VARCHAR(20)  NULL,
  correo         VARCHAR(120) NULL,
  PRIMARY KEY (id_parqueadero),
  CONSTRAINT ck_parqueadero_capacidad CHECK (capacidad > 0)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- USUARIO (operadores y administradores; global a todas las sedes)
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
  id_usuario INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre     VARCHAR(80)  NOT NULL,
  apellido   VARCHAR(80)  NOT NULL,
  cedula     VARCHAR(20)  NULL,
  correo     VARCHAR(120) NULL,
  rol        ENUM('Administrador','Operador') NOT NULL,
  -- Acceso al sistema (la contraseña se guarda como hash, nunca en texto plano)
  password_hash     VARCHAR(255) NULL,
  activo            TINYINT(1) NOT NULL DEFAULT 1,
  intentos_fallidos INT UNSIGNED NOT NULL DEFAULT 0,
  bloqueado_hasta   DATETIME NULL,
  PRIMARY KEY (id_usuario),
  UNIQUE KEY uq_usuario_cedula (cedula),
  UNIQUE KEY uq_usuario_correo (correo)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- CLIENTE (global)
-- ---------------------------------------------------------------------
CREATE TABLE cliente (
  id_cliente INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre     VARCHAR(80)  NOT NULL,
  apellido   VARCHAR(80)  NOT NULL,
  cedula     VARCHAR(20)  NOT NULL,
  telefono   VARCHAR(20)  NULL,
  correo     VARCHAR(120) NULL,
  PRIMARY KEY (id_cliente),
  UNIQUE KEY uq_cliente_cedula (cedula)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- VEHICULO (global). Un cliente tiene 0..* vehículos;
-- un vehículo tiene 0..1 cliente (visitantes sin registrar).
-- ---------------------------------------------------------------------
CREATE TABLE vehiculo (
  id_vehiculo   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  placa         VARCHAR(8)   NOT NULL,
  marca         VARCHAR(60)  NULL,
  color         VARCHAR(40)  NULL,
  tipo_vehiculo ENUM('Carro','Moto','Bicicleta') NOT NULL,
  id_cliente    INT UNSIGNED NULL,
  PRIMARY KEY (id_vehiculo),
  UNIQUE KEY uq_vehiculo_placa (placa),
  KEY ix_vehiculo_cliente (id_cliente),
  CONSTRAINT ck_vehiculo_placa CHECK (placa REGEXP '^[A-Z0-9]{5,8}$'),
  CONSTRAINT fk_vehiculo_cliente FOREIGN KEY (id_cliente)
    REFERENCES cliente (id_cliente)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- ESPACIO (por sede). El código (A-01) puede repetirse entre sedes.
-- ---------------------------------------------------------------------
CREATE TABLE espacio (
  id_espacio     INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_parqueadero INT UNSIGNED NOT NULL,
  codigo         VARCHAR(20)  NOT NULL,
  seccion        VARCHAR(40)  NOT NULL,
  tipo_vehiculo  ENUM('Carro','Moto','Bicicleta') NOT NULL,
  estado         ENUM('Disponible','Ocupado','Mantenimiento') NOT NULL DEFAULT 'Disponible',
  PRIMARY KEY (id_espacio),
  UNIQUE KEY uq_espacio_sede_codigo (id_parqueadero, codigo),
  KEY ix_espacio_busqueda (id_parqueadero, tipo_vehiculo, estado),
  CONSTRAINT fk_espacio_parqueadero FOREIGN KEY (id_parqueadero)
    REFERENCES parqueadero (id_parqueadero)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- TARIFA (por sede). Valores en pesos colombianos (COP).
-- ---------------------------------------------------------------------
CREATE TABLE tarifa (
  id_tarifa      INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_parqueadero INT UNSIGNED NOT NULL,
  tipo_vehiculo  ENUM('Carro','Moto','Bicicleta') NOT NULL,
  precio_hora    INT UNSIGNED NOT NULL,
  precio_dia     INT UNSIGNED NOT NULL,
  fecha_vigencia DATE NOT NULL,
  PRIMARY KEY (id_tarifa),
  KEY ix_tarifa_busqueda (id_parqueadero, tipo_vehiculo, fecha_vigencia),
  CONSTRAINT ck_tarifa_valores CHECK (precio_hora > 0 AND precio_dia > 0),
  CONSTRAINT fk_tarifa_parqueadero FOREIGN KEY (id_parqueadero)
    REFERENCES parqueadero (id_parqueadero)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- INGRESO (estadía). La sede se deduce del espacio.
-- Reglas garantizadas por la BD:
--   * un vehículo no puede tener dos ingresos activos (en ninguna sede)
--   * un espacio no puede tener dos ingresos activos
-- (`activo` vale 1 mientras salida sea NULL y NULL cuando ya salió;
--  los UNIQUE ignoran los NULL, por eso el historial no choca.)
-- ---------------------------------------------------------------------
CREATE TABLE ingreso (
  id_ingreso  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_usuario  INT UNSIGNED NOT NULL,
  id_espacio  INT UNSIGNED NOT NULL,
  id_vehiculo INT UNSIGNED NOT NULL,
  id_tarifa   INT UNSIGNED NOT NULL,
  entrada     DATETIME NOT NULL,
  salida      DATETIME NULL,
  tiempo      DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT 'horas',
  activo      TINYINT AS (IF(salida IS NULL, 1, NULL)) PERSISTENT,
  PRIMARY KEY (id_ingreso),
  UNIQUE KEY uq_ingreso_vehiculo_activo (id_vehiculo, activo),
  UNIQUE KEY uq_ingreso_espacio_activo  (id_espacio, activo),
  KEY ix_ingreso_usuario (id_usuario),
  KEY ix_ingreso_tarifa (id_tarifa),
  KEY ix_ingreso_entrada (entrada),
  CONSTRAINT ck_ingreso_fechas CHECK (salida IS NULL OR salida >= entrada),
  CONSTRAINT fk_ingreso_usuario  FOREIGN KEY (id_usuario)  REFERENCES usuario  (id_usuario)  ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_ingreso_espacio  FOREIGN KEY (id_espacio)  REFERENCES espacio  (id_espacio)  ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_ingreso_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculo (id_vehiculo) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_ingreso_tarifa   FOREIGN KEY (id_tarifa)   REFERENCES tarifa   (id_tarifa)   ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- FACTURA. Un ingreso tiene como máximo una factura.
-- Estado: PENDIENTE si fecha_pago es NULL; PAGADA en caso contrario.
-- El número es consecutivo único en toda la red de sedes.
-- ---------------------------------------------------------------------
CREATE TABLE factura (
  numero      INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'id_factura',
  id_ingreso  INT UNSIGNED NOT NULL,
  fecha       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  horas       INT UNSIGNED NOT NULL,
  total       INT UNSIGNED NOT NULL,
  metodo_pago ENUM('Efectivo','Tarjeta','Transferencia') NULL,
  fecha_pago  DATETIME NULL,
  PRIMARY KEY (numero),
  UNIQUE KEY uq_factura_ingreso (id_ingreso),
  CONSTRAINT ck_factura_pago CHECK (
    (metodo_pago IS NULL AND fecha_pago IS NULL)
    OR (metodo_pago IS NOT NULL AND fecha_pago IS NOT NULL)
  ),
  CONSTRAINT fk_factura_ingreso FOREIGN KEY (id_ingreso)
    REFERENCES ingreso (id_ingreso)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- VISTA: reporte consolidado por sede (equivale a la opción 22 del menú)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reporte_sedes AS
SELECT
  p.id_parqueadero,
  p.razon_social,
  p.ubicacion,
  p.capacidad,
  COUNT(DISTINCT e.id_espacio)                                   AS espacios_registrados,
  COUNT(DISTINCT CASE WHEN e.estado = 'Disponible'    THEN e.id_espacio END) AS libres,
  COUNT(DISTINCT CASE WHEN e.estado = 'Ocupado'       THEN e.id_espacio END) AS ocupados,
  COUNT(DISTINCT CASE WHEN e.estado = 'Mantenimiento' THEN e.id_espacio END) AS en_mantenimiento,
  COALESCE(SUM(CASE WHEN f.fecha_pago IS NOT NULL THEN f.total END), 0) AS recaudado,
  COALESCE(SUM(CASE WHEN f.numero IS NOT NULL AND f.fecha_pago IS NULL THEN f.total END), 0) AS por_cobrar
FROM parqueadero p
LEFT JOIN espacio  e ON e.id_parqueadero = p.id_parqueadero
LEFT JOIN ingreso  i ON i.id_espacio = e.id_espacio
LEFT JOIN factura  f ON f.id_ingreso = i.id_ingreso
GROUP BY p.id_parqueadero, p.razon_social, p.ubicacion, p.capacidad;

-- ---------------------------------------------------------------------
-- (Opcional) DATOS DE PRUEBA: quita los "-- " para cargarlos
-- ---------------------------------------------------------------------
-- INSERT INTO parqueadero (razon_social, ubicacion, capacidad, telefono, correo)
--   VALUES ('Parqueadero Centro', 'Calle 10 # 5-20, Bogotá', 20, '3001234567', 'centro@parqueadero.com');
-- Los usuarios se crean desde el sistema (opción 5) o con establecer_password.py,
-- porque necesitan contraseña para iniciar sesión.
-- INSERT INTO cliente (nombre, apellido, cedula, telefono, correo)
--   VALUES ('Carlos', 'Gómez', '1000000002', '3109876543', 'carlos@correo.com');
-- INSERT INTO vehiculo (placa, marca, color, tipo_vehiculo, id_cliente)
--   VALUES ('ABC123', 'Mazda', 'Rojo', 'Carro', 1);
-- INSERT INTO espacio (id_parqueadero, codigo, seccion, tipo_vehiculo)
--   VALUES (1, 'A-01', 'A', 'Carro'), (1, 'M-01', 'M', 'Moto');
-- INSERT INTO tarifa (id_parqueadero, tipo_vehiculo, precio_hora, precio_dia, fecha_vigencia)
--   VALUES (1, 'Carro', 3000, 20000, '2027-12-31');
