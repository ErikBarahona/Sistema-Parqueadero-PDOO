"""Define o restablece la contraseña de un usuario que ya existe en la base de datos.

Sirve para dar la primera contraseña al administrador y para recuperar el acceso.
Se ejecuta en la carpeta del proyecto:   python establecer_password.py
Solo funciona con las credenciales del archivo .env (acceso directo a la base de datos).
"""
import getpass
import sys

from services import db, seguridad


def main():
    identificador = input('Correo o cédula del usuario: ').strip()
    if not identificador:
        print('Cancelado.')
        return 1
    nueva = getpass.getpass('Nueva contraseña: ')
    if nueva != getpass.getpass('Repite la contraseña: '):
        print('Las contraseñas no coinciden.')
        return 1
    try:
        seguridad.validar_password(nueva)
    except ValueError as error:
        print(error)
        return 1

    conexion = db.get_connection()
    try:
        with conexion.cursor() as cur:
            cur.execute('SELECT id_usuario, nombre, apellido, rol FROM usuario '
                        'WHERE correo = %s OR cedula = %s', (identificador, identificador))
            usuario = cur.fetchone()
            if usuario is None:
                print('No existe un usuario con ese correo o cédula.')
                return 1
            cur.execute('UPDATE usuario SET password_hash = %s, activo = 1, intentos_fallidos = 0, '
                        'bloqueado_hasta = NULL WHERE id_usuario = %s',
                        (seguridad.hashear_password(nueva), usuario['id_usuario']))
        conexion.commit()
    finally:
        conexion.close()
    print(f"Contraseña actualizada para {usuario['nombre']} {usuario['apellido']} ({usuario['rol']}).")
    return 0


if __name__ == '__main__':
    sys.exit(main())
