import uuid


class Usuario:
    def __init__(self, id_usuario, nombre, apellido, correo, rol, cedula=''):
        self.id_usuario = id_usuario
        self.nombre = nombre
        self.apellido = apellido
        self.correo = correo
        self.rol = rol
        self.cedula = cedula

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'

    def __str__(self):
        return f'{self.nombre_completo} ({self.rol})'

    @classmethod
    def crearusuario(cls, id_usuario=None):
        print('\n--- CREAR USUARIO ---')
        nombre = input('Nombre: ').strip()
        apellido = input('Apellido: ').strip()
        cedula = input('Cédula: ').strip()
        correo = input('Correo: ').strip()
        rol = input('Rol (Administrador/Operador): ').strip().title()
        if not nombre or not apellido or rol not in ('Administrador', 'Operador'):
            print('Se requieren nombre, apellido y rol válido.')
            return None
        usuario = cls(id_usuario if id_usuario is not None else str(uuid.uuid4()),
                      nombre, apellido, correo, rol, cedula)
        print('Usuario creado correctamente.')
        return usuario

    def iniciarSesion(self):
        print(f'Usuario seleccionado: {self.nombre_completo}.')

    def cerrarSesion(self):
        print('Sesión finalizada.')

    def generarReporte(self, parqueadero):
        parqueadero.generarReporte()

    def gestionarEspacios(self, parqueadero):
        if self.rol == 'Administrador':
            return parqueadero.consultarDisponibilidad()
        print('No tiene permisos para gestionar espacios.')
        return None
