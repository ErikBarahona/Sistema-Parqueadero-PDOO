"""Menú de consola del sistema de parqueaderos (con inicio de sesión y roles).

Ejecutar desde la carpeta del proyecto: python main.py
"""
import getpass
from datetime import date
from pathlib import Path

import pymysql

from models.cliente import Cliente
from models.espacio import Espacio
from models.parqueadero import Parqueadero
from models.tarifa import Tarifa
from models.usuario import Usuario
from models.vehiculo import Vehiculo
from services.sistema import AccesoDenegado, SistemaParqueadero


TIPOS = ('Carro', 'Moto', 'Bicicleta')
ADMIN = ('Administrador',)
TODOS = ('Administrador', 'Operador')
MAX_INTENTOS_LOGIN = 3

# (número, texto, roles que pueden usarla)
OPCIONES = [
    ('1', 'Crear otro parqueadero (y seleccionarlo)', ADMIN),
    ('2', 'Ver información del parqueadero activo', TODOS),
    ('3', 'Registrar espacio', ADMIN),
    ('4', 'Ver espacios y disponibilidad', TODOS),
    ('5', 'Registrar usuario (con contraseña)', ADMIN),
    ('6', 'Registrar cliente', TODOS),
    ('7', 'Registrar vehículo', TODOS),
    ('8', 'Configurar tarifa', ADMIN),
    ('9', 'Ver tarifas', TODOS),
    ('10', 'Registrar ingreso de vehículo', TODOS),
    ('11', 'Registrar salida y generar factura', TODOS),
    ('12', 'Registrar pago de factura', TODOS),
    ('13', 'Consultar historial de ingresos', TODOS),
    ('14', 'Consultar facturas', TODOS),
    ('15', 'Generar reporte general', ADMIN),
    ('16', 'Exportar historial a CSV', ADMIN),
    ('17', 'Buscar vehículo por placa', TODOS),
    ('18', 'Consultar vehículos de un cliente', TODOS),
    ('19', 'Poner espacio en mantenimiento / habilitar', ADMIN),
    ('20', 'Listar todos los parqueaderos', ADMIN),
    ('21', 'Seleccionar / cambiar parqueadero activo', TODOS),
    ('22', 'Reporte consolidado de todos los parqueaderos', ADMIN),
    ('23', 'Cambiar mi contraseña', TODOS),
    ('24', 'Restablecer la contraseña de otro usuario', ADMIN),
    ('25', 'Cerrar sesión (cambiar de usuario)', TODOS),
    ('0', 'Salir', TODOS),
]


def opciones_permitidas(rol):
    return [(n, t) for n, t, roles in OPCIONES if rol in roles]


def menu(s):
    activo = s.parqueadero
    print(f"\nPARQUEADERO ACTIVO: {activo.razon_social} (ID {activo.id_parqueadero})"
          if activo else "\nPARQUEADERO ACTIVO: ninguno — "
          + ("crea uno con la opción 1" if s.usuario.rol == 'Administrador'
             else "pide a un administrador que cree uno"))
    print(f'USUARIO: {s.usuario.nombre_completo} ({s.usuario.rol})')
    print('\n========== SISTEMA DE PARQUEADERO ==========')
    for numero_opcion, descripcion in opciones_permitidas(s.usuario.rol):
        print(f'{numero_opcion:>2}. {descripcion}')
    print('============================================')
    return input('Elige una opción: ').strip()


def texto(etiqueta, obligatorio=True):
    dato = input(f'{etiqueta}: ').strip()
    if obligatorio and not dato:
        raise ValueError(f'{etiqueta} es obligatorio.')
    return dato


def numero(etiqueta, minimo=1):
    valor = int(texto(etiqueta))
    if valor < minimo:
        raise ValueError(f'{etiqueta} debe ser como mínimo {minimo}.')
    return valor


def tipo_vehiculo():
    print('Tipos: 1. Carro | 2. Moto | 3. Bicicleta')
    opcion = numero('Selecciona el tipo')
    if opcion > 3:
        raise ValueError('Tipo no válido.')
    return TIPOS[opcion - 1]


def fecha_vigencia():
    return date.fromisoformat(texto('Vigente hasta (AAAA-MM-DD)'))


def pedir_clave_nueva(etiqueta='Nueva contraseña'):
    clave = getpass.getpass(f'{etiqueta}: ')
    if clave != getpass.getpass('Repite la contraseña: '):
        raise ValueError('Las contraseñas no coinciden.')
    return clave


def iniciar_sesion(s):
    """Pide credenciales (hasta 3 intentos). Devuelve True si se inició sesión."""
    print('\n=== SISTEMA DE PARQUEADEROS — INICIAR SESIÓN ===')
    for _ in range(MAX_INTENTOS_LOGIN):
        identificador = input('Correo o cédula (vacío para salir): ').strip()
        if not identificador:
            return False
        clave = getpass.getpass('Contraseña: ')
        try:
            usuario = s.iniciarSesion(identificador, clave)
        except AccesoDenegado as error:
            print('Error:', error)
            continue
        print(f'Bienvenido, {usuario.nombre_completo} ({usuario.rol}).')
        return True
    print('Demasiados intentos fallidos.')
    return False


def ejecutar(opcion, s):
    # Las opciones operativas actúan únicamente sobre el parqueadero seleccionado.
    if opcion in {'3', '8', '9', '10', '11', '12', '13', '14', '15', '16', '19'} and not s.parqueadero:
        raise ValueError('Primero crea un parqueadero con la opción 1 o selecciónalo con la opción 21.')
    if opcion == '1':
        p = Parqueadero.crearParqueadero(id_parqueadero=s.siguiente_id(s.parqueaderos, 'id_parqueadero'))
        if p:
            s.crearParqueadero(p)
            print(f'Ahora estás trabajando en: {p.razon_social} (ID {p.id_parqueadero})')

    elif opcion == '2':
        if not s.parqueadero:
            print('Primero debes crear un parqueadero.')
        else:
            s.parqueadero.mostrarInformacion()

    elif opcion == '3':
        print('\n--- NUEVO ESPACIO ---')
        codigo = texto('Código (ejemplo A-01)').upper()
        seccion = texto('Sección')
        tipo = tipo_vehiculo()
        s.registrarEspacio(Espacio(0, codigo, seccion, tipo))

    elif opcion == '4':
        if not s.parqueadero:
            print('Primero debes crear un parqueadero.')
        else:
            print('\n--- ESPACIOS ---')
            s.parqueadero.listarEspacios()
            s.parqueadero.consultarDisponibilidad()

    elif opcion == '5':
        usuario = Usuario.crearusuario(id_usuario=0)
        if usuario:
            s.registrarUsuario(usuario, pedir_clave_nueva('Contraseña del nuevo usuario'))
            print('Usuario registrado. ID:', usuario.id_usuario)

    elif opcion == '6':
        print('\n--- NUEVO CLIENTE ---')
        cliente = Cliente(0, texto('Nombre'), texto('Apellido'), texto('Cédula'),
                          texto('Teléfono', False), texto('Correo', False))
        s.registrarCliente(cliente)
        print('Cliente registrado. ID:', cliente.id_cliente)

    elif opcion == '7':
        print('\n--- NUEVO VEHÍCULO ---')
        placa = texto('Placa').upper()
        marca = texto('Marca')
        color = texto('Color')
        tipo = tipo_vehiculo()
        print('Clientes disponibles:', ', '.join(f'{c.id_cliente}: {c.nombre_completo}' for c in s.clientes) or '(ninguno)')
        opcion_cliente = texto('ID del cliente (vacío = visitante sin registrar)', False)
        id_cliente = int(opcion_cliente) if opcion_cliente else None
        vehiculo = Vehiculo(0, placa, marca, color, tipo)
        s.registrarVehiculo(vehiculo, id_cliente)
        print('Vehículo registrado:', vehiculo)

    elif opcion == '8':
        print('\n--- NUEVA TARIFA ---')
        tipo = tipo_vehiculo()
        precio_hora = numero('Precio por hora (COP)')
        precio_dia = numero('Precio por día (COP)')
        vigencia = fecha_vigencia()
        s.registrarTarifa(Tarifa(0, tipo, precio_hora, precio_dia, vigencia))
        print('Tarifa registrada.')

    elif opcion == '9':
        print('\n--- TARIFAS ---')
        tarifas = s.tarifas
        if not tarifas:
            print('No hay tarifas configuradas.')
        for t in tarifas:
            print(f'ID {t.id_tarifa}: {t.tipo_vehiculo} | Hora ${t.precio_hora:,} | '
                  f'Día ${t.precio_dia:,} | Hasta {t.fecha_vigencia} | '
                  f'{"Vigente" if t.validarVigencia() else "Vencida"}')

    elif opcion == '10':
        print('\n--- INGRESO ---')
        print(f'Registra el ingreso: {s.usuario.nombre_completo}')
        placa = texto('Placa del vehículo')
        tipo = None
        vehiculo = s.buscarVehiculo(placa)
        if vehiculo is None:
            print('Placa no registrada: ingresará como visitante (sin cliente).')
            tipo = tipo_vehiculo()
        elif vehiculo.cliente:
            print(f'Vehículo identificado. Cliente: {vehiculo.cliente.nombre_completo} (ID {vehiculo.cliente.id_cliente})')
        codigo = texto('Código de espacio (vacío = asignación automática)', False)
        s.registrarIngreso(placa, codigo or None, tipo)

    elif opcion == '11':
        print('\n--- SALIDA ---')
        placa = texto('Placa del vehículo')
        factura = s.registrarSalida(placa)
        opcion_pago = texto('¿Registrar el pago ahora? (s/n)', False).lower()
        if opcion_pago == 's':
            registrar_pago(s, factura.numero)

    elif opcion == '12':
        numero_factura = numero('Número de factura')
        registrar_pago(s, numero_factura)

    elif opcion == '13':
        placa = texto('Placa (vacío = todo el historial)', False)
        movimientos = s.consultarHistorial(placa or None)
        if not movimientos:
            print('No hay movimientos para mostrar.')
        for i in movimientos:
            entrada = i.entrada.strftime('%d/%m/%Y %H:%M') if i.entrada else '-'
            salida = i.salida.strftime('%d/%m/%Y %H:%M') if i.salida else 'Aún estacionado'
            print(f'Ingreso {i.id_ingreso} | {i.vehiculo.placa} | {i.espacio.codigo} | '
                  f'Registró: {i.usuario.nombre_completo} | Entrada: {entrada} | Salida: {salida}')

    elif opcion == '14':
        facturas = s.facturas
        if not facturas:
            print('Todavía no hay facturas.')
        for f in facturas:
            print(f'Factura {f.numero} | {f.vehiculo.placa} | ${f.total:,.0f} | '
                  f'{"Pagada" if f.pagada else "Pendiente"}')
        if facturas:
            seleccion = texto('Número para imprimir factura (vacío = volver)', False)
            if seleccion:
                encontrada = next((f for f in facturas if f.numero == int(seleccion)), None)
                if encontrada:
                    encontrada.imprimirFactura()
                else:
                    print('No se encontró la factura.')

    elif opcion == '15':
        s.generarReporte()

    elif opcion == '16':
        ruta = Path(__file__).resolve().parent / 'reportes' / f'historial_parqueadero_{s.parqueadero.id_parqueadero}.csv'
        print('Historial exportado a:', s.exportarHistorialCSV(ruta))

    elif opcion == '17':
        vehiculo = s.buscarVehiculo(texto('Placa'))
        if vehiculo:
            print(f'{vehiculo} | Marca: {vehiculo.marca} | Color: {vehiculo.color} | '
                  f'Propietario: {vehiculo.cliente.nombre_completo if vehiculo.cliente else "No registrado"}')
            activo = s.buscarIngresoActivoGlobal(vehiculo.placa)
            if activo:
                sede, ingreso = activo
                print(f'Estado: Estacionado en {sede.razon_social} (ID {sede.id_parqueadero}), espacio {ingreso.espacio.codigo}')
            else:
                print('Estado: Sin ingreso activo')
        else:
            print('No se encontró el vehículo.')

    elif opcion == '18':
        cedula = texto('Cédula del cliente')
        cliente = next((c for c in s.clientes if c.cedula == cedula), None)
        if cliente:
            cliente.consultarVehiculos()
        else:
            print('No se encontró el cliente.')

    elif opcion == '19':
        codigo = texto('Código del espacio')
        print('1. Poner en mantenimiento | 2. Volver a habilitar')
        accion = numero('Acción')
        if accion not in (1, 2):
            raise ValueError('Acción inválida.')
        s.cambiarEstadoEspacio(codigo, 'Mantenimiento' if accion == 1 else 'Disponible')

    elif opcion == '20':
        print('\n--- PARQUEADEROS REGISTRADOS ---')
        resumen = s.resumenParqueaderos()
        if not resumen:
            print('Todavía no hay parqueaderos. Registra uno con la opción 1.')
        for p in resumen:
            indicador = '*' if p['id'] == s.id_parqueadero_activo else ' '
            print(f"{indicador} ID {p['id']} | {p['nombre']} | {p['ubicacion']} | "
                  f"Capacidad: {p['capacidad']} | Libres: {p['disponibles']} | Ocupados: {p['ocupados']}")
        if resumen:
            print('* = parqueadero seleccionado actualmente')

    elif opcion == '21':
        parqueaderos = s.parqueaderos
        if not parqueaderos:
            print('Todavía no hay parqueaderos registrados.')
        else:
            for p in parqueaderos:
                print(f'ID {p.id_parqueadero}: {p.razon_social} ({p.ubicacion})')
            seleccionado = s.seleccionarParqueadero(numero('ID del parqueadero para trabajar'))
            print(f'Parqueadero seleccionado: {seleccionado.razon_social} (ID {seleccionado.id_parqueadero})')

    elif opcion == '22':
        print('\n--- REPORTE DE TODOS LOS PARQUEADEROS ---')
        resumen = s.resumenParqueaderos()
        if not resumen:
            print('No hay parqueaderos registrados.')
        else:
            for p in resumen:
                print(f"ID {p['id']} | {p['nombre']} | Libres: {p['disponibles']} | "
                      f"Ocupados: {p['ocupados']} | Recaudado: ${p['recaudado']:,.0f} | "
                      f"Pendiente: ${p['por_cobrar']:,.0f}")
            print(f"TOTAL RECAUDADO: ${sum(p['recaudado'] for p in resumen):,.0f}")
            print(f"TOTAL PENDIENTE: ${sum(p['por_cobrar'] for p in resumen):,.0f}")

    elif opcion == '23':
        actual = getpass.getpass('Contraseña actual: ')
        s.cambiarPassword(actual, pedir_clave_nueva())
        print('Contraseña actualizada.')

    elif opcion == '24':
        identificador = texto('ID, correo o cédula del usuario')
        usuario = s.restablecerPassword(identificador, pedir_clave_nueva('Nueva contraseña para ese usuario'))
        print(f'Contraseña restablecida para {usuario.nombre_completo}.')

    elif opcion == '25':
        s.cerrarSesion()
        print('Sesión cerrada.')

    else:
        print('Opción no válida.')


def registrar_pago(s, numero_factura):
    print('Métodos: 1. Efectivo | 2. Tarjeta | 3. Transferencia')
    indice = numero('Método de pago')
    if not 1 <= indice <= 3:
        raise ValueError('Método de pago no válido.')
    s.registrarPago(numero_factura, ('Efectivo', 'Tarjeta', 'Transferencia')[indice - 1])


def main():
    try:
        sistema = SistemaParqueadero()
        activa = iniciar_sesion(sistema)
    except (pymysql.MySQLError, RuntimeError, OSError) as error:
        print(f'No se pudo conectar a la base de datos: {error}')
        print('Revisa el archivo .env (host, usuario, contraseña) y que el servidor esté accesible.')
        return

    while activa:
        try:
            opcion = menu(sistema)
            if opcion == '0':
                print('Hasta luego. Los datos quedaron guardados en la base de datos.')
                break
            if opcion not in {n for n, _ in opciones_permitidas(sistema.usuario.rol)}:
                print('Opción no válida para tu rol.')
                continue
            ejecutar(opcion, sistema)
        except (ValueError, TypeError, OSError) as error:   # incluye AccesoDenegado
            print('Error:', error)
        except pymysql.MySQLError as error:
            print('Error de base de datos:', error)
        if sistema.usuario is None:       # se cerró la sesión
            activa = iniciar_sesion(sistema)


if __name__ == '__main__':
    main()
