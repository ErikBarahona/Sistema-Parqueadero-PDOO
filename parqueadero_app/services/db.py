"""Conexión a MariaDB. Las credenciales se leen del archivo .env (nunca en el código)."""
import os

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv()

# Excepción que lanza MariaDB al violar una restricción (UNIQUE, FOREIGN KEY...)
IntegrityError = pymysql.err.IntegrityError

_OBLIGATORIAS = ('DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME')


def get_connection():
    faltan = [v for v in _OBLIGATORIAS if not os.getenv(v)]
    if faltan:
        raise RuntimeError('Faltan variables en el archivo .env: ' + ', '.join(faltan))
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 3306)),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10,
    )
