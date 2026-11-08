"""Base de datos SQLite en memoria que imita el esquema de MariaDB.

Sirve para ejecutar las pruebas sin tocar la base de datos real.
Las consultas de services/sistema.py usan marcadores %s (estilo PyMySQL);
aquí se convierten a ? y se ignora el FOR UPDATE, que SQLite no usa.
"""
import re
import sqlite3
from datetime import date, datetime

import pymysql

from services import db, seguridad

sqlite3.register_adapter(datetime, lambda d: d.isoformat(' '))
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_converter('DATETIME', lambda b: datetime.fromisoformat(b.decode()))
sqlite3.register_converter('DATE', lambda b: date.fromisoformat(b.decode()))

ESQUEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE parqueadero (id_parqueadero INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT NOT NULL,
  ubicacion TEXT NOT NULL, capacidad INTEGER NOT NULL CHECK (capacidad > 0), telefono TEXT, correo TEXT);
CREATE TABLE usuario (id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, apellido TEXT NOT NULL,
  cedula TEXT UNIQUE, correo TEXT UNIQUE, rol TEXT NOT NULL CHECK (rol IN ('Administrador','Operador')),
  password_hash TEXT, activo INTEGER NOT NULL DEFAULT 1, intentos_fallidos INTEGER NOT NULL DEFAULT 0,
  bloqueado_hasta DATETIME);
CREATE TABLE cliente (id_cliente INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, apellido TEXT NOT NULL,
  cedula TEXT NOT NULL UNIQUE, telefono TEXT, correo TEXT);
CREATE TABLE vehiculo (id_vehiculo INTEGER PRIMARY KEY AUTOINCREMENT, placa TEXT NOT NULL UNIQUE, marca TEXT,
  color TEXT, tipo_vehiculo TEXT NOT NULL, id_cliente INTEGER REFERENCES cliente(id_cliente) ON DELETE SET NULL);
CREATE TABLE espacio (id_espacio INTEGER PRIMARY KEY AUTOINCREMENT,
  id_parqueadero INTEGER NOT NULL REFERENCES parqueadero(id_parqueadero), codigo TEXT NOT NULL COLLATE NOCASE,
  seccion TEXT NOT NULL, tipo_vehiculo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'Disponible',
  UNIQUE (id_parqueadero, codigo));
CREATE TABLE tarifa (id_tarifa INTEGER PRIMARY KEY AUTOINCREMENT,
  id_parqueadero INTEGER NOT NULL REFERENCES parqueadero(id_parqueadero), tipo_vehiculo TEXT NOT NULL,
  precio_hora INTEGER NOT NULL, precio_dia INTEGER NOT NULL, fecha_vigencia DATE NOT NULL);
CREATE TABLE ingreso (id_ingreso INTEGER PRIMARY KEY AUTOINCREMENT,
  id_usuario INTEGER NOT NULL REFERENCES usuario(id_usuario), id_espacio INTEGER NOT NULL REFERENCES espacio(id_espacio),
  id_vehiculo INTEGER NOT NULL REFERENCES vehiculo(id_vehiculo), id_tarifa INTEGER NOT NULL REFERENCES tarifa(id_tarifa),
  entrada DATETIME NOT NULL, salida DATETIME, tiempo REAL NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX uq_ingreso_vehiculo_activo ON ingreso (id_vehiculo) WHERE salida IS NULL;
CREATE UNIQUE INDEX uq_ingreso_espacio_activo ON ingreso (id_espacio) WHERE salida IS NULL;
CREATE TABLE factura (numero INTEGER PRIMARY KEY AUTOINCREMENT, id_ingreso INTEGER NOT NULL UNIQUE REFERENCES ingreso(id_ingreso),
  fecha DATETIME NOT NULL, horas INTEGER NOT NULL, total INTEGER NOT NULL, metodo_pago TEXT, fecha_pago DATETIME);
CREATE VIEW v_reporte_sedes AS
SELECT p.id_parqueadero, p.razon_social, p.ubicacion, p.capacidad,
  COUNT(DISTINCT e.id_espacio) AS espacios_registrados,
  COUNT(DISTINCT CASE WHEN e.estado = 'Disponible' THEN e.id_espacio END) AS libres,
  COUNT(DISTINCT CASE WHEN e.estado = 'Ocupado' THEN e.id_espacio END) AS ocupados,
  COUNT(DISTINCT CASE WHEN e.estado = 'Mantenimiento' THEN e.id_espacio END) AS en_mantenimiento,
  COALESCE(SUM(CASE WHEN f.fecha_pago IS NOT NULL THEN f.total END), 0) AS recaudado,
  COALESCE(SUM(CASE WHEN f.numero IS NOT NULL AND f.fecha_pago IS NULL THEN f.total END), 0) AS por_cobrar
FROM parqueadero p LEFT JOIN espacio e ON e.id_parqueadero = p.id_parqueadero
LEFT JOIN ingreso i ON i.id_espacio = e.id_espacio LEFT JOIN factura f ON f.id_ingreso = i.id_ingreso
GROUP BY p.id_parqueadero, p.razon_social, p.ubicacion, p.capacidad;
"""


class _Cursor:
    def __init__(self, conexion):
        self._c = conexion.cursor()
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        sql = re.sub(r'\s+FOR UPDATE\b', '', sql.replace('%s', '?'))
        try:
            self._c.execute(sql, tuple(params))
        except sqlite3.IntegrityError as error:
            raise pymysql.err.IntegrityError(1062, str(error)) from error
        self.lastrowid = self._c.lastrowid
        self.rowcount = self._c.rowcount

    def fetchone(self):
        fila = self._c.fetchone()
        return dict(fila) if fila is not None else None

    def fetchall(self):
        return [dict(f) for f in self._c.fetchall()]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Conexion:
    def __init__(self, real):
        self._real = real

    def cursor(self):
        return _Cursor(self._real)

    def commit(self):
        self._real.commit()

    def rollback(self):
        self._real.rollback()

    def close(self):
        pass  # la base en memoria vive mientras dure la prueba


def instalar():
    """Crea la base en memoria y hace que services.db.get_connection la use."""
    real = sqlite3.connect(':memory:', detect_types=sqlite3.PARSE_DECLTYPES)
    real.row_factory = sqlite3.Row
    real.executescript(ESQUEMA)
    conexion = _Conexion(real)
    db.get_connection = lambda: conexion
    return real


def crear_usuario(real, nombre, apellido, correo, rol, password, cedula=None):
    """Inserta un usuario con contraseña directamente (como el administrador ya existente)."""
    real.execute('INSERT INTO usuario (nombre, apellido, cedula, correo, rol, password_hash) '
                 'VALUES (?, ?, ?, ?, ?, ?)',
                 (nombre, apellido, cedula, correo, rol, seguridad.hashear_password(password)))
    real.commit()
