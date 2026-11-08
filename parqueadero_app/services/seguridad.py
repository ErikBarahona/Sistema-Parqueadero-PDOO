"""Manejo seguro de contraseñas: nunca se guardan en texto plano, solo su hash.

Usa PBKDF2-HMAC-SHA256 con sal aleatoria (incluido en Python, sin dependencias).
Formato guardado:  pbkdf2_sha256$iteraciones$sal$hash
"""
import hashlib
import hmac
import secrets

ITERACIONES = 600_000      # se lee en cada llamada; las pruebas lo reducen para ir más rápido
LONGITUD_MINIMA = 8
_ALGORITMO = 'pbkdf2_sha256'


def validar_password(password):
    """Exige mínimo 8 caracteres, con al menos una letra y un número."""
    if (not isinstance(password, str) or len(password) < LONGITUD_MINIMA
            or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password)):
        raise ValueError(f'La contraseña debe tener mínimo {LONGITUD_MINIMA} caracteres, '
                         'con al menos una letra y un número.')


def hashear_password(password):
    sal = secrets.token_hex(16)
    resumen = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(sal), ITERACIONES)
    return f'{_ALGORITMO}${ITERACIONES}${sal}${resumen.hex()}'


def verificar_password(password, almacenado):
    """True si la contraseña coincide. Si no hay hash guardado, hace el mismo trabajo y
    devuelve False, para que no se note por el tiempo de respuesta que el usuario no existe."""
    try:
        algoritmo, iteraciones, sal, esperado = (almacenado or '').split('$')
        if algoritmo != _ALGORITMO:
            raise ValueError
        resumen = hashlib.pbkdf2_hmac('sha256', (password or '').encode('utf-8'),
                                      bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(resumen.hex(), esperado)
    except ValueError:
        hashlib.pbkdf2_hmac('sha256', (password or '').encode('utf-8'), b'\x00' * 16, ITERACIONES)
        return False
