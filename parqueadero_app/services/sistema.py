"""Servicio multisedes con persistencia en MariaDB y control de acceso por usuario y rol.

Usuarios, clientes y vehículos son globales. Espacios, tarifas, ingresos y
facturas corresponden siempre a un parqueadero, seleccionado como activo.

Hay que iniciar sesión (iniciarSesion) antes de operar. Roles: Administrador (todo) y
Operador (clientes, vehículos, ingresos, salidas, pagos y consultas).

Cada operación abre una transacción: si algo falla, no queda nada a medias.
Las clases de models/ conservan las reglas de negocio; este servicio las usa
y guarda el resultado en la base de datos (ya no existe registros.json).
"""

import csv
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from models.cliente import Cliente
from models.espacio import Espacio
from models.factura import Factura
from models.ingreso import Ingreso
from models.parqueadero import Parqueadero
from models.tarifa import Tarifa
from models.usuario import Usuario
from models.vehiculo import Vehiculo
from services import db, seguridad

TIPOS = ('Carro', 'Moto', 'Bicicleta')
ADMIN = 'Administrador'
MAX_INTENTOS = 5          # intentos fallidos antes de bloquear la cuenta
MINUTOS_BLOQUEO = 15
_CREDENCIALES_INCORRECTAS = 'Credenciales incorrectas.'


class AccesoDenegado(ValueError):
    """No se ha iniciado sesión o el rol del usuario no permite la acción."""

_MENSAJES_INTEGRIDAD = {
    'uq_cliente_cedula': 'Ya existe un cliente con esa cédula.',
    'uq_vehiculo_placa': 'Ya existe un vehículo con esa placa.',
    'uq_espacio_sede_codigo': 'Ya existe un espacio con ese código en el parqueadero.',
    'uq_usuario_cedula': 'Ya existe un usuario con esa cédula.',
    'uq_usuario_correo': 'Ya existe un usuario con ese correo.',
    'uq_ingreso_vehiculo_activo': 'Este vehículo ya tiene un ingreso activo.',
    'uq_ingreso_espacio_activo': 'Ese espacio ya está ocupado.',
    'uq_factura_ingreso': 'Ese ingreso ya tiene una factura.',
}


def _marcas(cantidad):
    return ','.join(['%s'] * cantidad)


def _sin_micro(momento):
    return momento.replace(microsecond=0) if momento else None


class SistemaParqueadero:
    def __init__(self):
        self.id_parqueadero_activo = None
        self._sesion = None   # Usuario que inició sesión
        with self._transaccion() as cur:
            cur.execute('SELECT id_parqueadero FROM parqueadero ORDER BY id_parqueadero LIMIT 1')
            fila = cur.fetchone()
        if fila:
            self.id_parqueadero_activo = fila['id_parqueadero']

    # ------------------------------------------------------------------
    # Infraestructura
    # ------------------------------------------------------------------
    @contextmanager
    def _transaccion(self):
        """Abre conexión + cursor; confirma al salir o deshace si hay error."""
        conexion = db.get_connection()
        try:
            with conexion.cursor() as cur:
                yield cur
            conexion.commit()
        except db.IntegrityError as error:
            conexion.rollback()
            raise ValueError(self._mensaje_integridad(error)) from error
        except BaseException:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    @staticmethod
    def _mensaje_integridad(error):
        texto = str(error)
        for clave, mensaje in _MENSAJES_INTEGRIDAD.items():
            if clave in texto:
                return mensaje
        if error.args and error.args[0] == 1452:
            return 'Un registro relacionado no existe (llave foránea inválida).'
        return f'La base de datos rechazó el dato: {texto}'

    @staticmethod
    def siguiente_id(elementos, nombre):
        """Solo para compatibilidad con el menú: el ID real lo asigna la base de datos."""
        return max((getattr(e, nombre) for e in elementos), default=0) + 1

    # ------------------------------------------------------------------
    # Constructores de objetos a partir de filas
    # ------------------------------------------------------------------
    @staticmethod
    def _usuario(f):
        return Usuario(f['id_usuario'], f['nombre'], f['apellido'], f['correo'] or '',
                       f['rol'], f['cedula'] or '')

    @staticmethod
    def _cliente(f):
        return Cliente(f['id_cliente'], f['nombre'], f['apellido'], f['cedula'],
                       f['telefono'] or '', f['correo'] or '')

    @staticmethod
    def _vehiculo(f, cliente=None):
        return Vehiculo(f['id_vehiculo'], f['placa'], f['marca'] or '', f['color'] or '',
                        f['tipo_vehiculo'], cliente)

    @staticmethod
    def _espacio(f):
        return Espacio(f['id_espacio'], f['codigo'], f['seccion'], f['tipo_vehiculo'], f['estado'])

    @staticmethod
    def _tarifa(f):
        return Tarifa(f['id_tarifa'], f['tipo_vehiculo'], int(f['precio_hora']),
                      int(f['precio_dia']), f['fecha_vigencia'])

    @staticmethod
    def _parqueadero(f, espacios=()):
        p = Parqueadero(f['id_parqueadero'], f['razon_social'], f['ubicacion'],
                        int(f['capacidad']), f['telefono'] or '', f['correo'] or '')
        p.espacios = list(espacios)
        return p

    def _cargar_parqueadero(self, cur, id_parqueadero, con_espacios=True):
        cur.execute('SELECT * FROM parqueadero WHERE id_parqueadero = %s', (id_parqueadero,))
        fila = cur.fetchone()
        if fila is None:
            return None
        espacios = []
        if con_espacios:
            cur.execute('SELECT * FROM espacio WHERE id_parqueadero = %s ORDER BY id_espacio',
                        (id_parqueadero,))
            espacios = [self._espacio(e) for e in cur.fetchall()]
        return self._parqueadero(fila, espacios)

    @staticmethod
    def _filas_por_id(cur, tabla, columna, ids):
        ids = sorted({i for i in ids if i is not None})
        if not ids:
            return {}
        cur.execute(f'SELECT * FROM {tabla} WHERE {columna} IN ({_marcas(len(ids))})', ids)
        return {fila[columna]: fila for fila in cur.fetchall()}

    def _cargar_ingresos(self, cur, ids):
        """Construye objetos Ingreso (con usuario, espacio, vehículo, cliente y tarifa)."""
        ids = sorted(set(ids))
        if not ids:
            return []
        cur.execute(f'SELECT * FROM ingreso WHERE id_ingreso IN ({_marcas(len(ids))}) '
                    'ORDER BY id_ingreso', ids)
        filas = cur.fetchall()
        usuarios = self._filas_por_id(cur, 'usuario', 'id_usuario', [f['id_usuario'] for f in filas])
        espacios = self._filas_por_id(cur, 'espacio', 'id_espacio', [f['id_espacio'] for f in filas])
        tarifas = self._filas_por_id(cur, 'tarifa', 'id_tarifa', [f['id_tarifa'] for f in filas])
        vehiculos = self._filas_por_id(cur, 'vehiculo', 'id_vehiculo', [f['id_vehiculo'] for f in filas])
        clientes = self._filas_por_id(cur, 'cliente', 'id_cliente',
                                      [v['id_cliente'] for v in vehiculos.values()])
        resultado = []
        for f in filas:
            fila_v = vehiculos[f['id_vehiculo']]
            cliente = self._cliente(clientes[fila_v['id_cliente']]) if fila_v['id_cliente'] else None
            ingreso = Ingreso(f['id_ingreso'], self._usuario(usuarios[f['id_usuario']]),
                              self._espacio(espacios[f['id_espacio']]),
                              self._vehiculo(fila_v, cliente),
                              self._tarifa(tarifas[f['id_tarifa']]))
            ingreso.entrada = f['entrada']
            ingreso.salida = f['salida']
            ingreso.tiempo = float(f['tiempo'])
            resultado.append(ingreso)
        return resultado

    @staticmethod
    def _factura(fila, ingreso, parqueadero):
        factura = Factura(ingreso, numero=fila['numero'], parqueadero=parqueadero)
        factura.fecha = fila['fecha']
        factura.horas = int(fila['horas'])
        factura.total = int(fila['total'])
        factura.metodo_pago = fila['metodo_pago']
        factura.fecha_pago = fila['fecha_pago']
        return factura

    @staticmethod
    def _ids_ingresos(cur, id_parqueadero, id_vehiculo=None):
        sql = ('SELECT i.id_ingreso FROM ingreso i JOIN espacio e ON e.id_espacio = i.id_espacio '
               'WHERE e.id_parqueadero = %s')
        params = [id_parqueadero]
        if id_vehiculo is not None:
            sql += ' AND i.id_vehiculo = %s'
            params.append(id_vehiculo)
        cur.execute(sql, params)
        return [f['id_ingreso'] for f in cur.fetchall()]

    # ------------------------------------------------------------------
    # Listas (siempre se leen frescas desde la base de datos)
    # ------------------------------------------------------------------
    @property
    def parqueadero(self):
        if self.id_parqueadero_activo is None:
            return None
        with self._transaccion() as cur:
            return self._cargar_parqueadero(cur, self.id_parqueadero_activo)

    @property
    def parqueaderos(self):
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM parqueadero ORDER BY id_parqueadero')
            return [self._parqueadero(f) for f in cur.fetchall()]

    @property
    def usuarios(self):
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM usuario ORDER BY id_usuario')
            return [self._usuario(f) for f in cur.fetchall()]

    def _personas(self):
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM cliente ORDER BY id_cliente')
            clientes = {f['id_cliente']: self._cliente(f) for f in cur.fetchall()}
            cur.execute('SELECT * FROM vehiculo ORDER BY id_vehiculo')
            vehiculos = []
            for f in cur.fetchall():
                cliente = clientes.get(f['id_cliente'])
                vehiculo = self._vehiculo(f, cliente)
                if cliente:
                    cliente.vehiculos.append(vehiculo)
                vehiculos.append(vehiculo)
        return list(clientes.values()), vehiculos

    @property
    def clientes(self):
        return self._personas()[0]

    @property
    def vehiculos(self):
        return self._personas()[1]

    @property
    def tarifas(self):
        if self.id_parqueadero_activo is None:
            return []
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM tarifa WHERE id_parqueadero = %s ORDER BY id_tarifa',
                        (self.id_parqueadero_activo,))
            return [self._tarifa(f) for f in cur.fetchall()]

    @property
    def ingresos(self):
        if self.id_parqueadero_activo is None:
            return []
        with self._transaccion() as cur:
            return self._cargar_ingresos(cur, self._ids_ingresos(cur, self.id_parqueadero_activo))

    @property
    def facturas(self):
        if self.id_parqueadero_activo is None:
            return []
        with self._transaccion() as cur:
            cur.execute('SELECT f.* FROM factura f '
                        'JOIN ingreso i ON i.id_ingreso = f.id_ingreso '
                        'JOIN espacio e ON e.id_espacio = i.id_espacio '
                        'WHERE e.id_parqueadero = %s ORDER BY f.numero',
                        (self.id_parqueadero_activo,))
            filas = cur.fetchall()
            ingresos = {i.id_ingreso: i
                        for i in self._cargar_ingresos(cur, [f['id_ingreso'] for f in filas])}
            sede = self._cargar_parqueadero(cur, self.id_parqueadero_activo, con_espacios=False)
            return [self._factura(f, ingresos[f['id_ingreso']], sede) for f in filas]

    # ------------------------------------------------------------------
    # Sesión y permisos
    # ------------------------------------------------------------------
    @property
    def usuario(self):
        """Usuario que inició sesión, o None."""
        return self._sesion

    def _exigir_sesion(self, *roles):
        """Exige una sesión iniciada y, si se indican roles, que el usuario tenga alguno."""
        if self._sesion is None:
            raise AccesoDenegado('Debes iniciar sesión para realizar esta acción.')
        if roles and self._sesion.rol not in roles:
            raise AccesoDenegado('Tu rol no tiene permiso para esta acción '
                                 f'(requiere: {" o ".join(roles)}).')
        return self._sesion

    def iniciarSesion(self, identificador, password):
        """Inicia sesión con correo o cédula. Bloquea la cuenta tras varios intentos fallidos."""
        identificador = (identificador or '').strip()
        error = None
        usuario = None
        # Los contadores de intentos deben guardarse aunque el inicio falle, por eso el error
        # se lanza después de cerrar la transacción y no dentro de ella.
        with self._transaccion() as cur:
            fila = None
            if identificador:
                cur.execute('SELECT * FROM usuario WHERE correo = %s OR cedula = %s '
                            'ORDER BY id_usuario LIMIT 1', (identificador, identificador))
                fila = cur.fetchone()
            if fila is not None and 'password_hash' not in fila:
                raise RuntimeError('La base de datos no tiene las columnas de acceso. '
                                   'Ejecuta migracion_login.sql.')
            ahora = datetime.now()
            if fila is None or not fila['password_hash'] or not fila['activo']:
                seguridad.verificar_password(password, None)   # mismo tiempo de respuesta
                error = _CREDENCIALES_INCORRECTAS
            elif fila['bloqueado_hasta'] and fila['bloqueado_hasta'] > ahora:
                minutos = int((fila['bloqueado_hasta'] - ahora).total_seconds() // 60) + 1
                error = f'Cuenta bloqueada por demasiados intentos. Intenta de nuevo en {minutos} minuto(s).'
            elif seguridad.verificar_password(password, fila['password_hash']):
                cur.execute('UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = NULL '
                            'WHERE id_usuario = %s', (fila['id_usuario'],))
                usuario = self._usuario(fila)
            else:
                intentos = int(fila['intentos_fallidos']) + 1
                if intentos >= MAX_INTENTOS:
                    cur.execute('UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = %s '
                                'WHERE id_usuario = %s',
                                (_sin_micro(ahora + timedelta(minutes=MINUTOS_BLOQUEO)),
                                 fila['id_usuario']))
                    error = (f'Demasiados intentos fallidos: la cuenta queda bloqueada '
                             f'{MINUTOS_BLOQUEO} minutos.')
                else:
                    cur.execute('UPDATE usuario SET intentos_fallidos = %s WHERE id_usuario = %s',
                                (intentos, fila['id_usuario']))
                    error = _CREDENCIALES_INCORRECTAS
        if error:
            raise AccesoDenegado(error)
        self._sesion = usuario
        return usuario

    def cerrarSesion(self):
        self._sesion = None

    def cambiarPassword(self, actual, nueva):
        """El usuario con sesión cambia su propia contraseña."""
        sesion = self._exigir_sesion()
        seguridad.validar_password(nueva)
        with self._transaccion() as cur:
            cur.execute('SELECT password_hash FROM usuario WHERE id_usuario = %s FOR UPDATE',
                        (sesion.id_usuario,))
            fila = cur.fetchone()
            if not fila or not seguridad.verificar_password(actual, fila['password_hash']):
                raise AccesoDenegado('La contraseña actual no es correcta.')
            cur.execute('UPDATE usuario SET password_hash = %s WHERE id_usuario = %s',
                        (seguridad.hashear_password(nueva), sesion.id_usuario))

    def restablecerPassword(self, identificador, nueva):
        """Un administrador define una contraseña nueva a otro usuario y lo desbloquea."""
        self._exigir_sesion(ADMIN)
        seguridad.validar_password(nueva)
        identificador = str(identificador).strip()
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM usuario WHERE correo = %s OR cedula = %s OR id_usuario = %s '
                        'LIMIT 1', (identificador, identificador,
                                    int(identificador) if identificador.isdigit() else -1))
            fila = cur.fetchone()
            if fila is None:
                raise ValueError('No existe un usuario con ese ID, correo o cédula.')
            cur.execute('UPDATE usuario SET password_hash = %s, activo = 1, intentos_fallidos = 0, '
                        'bloqueado_hasta = NULL WHERE id_usuario = %s',
                        (seguridad.hashear_password(nueva), fila['id_usuario']))
        return self._usuario(fila)

    def _exigir_parqueadero(self):
        parqueadero = self.parqueadero
        if not parqueadero:
            raise ValueError('Primero registra y selecciona un parqueadero (opciones 1 y 21).')
        return parqueadero

    # ------------------------------------------------------------------
    # Parqueaderos
    # ------------------------------------------------------------------
    def crearParqueadero(self, parqueadero):
        self._exigir_sesion(ADMIN)
        if not parqueadero.razon_social.strip() or not parqueadero.ubicacion.strip():
            raise ValueError('Razón social y ubicación son obligatorias.')
        if parqueadero.capacidad <= 0:
            raise ValueError('La capacidad debe ser mayor a cero.')
        with self._transaccion() as cur:
            cur.execute('SELECT 1 AS x FROM parqueadero '
                        'WHERE LOWER(razon_social) = LOWER(%s) AND LOWER(ubicacion) = LOWER(%s)',
                        (parqueadero.razon_social, parqueadero.ubicacion))
            if cur.fetchone():
                raise ValueError('Ese parqueadero ya está registrado en la misma ubicación.')
            cur.execute("INSERT INTO parqueadero (razon_social, ubicacion, capacidad, telefono, correo) "
                        "VALUES (%s, %s, %s, NULLIF(%s, ''), NULLIF(%s, ''))",
                        (parqueadero.razon_social, parqueadero.ubicacion, parqueadero.capacidad,
                         parqueadero.telefono, parqueadero.correo))
            parqueadero.id_parqueadero = cur.lastrowid
        self.id_parqueadero_activo = parqueadero.id_parqueadero
        return parqueadero

    def seleccionarParqueadero(self, id_parqueadero):
        self._exigir_sesion()
        with self._transaccion() as cur:
            encontrado = self._cargar_parqueadero(cur, int(id_parqueadero))
        if not encontrado:
            raise ValueError('No existe un parqueadero con ese ID.')
        self.id_parqueadero_activo = encontrado.id_parqueadero
        return encontrado

    def resumenParqueaderos(self):
        self._exigir_sesion(ADMIN)
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM v_reporte_sedes ORDER BY id_parqueadero')
            filas = cur.fetchall()
            cur.execute('SELECT e.id_parqueadero, COUNT(*) AS n FROM ingreso i '
                        'JOIN espacio e ON e.id_espacio = i.id_espacio GROUP BY e.id_parqueadero')
            ingresos = {f['id_parqueadero']: int(f['n']) for f in cur.fetchall()}
        return [{
            'id': f['id_parqueadero'],
            'nombre': f['razon_social'],
            'ubicacion': f['ubicacion'],
            'capacidad': int(f['capacidad']),
            'registrados': int(f['espacios_registrados']),
            'disponibles': int(f['libres']),
            'ocupados': int(f['ocupados']),
            'en_mantenimiento': int(f['en_mantenimiento']),
            'ingresos': ingresos.get(f['id_parqueadero'], 0),
            'recaudado': int(f['recaudado']),
            'por_cobrar': int(f['por_cobrar']),
        } for f in filas]

    # ------------------------------------------------------------------
    # Espacios
    # ------------------------------------------------------------------
    def registrarEspacio(self, espacio):
        self._exigir_sesion(ADMIN)
        self._exigir_parqueadero()
        if espacio.tipo_vehiculo not in TIPOS:
            raise ValueError('Tipo de vehículo no admitido.')
        if not espacio.codigo.strip() or not espacio.seccion.strip():
            raise ValueError('El código y la sección son obligatorios.')
        id_sede = self.id_parqueadero_activo
        with self._transaccion() as cur:
            # Se bloquea la sede para que dos usuarios no superen la capacidad a la vez.
            cur.execute('SELECT capacidad FROM parqueadero WHERE id_parqueadero = %s FOR UPDATE',
                        (id_sede,))
            capacidad = int(cur.fetchone()['capacidad'])
            cur.execute('SELECT COUNT(*) AS n FROM espacio WHERE id_parqueadero = %s', (id_sede,))
            if int(cur.fetchone()['n']) >= capacidad:
                raise ValueError('Se alcanzó la capacidad máxima.')
            cur.execute('SELECT 1 AS x FROM espacio WHERE id_parqueadero = %s '
                        'AND UPPER(codigo) = UPPER(%s)', (id_sede, espacio.codigo))
            if cur.fetchone():
                raise ValueError('Ya existe un espacio con ese código en el parqueadero.')
            cur.execute('INSERT INTO espacio (id_parqueadero, codigo, seccion, tipo_vehiculo, estado) '
                        'VALUES (%s, %s, %s, %s, %s)',
                        (id_sede, espacio.codigo, espacio.seccion, espacio.tipo_vehiculo,
                         espacio.estado))
            espacio.id_espacio = cur.lastrowid
        print('Espacio registrado correctamente.')
        return espacio

    def cambiarEstadoEspacio(self, codigo, estado):
        self._exigir_sesion(ADMIN)
        self._exigir_parqueadero()
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM espacio WHERE id_parqueadero = %s AND UPPER(codigo) = UPPER(%s) '
                        'FOR UPDATE', (self.id_parqueadero_activo, codigo))
            fila = cur.fetchone()
            if fila is None:
                raise ValueError('No existe un espacio con ese código en el parqueadero activo.')
            espacio = self._espacio(fila)
            if espacio.estado == 'Ocupado':
                raise ValueError('No se puede deshabilitar un espacio ocupado; registra primero la salida.')
            if estado not in ('Disponible', 'Mantenimiento'):
                raise ValueError('Solo se puede poner en mantenimiento o habilitar un espacio.')
            espacio.actualizarEstado(estado)
            cur.execute('UPDATE espacio SET estado = %s WHERE id_espacio = %s',
                        (espacio.estado, espacio.id_espacio))
        return espacio

    # ------------------------------------------------------------------
    # Usuarios, clientes, vehículos y tarifas
    # ------------------------------------------------------------------
    def registrarUsuario(self, usuario, password):
        self._exigir_sesion(ADMIN)
        if not usuario.nombre.strip() or not usuario.apellido.strip():
            raise ValueError('Nombre y apellido son obligatorios.')
        if usuario.rol not in ('Administrador', 'Operador'):
            raise ValueError('El rol debe ser Administrador u Operador.')
        if not (usuario.correo.strip() or usuario.cedula.strip()):
            raise ValueError('Indica el correo o la cédula: se usan para iniciar sesión.')
        seguridad.validar_password(password)
        with self._transaccion() as cur:
            if usuario.cedula:
                cur.execute('SELECT 1 AS x FROM usuario WHERE cedula = %s', (usuario.cedula,))
                if cur.fetchone():
                    raise ValueError('Ya existe un usuario con esa cédula.')
            if usuario.correo:
                cur.execute('SELECT 1 AS x FROM usuario WHERE correo = %s', (usuario.correo,))
                if cur.fetchone():
                    raise ValueError('Ya existe un usuario con ese correo.')
            cur.execute("INSERT INTO usuario (nombre, apellido, cedula, correo, rol, password_hash) "
                        "VALUES (%s, %s, NULLIF(%s, ''), NULLIF(%s, ''), %s, %s)",
                        (usuario.nombre, usuario.apellido, usuario.cedula, usuario.correo,
                         usuario.rol, seguridad.hashear_password(password)))
            usuario.id_usuario = cur.lastrowid
        return usuario

    def registrarCliente(self, cliente):
        self._exigir_sesion()
        if not cliente.nombre.strip() or not cliente.cedula.strip():
            raise ValueError('Nombre y cédula son obligatorios.')
        with self._transaccion() as cur:
            cur.execute('SELECT 1 AS x FROM cliente WHERE cedula = %s', (cliente.cedula,))
            if cur.fetchone():
                raise ValueError('Ya existe un cliente con esa cédula.')
            cur.execute("INSERT INTO cliente (nombre, apellido, cedula, telefono, correo) "
                        "VALUES (%s, %s, %s, NULLIF(%s, ''), NULLIF(%s, ''))",
                        (cliente.nombre, cliente.apellido, cliente.cedula, cliente.telefono,
                         cliente.correo))
            cliente.id_cliente = cur.lastrowid
        return cliente

    def registrarVehiculo(self, vehiculo, id_cliente=None):
        self._exigir_sesion()
        if vehiculo.tipo_vehiculo not in TIPOS:
            raise ValueError('Tipo de vehículo no admitido.')
        if not vehiculo.validarPlaca():
            raise ValueError('Placa inválida.')
        with self._transaccion() as cur:
            cur.execute('SELECT * FROM vehiculo WHERE placa = %s', (vehiculo.placa,))
            existente = cur.fetchone()
            # Solo se permite reutilizar un visitante (sin cliente) para asignarle un cliente.
            if existente and (existente['id_cliente'] is not None or id_cliente is None):
                raise ValueError('Ya existe un vehículo con esa placa.')
            if existente and existente['tipo_vehiculo'] != vehiculo.tipo_vehiculo:
                raise ValueError(f"Esa placa ya está registrada como visitante de tipo "
                                 f"{existente['tipo_vehiculo']}.")
            cliente = None
            if id_cliente is not None:
                cur.execute('SELECT * FROM cliente WHERE id_cliente = %s', (id_cliente,))
                fila = cur.fetchone()
                if not fila:
                    raise ValueError('No se encontró el cliente.')
                cliente = self._cliente(fila)
            if existente:
                cur.execute("UPDATE vehiculo SET marca = NULLIF(%s, ''), color = NULLIF(%s, ''), "
                            "id_cliente = %s WHERE id_vehiculo = %s",
                            (vehiculo.marca, vehiculo.color, id_cliente, existente['id_vehiculo']))
                vehiculo.id_vehiculo = existente['id_vehiculo']
            else:
                cur.execute("INSERT INTO vehiculo (placa, marca, color, tipo_vehiculo, id_cliente) "
                            "VALUES (%s, NULLIF(%s, ''), NULLIF(%s, ''), %s, %s)",
                            (vehiculo.placa, vehiculo.marca, vehiculo.color, vehiculo.tipo_vehiculo,
                             id_cliente))
                vehiculo.id_vehiculo = cur.lastrowid
        if cliente:
            cliente.agregarVehiculo(vehiculo)
        return vehiculo

    def registrarTarifa(self, tarifa):
        self._exigir_sesion(ADMIN)
        self._exigir_parqueadero()
        if not tarifa.validarVigencia():
            raise ValueError('La vigencia no puede ser una fecha anterior a hoy.')
        if tarifa.tipo_vehiculo not in TIPOS:
            raise ValueError('Tipo de vehículo no admitido.')
        with self._transaccion() as cur:
            cur.execute('INSERT INTO tarifa (id_parqueadero, tipo_vehiculo, precio_hora, precio_dia, '
                        'fecha_vigencia) VALUES (%s, %s, %s, %s, %s)',
                        (self.id_parqueadero_activo, tarifa.tipo_vehiculo, tarifa.precio_hora,
                         tarifa.precio_dia, tarifa.fecha_vigencia))
            tarifa.id_tarifa = cur.lastrowid
        return tarifa

    # ------------------------------------------------------------------
    # Búsquedas
    # ------------------------------------------------------------------
    @staticmethod
    def _normalizar_placa(placa):
        return placa.strip().upper().replace('-', '').replace(' ', '')

    def _vehiculo_por_placa(self, cur, placa):
        cur.execute('SELECT * FROM vehiculo WHERE placa = %s', (self._normalizar_placa(placa),))
        fila = cur.fetchone()
        if fila is None:
            return None
        cliente = None
        if fila['id_cliente']:
            cur.execute('SELECT * FROM cliente WHERE id_cliente = %s', (fila['id_cliente'],))
            cliente = self._cliente(cur.fetchone())
        return self._vehiculo(fila, cliente)

    def buscarVehiculo(self, placa):
        with self._transaccion() as cur:
            return self._vehiculo_por_placa(cur, placa)

    def _ingreso_activo_global(self, cur, placa):
        """Devuelve (parqueadero, ingreso) del ingreso sin salida, en cualquier sede."""
        cur.execute('SELECT i.id_ingreso, e.id_parqueadero FROM ingreso i '
                    'JOIN vehiculo v ON v.id_vehiculo = i.id_vehiculo '
                    'JOIN espacio e ON e.id_espacio = i.id_espacio '
                    'WHERE v.placa = %s AND i.salida IS NULL', (self._normalizar_placa(placa),))
        fila = cur.fetchone()
        if fila is None:
            return None
        ingreso = self._cargar_ingresos(cur, [fila['id_ingreso']])[0]
        return self._cargar_parqueadero(cur, fila['id_parqueadero'], con_espacios=False), ingreso

    def buscarIngresoActivoGlobal(self, placa):
        with self._transaccion() as cur:
            return self._ingreso_activo_global(cur, placa)

    def buscarIngresoActivo(self, placa):
        activo = self.buscarIngresoActivoGlobal(placa)
        if activo and activo[0].id_parqueadero == self.id_parqueadero_activo:
            return activo[1]
        return None

    # ------------------------------------------------------------------
    # Ingresos, salidas y pagos
    # ------------------------------------------------------------------
    def registrarIngreso(self, placa, codigo_espacio=None, tipo_vehiculo=None):
        """Registra la entrada de un vehículo.

        Si la placa ya existe, se usa ese vehículo (y su cliente, si lo tiene).
        Si no existe, entra como visitante: se crea el vehículo sin cliente, para lo
        cual hace falta indicar tipo_vehiculo. Todo ocurre en una sola transacción.
        El ingreso queda a nombre del usuario que inició sesión.
        """
        usuario = self._exigir_sesion()
        self._exigir_parqueadero()
        id_sede = self.id_parqueadero_activo
        with self._transaccion() as cur:
            vehiculo = self._vehiculo_por_placa(cur, placa)
            if vehiculo is None:
                if tipo_vehiculo not in TIPOS:
                    raise ValueError('La placa no está registrada: indica el tipo de vehículo '
                                     '(Carro, Moto o Bicicleta) para ingresarlo como visitante.')
                vehiculo = Vehiculo(0, self._normalizar_placa(placa), '', '', tipo_vehiculo)
                if not vehiculo.validarPlaca():
                    raise ValueError('Placa inválida.')
                cur.execute('INSERT INTO vehiculo (placa, tipo_vehiculo, id_cliente) '
                            'VALUES (%s, %s, NULL)', (vehiculo.placa, vehiculo.tipo_vehiculo))
                vehiculo.id_vehiculo = cur.lastrowid
            activo = self._ingreso_activo_global(cur, placa)
            if activo:
                raise ValueError(f'Este vehículo ya tiene un ingreso activo en '
                                 f'{activo[0].razon_social} (ID {activo[0].id_parqueadero}).')

            cur.execute('SELECT * FROM tarifa WHERE id_parqueadero = %s AND tipo_vehiculo = %s '
                        'AND fecha_vigencia >= %s ORDER BY id_tarifa DESC LIMIT 1',
                        (id_sede, vehiculo.tipo_vehiculo, date.today()))
            fila = cur.fetchone()
            if fila is None:
                raise ValueError('No hay una tarifa vigente para este vehículo en el parqueadero activo.')
            tarifa = self._tarifa(fila)

            # FOR UPDATE: si dos operadores piden el mismo espacio, el segundo espera al primero.
            if codigo_espacio:
                cur.execute('SELECT * FROM espacio WHERE id_parqueadero = %s '
                            'AND UPPER(codigo) = UPPER(%s) FOR UPDATE', (id_sede, codigo_espacio))
            else:
                cur.execute("SELECT * FROM espacio WHERE id_parqueadero = %s AND tipo_vehiculo = %s "
                            "AND estado = 'Disponible' ORDER BY id_espacio LIMIT 1 FOR UPDATE",
                            (id_sede, vehiculo.tipo_vehiculo))
            fila = cur.fetchone()
            if fila is None:
                raise ValueError('No existe un espacio disponible con ese código o tipo en el '
                                 'parqueadero activo.')
            espacio = self._espacio(fila)

            ingreso = Ingreso(None, usuario, espacio, vehiculo, tarifa)
            if not ingreso.registrarIngreso():
                raise ValueError('No fue posible registrar el ingreso.')
            ingreso.entrada = _sin_micro(ingreso.entrada)
            cur.execute('INSERT INTO ingreso (id_usuario, id_espacio, id_vehiculo, id_tarifa, '
                        'entrada, salida, tiempo) VALUES (%s, %s, %s, %s, %s, NULL, 0)',
                        (usuario.id_usuario, espacio.id_espacio, vehiculo.id_vehiculo,
                         tarifa.id_tarifa, ingreso.entrada))
            ingreso.id_ingreso = cur.lastrowid
            cur.execute("UPDATE espacio SET estado = 'Ocupado' WHERE id_espacio = %s",
                        (espacio.id_espacio,))
        return ingreso

    def registrarSalida(self, placa):
        self._exigir_sesion()
        sede = self._exigir_parqueadero()
        with self._transaccion() as cur:
            cur.execute('SELECT i.id_ingreso FROM ingreso i '
                        'JOIN vehiculo v ON v.id_vehiculo = i.id_vehiculo '
                        'JOIN espacio e ON e.id_espacio = i.id_espacio '
                        'WHERE v.placa = %s AND i.salida IS NULL AND e.id_parqueadero = %s '
                        'FOR UPDATE', (self._normalizar_placa(placa), sede.id_parqueadero))
            fila = cur.fetchone()
            if fila is None:
                otra = self._ingreso_activo_global(cur, placa)
                if otra:
                    raise ValueError(f'El vehículo está en otro parqueadero: {otra[0].razon_social} '
                                     f'(ID {otra[0].id_parqueadero}). Selecciónalo primero.')
                raise ValueError('El vehículo no tiene un ingreso activo.')
            ingreso = self._cargar_ingresos(cur, [fila['id_ingreso']])[0]

            ingreso.registrarSalida()
            ingreso.salida = _sin_micro(ingreso.salida)
            ingreso.calcularTiempo()
            factura = Factura(ingreso, numero=0, parqueadero=sede)
            factura.fecha = _sin_micro(factura.fecha)

            cur.execute('INSERT INTO factura (id_ingreso, fecha, horas, total) VALUES (%s, %s, %s, %s)',
                        (ingreso.id_ingreso, factura.fecha, factura.horas, factura.total))
            factura.numero = factura.id_factura = cur.lastrowid
            cur.execute('UPDATE ingreso SET salida = %s, tiempo = %s WHERE id_ingreso = %s',
                        (ingreso.salida, round(ingreso.tiempo, 4), ingreso.id_ingreso))
            cur.execute("UPDATE espacio SET estado = 'Disponible' WHERE id_espacio = %s",
                        (ingreso.espacio.id_espacio,))
        factura.imprimirFactura()
        return factura

    def registrarPago(self, numero_factura, metodo):
        self._exigir_sesion()
        sede = self._exigir_parqueadero()
        with self._transaccion() as cur:
            cur.execute('SELECT f.* FROM factura f '
                        'JOIN ingreso i ON i.id_ingreso = f.id_ingreso '
                        'JOIN espacio e ON e.id_espacio = i.id_espacio '
                        'WHERE f.numero = %s AND e.id_parqueadero = %s FOR UPDATE',
                        (numero_factura, sede.id_parqueadero))
            fila = cur.fetchone()
            if fila is None:
                raise ValueError('No existe la factura indicada en el parqueadero activo.')
            ingreso = self._cargar_ingresos(cur, [fila['id_ingreso']])[0]
            factura = self._factura(fila, ingreso, sede)
            if not factura.registrarPago(metodo):
                raise ValueError('No se pudo registrar el pago.')
            factura.fecha_pago = _sin_micro(factura.fecha_pago)
            cur.execute('UPDATE factura SET metodo_pago = %s, fecha_pago = %s WHERE numero = %s',
                        (factura.metodo_pago, factura.fecha_pago, factura.numero))
        return factura

    # ------------------------------------------------------------------
    # Consultas y reportes
    # ------------------------------------------------------------------
    def consultarHistorial(self, placa=None):
        self._exigir_sesion()
        if self.id_parqueadero_activo is None:
            return []
        with self._transaccion() as cur:
            id_vehiculo = None
            if placa:
                vehiculo = self._vehiculo_por_placa(cur, placa)
                if vehiculo is None:
                    return []
                id_vehiculo = vehiculo.id_vehiculo
            return self._cargar_ingresos(
                cur, self._ids_ingresos(cur, self.id_parqueadero_activo, id_vehiculo))

    def obtenerReporte(self):
        self._exigir_sesion(ADMIN)
        vacio = {'capacidad': 0, 'registrados': 0, 'disponibles': 0, 'ocupados': 0,
                 'en_mantenimiento': 0, 'ingresos': 0, 'vehiculos_activos': 0,
                 'facturas_pagadas': 0, 'facturas_pendientes': 0, 'recaudado': 0, 'por_cobrar': 0}
        id_sede = self.id_parqueadero_activo
        if id_sede is None:
            return vacio
        with self._transaccion() as cur:
            cur.execute('SELECT capacidad FROM parqueadero WHERE id_parqueadero = %s', (id_sede,))
            fila = cur.fetchone()
            if fila is None:
                return vacio
            capacidad = int(fila['capacidad'])
            cur.execute("SELECT COUNT(*) AS n, "
                        "COALESCE(SUM(CASE WHEN estado = 'Disponible' THEN 1 ELSE 0 END), 0) AS d, "
                        "COALESCE(SUM(CASE WHEN estado = 'Ocupado' THEN 1 ELSE 0 END), 0) AS o, "
                        "COALESCE(SUM(CASE WHEN estado = 'Mantenimiento' THEN 1 ELSE 0 END), 0) AS m "
                        "FROM espacio WHERE id_parqueadero = %s", (id_sede,))
            esp = cur.fetchone()
            cur.execute('SELECT COUNT(*) AS n, '
                        'COALESCE(SUM(CASE WHEN i.salida IS NULL THEN 1 ELSE 0 END), 0) AS a '
                        'FROM ingreso i JOIN espacio e ON e.id_espacio = i.id_espacio '
                        'WHERE e.id_parqueadero = %s', (id_sede,))
            ing = cur.fetchone()
            cur.execute('SELECT '
                        'COALESCE(SUM(CASE WHEN f.fecha_pago IS NOT NULL THEN 1 ELSE 0 END), 0) AS pag, '
                        'COALESCE(SUM(CASE WHEN f.fecha_pago IS NULL THEN 1 ELSE 0 END), 0) AS pen, '
                        'COALESCE(SUM(CASE WHEN f.fecha_pago IS NOT NULL THEN f.total ELSE 0 END), 0) AS rec, '
                        'COALESCE(SUM(CASE WHEN f.fecha_pago IS NULL THEN f.total ELSE 0 END), 0) AS xc '
                        'FROM factura f JOIN ingreso i ON i.id_ingreso = f.id_ingreso '
                        'JOIN espacio e ON e.id_espacio = i.id_espacio '
                        'WHERE e.id_parqueadero = %s', (id_sede,))
            fac = cur.fetchone()
        return {
            'capacidad': capacidad,
            'registrados': int(esp['n']),
            'disponibles': int(esp['d']),
            'ocupados': int(esp['o']),
            'en_mantenimiento': int(esp['m']),
            'ingresos': int(ing['n']),
            'vehiculos_activos': int(ing['a']),
            'facturas_pagadas': int(fac['pag']),
            'facturas_pendientes': int(fac['pen']),
            'recaudado': int(fac['rec']),
            'por_cobrar': int(fac['xc']),
        }

    def generarReporte(self):
        self._exigir_sesion(ADMIN)
        parqueadero = self._exigir_parqueadero()
        datos = self.obtenerReporte()
        print(f'\n========= REPORTE: {parqueadero.razon_social} (ID {parqueadero.id_parqueadero}) =========')
        for nombre, valor in datos.items():
            etiqueta = nombre.replace('_', ' ').capitalize()
            print(f'{etiqueta}: {valor:,}' if isinstance(valor, int) else f'{etiqueta}: {valor}')
        print('===========================================')
        return datos

    def exportarHistorialCSV(self, destino):
        self._exigir_sesion(ADMIN)
        parqueadero = self._exigir_parqueadero()
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        facturas_por_ingreso = {f.ingreso.id_ingreso: f for f in self.facturas}
        with destino.open('w', encoding='utf-8-sig', newline='') as archivo:
            writer = csv.writer(archivo)
            writer.writerow(['Parqueadero_ID', 'Parqueadero', 'Ingreso', 'Placa', 'Tipo', 'Espacio',
                             'Usuario', 'Entrada', 'Salida', 'Horas', 'Factura', 'Total_COP',
                             'Estado_pago', 'Metodo_pago'])
            for i in self.ingresos:
                f = facturas_por_ingreso.get(i.id_ingreso)
                writer.writerow([
                    parqueadero.id_parqueadero, parqueadero.razon_social,
                    i.id_ingreso, i.vehiculo.placa, i.vehiculo.tipo_vehiculo, i.espacio.codigo,
                    i.usuario.nombre_completo, i.entrada.isoformat(timespec='seconds') if i.entrada else '',
                    i.salida.isoformat(timespec='seconds') if i.salida else '',
                    round(i.tiempo, 2), f.numero if f else '', f.total if f else '',
                    ('Pagada' if f.pagada else 'Pendiente') if f else '',
                    f.metodo_pago if f and f.metodo_pago else '',
                ])
        return destino
