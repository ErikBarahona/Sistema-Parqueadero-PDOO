"""Pruebas del sistema. Usan SQLite en memoria (tests/fake_db.py): no tocan MariaDB."""
import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

from models.cliente import Cliente
from models.espacio import Espacio
from models.parqueadero import Parqueadero
from models.tarifa import Tarifa
from models.usuario import Usuario
from models.vehiculo import Vehiculo
from services import seguridad
from services.sistema import AccesoDenegado, SistemaParqueadero
from tests import fake_db

seguridad.ITERACIONES = 1000   # contraseñas rápidas de verificar en las pruebas
ADMIN_CORREO, ADMIN_CLAVE = 'admin@ejemplo.com', 'Admin12345'
OPERADOR_CORREO, OPERADOR_CLAVE = 'ana@ejemplo.com', 'Operador123'


def silencio():
    return redirect_stdout(io.StringIO())


class SistemaParqueaderoPruebas(unittest.TestCase):
    def setUp(self):
        self.real = fake_db.instalar()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # El administrador ya existe en la base de datos (como en tu servidor).
        fake_db.crear_usuario(self.real, 'Erik', 'Barahona', ADMIN_CORREO, 'Administrador',
                              ADMIN_CLAVE, '1523654987')
        self.s = SistemaParqueadero()
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        with silencio():
            self.s.crearParqueadero(Parqueadero(0, 'Mi Parqueadero', 'Bogotá', 2, '123', 'correo@ejemplo.com'))
            self.s.registrarEspacio(Espacio(0, 'A-01', 'A', 'Carro'))
            self.s.registrarEspacio(Espacio(0, 'M-01', 'B', 'Moto'))
            self.s.registrarUsuario(Usuario(0, 'Ana', 'Ruiz', OPERADOR_CORREO, 'Operador'), OPERADOR_CLAVE)
            self.s.registrarCliente(Cliente(0, 'Juan', 'Perez', '123456', '5555', 'juan@ejemplo.com'))
            self.s.registrarVehiculo(Vehiculo(0, 'abc123', 'Toyota', 'Rojo', 'Carro'), id_cliente=1)
            self.s.registrarTarifa(Tarifa(0, 'Carro', 3000, 20000, date.today() + timedelta(days=100)))
            self.s.registrarTarifa(Tarifa(0, 'Moto', 2000, 12000, date.today() + timedelta(days=100)))

    def registrar(self):
        with silencio():
            return self.s.registrarIngreso('ABC123')

    def salir(self):
        with silencio():
            return self.s.registrarSalida('ABC123')

    def retroceder_entrada(self, **tiempo):
        self.real.execute('UPDATE ingreso SET entrada = ? WHERE salida IS NULL',
                          ((datetime.now() - timedelta(**tiempo)).replace(microsecond=0),))
        self.real.commit()

    def estado_espacio(self, codigo):
        return self.s.parqueadero.buscarEspacioPorCodigo(codigo).estado

    # --- Registro básico ---
    def test_guarda_en_base_de_datos(self):
        self.assertEqual(len(self.s.parqueadero.espacios), 2)
        self.assertEqual(self.s.parqueadero.espacios[0].id_espacio, 1)

    def test_no_repite_placas(self):
        with self.assertRaisesRegex(ValueError, 'placa'):
            self.s.registrarVehiculo(Vehiculo(0, 'ABC123', 'Kia', 'Azul', 'Carro'))

    def test_no_supera_capacidad(self):
        with self.assertRaises(ValueError):
            self.s.registrarEspacio(Espacio(0, 'A-02', 'A', 'Carro'))

    def test_cliente_duplicado(self):
        with self.assertRaisesRegex(ValueError, 'cédula'):
            self.s.registrarCliente(Cliente(0, 'Otro', 'Nombre', '123456', '', ''))

    def test_usuarios_solo_con_cedula_no_chocan_por_correo_vacio(self):
        with silencio():
            self.s.registrarUsuario(Usuario(0, 'Luis', 'Mora', '', 'Operador', '111'), 'Clave12345')
            self.s.registrarUsuario(Usuario(0, 'Eva', 'Rey', '', 'Administrador', '222'), 'Clave12345')
        self.assertEqual(len(self.s.usuarios), 4)

    def test_usuario_necesita_correo_o_cedula(self):
        with self.assertRaisesRegex(ValueError, 'correo o la cédula'):
            self.s.registrarUsuario(Usuario(0, 'Sin', 'Datos', '', 'Operador', ''), 'Clave12345')

    def test_vehiculo_visitante_sin_cliente(self):
        with silencio():
            visitante = self.s.registrarVehiculo(Vehiculo(0, 'XYZ789', '', '', 'Moto'))
        self.assertIsNone(self.s.buscarVehiculo('xyz-789').cliente)
        self.assertEqual(visitante.id_vehiculo, 2)

    # --- Ingresos y salidas ---
    def test_ingreso_de_placa_no_registrada_entra_como_visitante(self):
        with silencio():
            ingreso = self.s.registrarIngreso('zzz-999', tipo_vehiculo='Carro')
            self.s.registrarSalida('ZZZ999')
        self.assertEqual(ingreso.vehiculo.placa, 'ZZZ999')
        self.assertIsNone(self.s.buscarVehiculo('ZZZ999').cliente)
        self.assertEqual(len(self.s.clientes), 1)  # no se creó ningún cliente
        self.assertEqual(len(self.s.facturas), 1)

    def test_ingreso_cliente_registrado_se_identifica(self):
        ingreso = self.registrar()
        self.assertEqual(ingreso.vehiculo.cliente.id_cliente, 1)
        self.assertEqual(self.s.ingresos[0].vehiculo.cliente.cedula, '123456')

    def test_visitante_sin_tipo_pide_el_tipo(self):
        with self.assertRaisesRegex(ValueError, 'tipo de vehículo'):
            self.s.registrarIngreso('ZZZ999')
        self.assertIsNone(self.s.buscarVehiculo('ZZZ999'))

    def test_visitante_con_placa_invalida_no_se_crea(self):
        with silencio(), self.assertRaisesRegex(ValueError, 'Placa'):
            self.s.registrarIngreso('@@', tipo_vehiculo='Carro')
        self.assertEqual(len(self.s.vehiculos), 1)

    def test_si_falla_el_ingreso_no_queda_el_visitante(self):
        # No hay espacios de Bicicleta ni tarifa: el ingreso falla y se deshace todo.
        with silencio(), self.assertRaises(ValueError):
            self.s.registrarIngreso('BIC123', tipo_vehiculo='Bicicleta')
        self.assertIsNone(self.s.buscarVehiculo('BIC123'))

    def test_visitante_puede_asociarse_luego_a_un_cliente(self):
        with silencio():
            self.s.registrarIngreso('ZZZ999', tipo_vehiculo='Carro')
            self.s.registrarSalida('ZZZ999')
            self.s.registrarCliente(Cliente(0, 'Marta', 'Diaz', '999', '', ''))
            self.s.registrarVehiculo(Vehiculo(0, 'ZZZ999', 'Kia', 'Azul', 'Carro'), id_cliente=2)
        v = self.s.buscarVehiculo('ZZZ999')
        self.assertEqual(v.cliente.cedula, '999')
        self.assertEqual(v.marca, 'Kia')
        self.assertEqual(len(self.s.vehiculos), 2)
        with self.assertRaisesRegex(ValueError, 'placa'):  # ya tiene cliente: no se duplica
            self.s.registrarVehiculo(Vehiculo(0, 'ZZZ999', 'Kia', 'Azul', 'Carro'), id_cliente=1)

    def test_ingreso_ocupa_espacio(self):
        ingreso = self.registrar()
        self.assertEqual(ingreso.id_ingreso, 1)
        self.assertEqual(self.estado_espacio('A-01'), 'Ocupado')
        self.assertEqual(self.s.obtenerReporte()['vehiculos_activos'], 1)

    def test_vehiculo_no_ingresa_dos_veces(self):
        self.registrar()
        with self.assertRaisesRegex(ValueError, 'activo'):
            self.registrar()

    def test_tipo_de_espacio_incompatible(self):
        with silencio(), self.assertRaises(ValueError):
            self.s.registrarIngreso('ABC123', codigo_espacio='M-01')
        self.assertEqual(self.estado_espacio('M-01'), 'Disponible')

    def test_salida_factura_y_espacio_libre(self):
        self.registrar()
        self.retroceder_entrada(hours=2, minutes=10)
        factura = self.salir()
        self.assertEqual(factura.total, 9000)
        self.assertEqual(self.estado_espacio('A-01'), 'Disponible')
        self.assertFalse(factura.pagada)
        self.assertEqual(self.s.obtenerReporte()['por_cobrar'], 9000)

    def test_salida_sin_ingreso(self):
        with self.assertRaisesRegex(ValueError, 'ingreso activo'):
            self.s.registrarSalida('ABC123')

    def test_pago_reflejado_en_recaudo(self):
        self.registrar()
        factura = self.salir()
        with silencio():
            self.s.registrarPago(factura.numero, 'Efectivo')
        self.assertTrue(self.s.facturas[0].pagada)
        self.assertEqual(self.s.obtenerReporte()['recaudado'], factura.total)
        self.assertEqual(self.s.obtenerReporte()['facturas_pendientes'], 0)
        with silencio(), self.assertRaises(ValueError):
            self.s.registrarPago(factura.numero, 'Tarjeta')

    def test_metodo_de_pago_invalido(self):
        self.registrar()
        factura = self.salir()
        with silencio(), self.assertRaises(ValueError):
            self.s.registrarPago(factura.numero, 'Cheque')
        self.assertFalse(self.s.facturas[0].pagada)

    # --- Lo guardado se recupera con una instancia nueva ---
    def test_persistencia_relaciones(self):
        self.registrar()
        self.salir()
        nuevo = SistemaParqueadero()
        nuevo.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.assertEqual(len(nuevo.ingresos), 1)
        self.assertEqual(len(nuevo.facturas), 1)
        self.assertEqual(nuevo.vehiculos[0].cliente.cedula, '123456')
        self.assertEqual(nuevo.clientes[0].vehiculos[0].placa, 'ABC123')
        self.assertEqual(nuevo.parqueadero.espacios[0].estado, 'Disponible')
        with silencio():
            otro = nuevo.registrarIngreso('ABC123')
        self.assertEqual(otro.id_ingreso, 2)

    def test_persistencia_de_pago(self):
        self.registrar()
        factura = self.salir()
        with silencio():
            self.s.registrarPago(factura.numero, 'Transferencia')
        nuevo = SistemaParqueadero()
        nuevo.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.assertTrue(nuevo.facturas[0].pagada)
        self.assertEqual(nuevo.facturas[0].metodo_pago, 'Transferencia')

    def test_exportar_csv(self):
        self.registrar()
        self.salir()
        ruta = Path(self.temp.name) / 'exportaciones' / 'historial.csv'
        self.s.exportarHistorialCSV(ruta)
        with ruta.open(encoding='utf-8-sig', newline='') as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['Placa'], 'ABC123')
        self.assertEqual(filas[0]['Estado_pago'], 'Pendiente')

    def test_historial_por_placa(self):
        self.registrar()
        self.assertEqual(len(self.s.consultarHistorial('ABC123')), 1)
        self.assertEqual(self.s.consultarHistorial('NOEXISTE'), [])

    # --- Tarifas y espacios ---
    def test_tarifa_por_dias_y_hora_fraccion(self):
        tarifa = self.s.tarifas[0]
        self.assertEqual(tarifa.calcularCosto(0.01), 3000)
        self.assertEqual(tarifa.calcularCosto(7.5), 20000)
        self.assertEqual(tarifa.calcularCosto(25.1), 26000)

    def test_tarifa_vencida_no_se_admite(self):
        with self.assertRaisesRegex(ValueError, 'vigencia'):
            self.s.registrarTarifa(Tarifa(0, 'Carro', 100, 500, date.today() - timedelta(days=1)))

    def test_espacio_en_mantenimiento_no_se_asigna(self):
        with silencio():
            self.s.cambiarEstadoEspacio('A-01', 'Mantenimiento')
        self.assertEqual(self.s.obtenerReporte()['en_mantenimiento'], 1)
        with silencio(), self.assertRaises(ValueError):
            self.s.registrarIngreso('ABC123')
        with silencio():
            self.s.cambiarEstadoEspacio('A-01', 'Disponible')
        self.assertIsNotNone(self.registrar())

    def test_espacio_ocupado_no_puede_entrar_en_mantenimiento(self):
        self.registrar()
        with self.assertRaises(ValueError):
            self.s.cambiarEstadoEspacio('A-01', 'Mantenimiento')

    # --- Multisedes ---
    def test_multisedes_con_espacios_y_tarifas_independientes(self):
        primero = self.registrar()
        with silencio():
            segundo = self.s.crearParqueadero(Parqueadero(0, 'Sede Norte', 'Calle 80', 1, '456', 'norte@test.com'))
        self.assertEqual(self.s.parqueadero.id_parqueadero, segundo.id_parqueadero)
        self.assertEqual(segundo.id_parqueadero, 2)
        with self.assertRaisesRegex(ValueError, 'activo'):
            self.s.registrarIngreso('ABC123')
        with silencio():
            self.s.registrarEspacio(Espacio(0, 'A-01', 'A', 'Carro'))  # mismo código que la sede 1
        self.assertEqual(len(self.s.parqueadero.espacios), 1)
        self.assertEqual(self.s.tarifas, [])
        self.s.registrarTarifa(Tarifa(0, 'Carro', 6000, 30000, date.today() + timedelta(days=10)))
        with silencio():
            self.s.registrarVehiculo(Vehiculo(0, 'DEF456', 'Kia', 'Negro', 'Carro'))
            segundo_ingreso = self.s.registrarIngreso('DEF456')
        self.assertNotEqual(primero.id_ingreso, segundo_ingreso.id_ingreso)
        self.assertEqual(self.s.obtenerReporte()['ocupados'], 1)
        self.s.seleccionarParqueadero(1)
        self.assertEqual(self.estado_espacio('A-01'), 'Ocupado')
        self.assertEqual(self.s.tarifas[0].precio_hora, 3000)
        self.assertEqual(len(self.s.ingresos), 1)
        self.assertEqual(len(self.s.resumenParqueaderos()), 2)
        with self.assertRaisesRegex(ValueError, 'otro parqueadero'):
            self.s.registrarSalida('DEF456')

    def test_facturas_y_pagos_pertenecen_a_su_sede(self):
        self.registrar()
        factura1 = self.salir()
        with silencio():
            self.s.crearParqueadero(Parqueadero(0, 'Sede Sur', 'Calle 10', 2, '', ''))
            self.s.registrarEspacio(Espacio(0, 'A-01', 'A', 'Carro'))
        self.s.registrarTarifa(Tarifa(0, 'Carro', 5500, 27000, date.today() + timedelta(days=30)))
        with silencio():
            self.s.registrarIngreso('ABC123')
            factura2 = self.s.registrarSalida('ABC123')
        self.assertNotEqual(factura1.numero, factura2.numero)
        self.assertEqual(factura2.parqueadero.id_parqueadero, 2)
        with self.assertRaisesRegex(ValueError, 'parqueadero activo'):
            self.s.registrarPago(factura1.numero, 'Efectivo')
        with silencio():
            self.s.registrarPago(factura2.numero, 'Tarjeta')
        self.s.seleccionarParqueadero(1)
        self.assertEqual(self.s.obtenerReporte()['por_cobrar'], factura1.total)
        self.assertEqual(self.s.obtenerReporte()['recaudado'], 0)
        self.s.seleccionarParqueadero(2)
        self.assertEqual(self.s.obtenerReporte()['recaudado'], factura2.total)
        resumen = self.s.resumenParqueaderos()
        self.assertEqual(sum(d['recaudado'] for d in resumen), factura2.total)
        self.assertEqual(sum(d['por_cobrar'] for d in resumen), factura1.total)

    def test_persistencia_multisedes(self):
        with silencio():
            self.s.crearParqueadero(Parqueadero(0, 'Segunda sede', 'Medellín', 5, '123', ''))
            self.s.registrarEspacio(Espacio(0, 'A-01', 'A', 'Carro'))
        self.s.registrarTarifa(Tarifa(0, 'Carro', 5000, 25000, date.today() + timedelta(days=25)))
        nuevo = SistemaParqueadero()
        nuevo.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.assertEqual(len(nuevo.parqueaderos), 2)
        self.assertEqual(nuevo.id_parqueadero_activo, 1)  # al iniciar se usa la primera sede
        nuevo.seleccionarParqueadero(2)
        self.assertEqual(nuevo.tarifas[0].precio_hora, 5000)
        self.assertEqual(len(nuevo.parqueadero.espacios), 1)
        nuevo.seleccionarParqueadero(1)
        self.assertEqual(len(nuevo.parqueadero.espacios), 2)
        self.assertEqual(nuevo.tarifas[0].precio_hora, 3000)
        self.assertEqual(len(nuevo.clientes), 1)
        self.assertEqual(len(nuevo.vehiculos), 1)

    def test_cambio_a_sede_inexistente_no_altera_seleccion(self):
        with silencio():
            self.s.crearParqueadero(Parqueadero(0, 'Norte', 'Bogotá', 10, '', ''))
        with self.assertRaisesRegex(ValueError, 'No existe'):
            self.s.seleccionarParqueadero(99)
        self.assertEqual(self.s.id_parqueadero_activo, 2)
        with self.assertRaisesRegex(ValueError, 'ya está registrado'):
            self.s.crearParqueadero(Parqueadero(0, 'Mi Parqueadero', 'Bogotá', 10, '', ''))

    def test_sin_parqueadero_activo(self):
        base = fake_db.instalar()  # base vacía, solo con el administrador
        fake_db.crear_usuario(base, 'Erik', 'Barahona', ADMIN_CORREO, 'Administrador', ADMIN_CLAVE)
        vacio = SistemaParqueadero()
        vacio.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.assertIsNone(vacio.parqueadero)
        self.assertEqual(vacio.tarifas, [])
        self.assertEqual(vacio.obtenerReporte()['capacidad'], 0)
        with self.assertRaisesRegex(ValueError, 'Primero registra'):
            vacio.registrarTarifa(Tarifa(0, 'Carro', 1, 1, date.today()))



class AccesoPruebas(unittest.TestCase):
    """Inicio de sesión, bloqueo de cuenta, roles y contraseñas."""

    def setUp(self):
        self.real = fake_db.instalar()
        fake_db.crear_usuario(self.real, 'Erik', 'Barahona', ADMIN_CORREO, 'Administrador',
                              ADMIN_CLAVE, '1523654987')
        fake_db.crear_usuario(self.real, 'Ana', 'Ruiz', OPERADOR_CORREO, 'Operador', OPERADOR_CLAVE)
        self.s = SistemaParqueadero()

    def datos(self, correo):
        cur = self.real.execute('SELECT * FROM usuario WHERE correo = ?', (correo,))
        return dict(cur.fetchone())

    def test_sin_sesion_no_se_puede_operar(self):
        for accion in (lambda: self.s.registrarIngreso('ABC123'),
                       lambda: self.s.registrarSalida('ABC123'),
                       lambda: self.s.crearParqueadero(Parqueadero(0, 'X', 'Y', 1, '', '')),
                       lambda: self.s.generarReporte()):
            with self.assertRaisesRegex(AccesoDenegado, 'iniciar sesión'):
                accion()

    def test_login_por_correo_y_por_cedula(self):
        self.assertEqual(self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE).rol, 'Administrador')
        self.s.cerrarSesion()
        self.assertIsNone(self.s.usuario)
        self.assertEqual(self.s.iniciarSesion('1523654987', ADMIN_CLAVE).nombre, 'Erik')

    def test_credenciales_incorrectas_no_revelan_que_fallo(self):
        with self.assertRaises(AccesoDenegado) as mal_clave:
            self.s.iniciarSesion(ADMIN_CORREO, 'ClaveMala123')
        with self.assertRaises(AccesoDenegado) as mal_usuario:
            self.s.iniciarSesion('nadie@ejemplo.com', 'ClaveMala123')
        self.assertEqual(str(mal_clave.exception), str(mal_usuario.exception))
        self.assertIsNone(self.s.usuario)

    def test_usuario_sin_contrasena_o_inactivo_no_entra(self):
        self.real.execute("INSERT INTO usuario (nombre, apellido, correo, rol) VALUES "
                          "('Sin','Clave','sin@ejemplo.com','Operador')")
        self.real.execute("UPDATE usuario SET activo = 0 WHERE correo = ?", (OPERADOR_CORREO,))
        self.real.commit()
        with self.assertRaises(AccesoDenegado):
            self.s.iniciarSesion('sin@ejemplo.com', '')
        with self.assertRaises(AccesoDenegado):
            self.s.iniciarSesion(OPERADOR_CORREO, OPERADOR_CLAVE)

    def test_la_contrasena_se_guarda_cifrada(self):
        guardado = self.datos(ADMIN_CORREO)['password_hash']
        self.assertNotIn(ADMIN_CLAVE, guardado)
        self.assertTrue(guardado.startswith('pbkdf2_sha256$'))

    def test_bloqueo_tras_cinco_intentos_fallidos(self):
        for _ in range(4):
            with self.assertRaisesRegex(AccesoDenegado, 'incorrectas'):
                self.s.iniciarSesion(ADMIN_CORREO, 'ClaveMala123')
        self.assertEqual(self.datos(ADMIN_CORREO)['intentos_fallidos'], 4)
        with self.assertRaisesRegex(AccesoDenegado, 'bloqueada'):
            self.s.iniciarSesion(ADMIN_CORREO, 'ClaveMala123')
        # Bloqueada: ni siquiera con la contraseña correcta.
        with self.assertRaisesRegex(AccesoDenegado, 'bloqueada'):
            self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        # Cuando pasa el tiempo de bloqueo, puede entrar de nuevo.
        self.real.execute('UPDATE usuario SET bloqueado_hasta = ? WHERE correo = ?',
                          (datetime.now() - timedelta(minutes=1), ADMIN_CORREO))
        self.real.commit()
        self.assertEqual(self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE).nombre, 'Erik')

    def test_un_login_correcto_reinicia_el_contador(self):
        for _ in range(3):
            with self.assertRaises(AccesoDenegado):
                self.s.iniciarSesion(ADMIN_CORREO, 'ClaveMala123')
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.assertEqual(self.datos(ADMIN_CORREO)['intentos_fallidos'], 0)

    def test_operador_no_puede_administrar(self):
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        with silencio():
            self.s.crearParqueadero(Parqueadero(0, 'Sede', 'Bogotá', 5, '', ''))
        self.s.cerrarSesion()
        self.s.iniciarSesion(OPERADOR_CORREO, OPERADOR_CLAVE)
        prohibidas = [
            lambda: self.s.crearParqueadero(Parqueadero(0, 'Otra', 'Cali', 5, '', '')),
            lambda: self.s.registrarEspacio(Espacio(0, 'A-01', 'A', 'Carro')),
            lambda: self.s.cambiarEstadoEspacio('A-01', 'Mantenimiento'),
            lambda: self.s.registrarTarifa(Tarifa(0, 'Carro', 1000, 5000, date.today() + timedelta(days=5))),
            lambda: self.s.registrarUsuario(Usuario(0, 'N', 'N', 'n@ejemplo.com', 'Operador'), 'Clave12345'),
            lambda: self.s.restablecerPassword(ADMIN_CORREO, 'Clave12345'),
            lambda: self.s.obtenerReporte(),
            lambda: self.s.generarReporte(),
            lambda: self.s.resumenParqueaderos(),
            lambda: self.s.exportarHistorialCSV('x.csv'),
        ]
        for accion in prohibidas:
            with self.assertRaisesRegex(AccesoDenegado, 'rol'):
                accion()

    def test_operador_si_puede_operar_y_el_ingreso_queda_a_su_nombre(self):
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        with silencio():
            self.s.crearParqueadero(Parqueadero(0, 'Sede', 'Bogotá', 5, '', ''))
            self.s.registrarEspacio(Espacio(0, 'A-01', 'A', 'Carro'))
        self.s.registrarTarifa(Tarifa(0, 'Carro', 3000, 20000, date.today() + timedelta(days=5)))
        self.s.cerrarSesion()
        self.s.iniciarSesion(OPERADOR_CORREO, OPERADOR_CLAVE)
        with silencio():
            self.s.registrarCliente(Cliente(0, 'Juan', 'Perez', '123456', '', ''))
            self.s.registrarVehiculo(Vehiculo(0, 'ABC123', 'Kia', 'Rojo', 'Carro'), id_cliente=1)
            ingreso = self.s.registrarIngreso('ABC123')
            factura = self.s.registrarSalida('ABC123')
            self.s.registrarPago(factura.numero, 'Efectivo')
        self.assertEqual(ingreso.usuario.nombre, 'Ana')
        self.assertEqual(self.s.consultarHistorial()[0].usuario.nombre_completo, 'Ana Ruiz')

    def test_cerrar_sesion_quita_los_permisos(self):
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.s.cerrarSesion()
        with self.assertRaises(AccesoDenegado):
            self.s.registrarCliente(Cliente(0, 'A', 'B', '1', '', ''))

    def test_cambiar_contrasena_propia(self):
        self.s.iniciarSesion(OPERADOR_CORREO, OPERADOR_CLAVE)
        with self.assertRaisesRegex(AccesoDenegado, 'actual'):
            self.s.cambiarPassword('Equivocada123', 'NuevaClave456')
        with self.assertRaisesRegex(ValueError, 'contraseña debe'):
            self.s.cambiarPassword(OPERADOR_CLAVE, 'corta')
        self.s.cambiarPassword(OPERADOR_CLAVE, 'NuevaClave456')
        self.s.cerrarSesion()
        with self.assertRaises(AccesoDenegado):
            self.s.iniciarSesion(OPERADOR_CORREO, OPERADOR_CLAVE)
        self.assertEqual(self.s.iniciarSesion(OPERADOR_CORREO, 'NuevaClave456').nombre, 'Ana')

    def test_admin_restablece_contrasena_y_desbloquea(self):
        for _ in range(5):
            with self.assertRaises(AccesoDenegado):
                self.s.iniciarSesion(OPERADOR_CORREO, 'ClaveMala123')
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        self.s.restablecerPassword(OPERADOR_CORREO, 'Reinicio789')
        self.s.cerrarSesion()
        self.assertEqual(self.s.iniciarSesion(OPERADOR_CORREO, 'Reinicio789').nombre, 'Ana')

    def test_usuario_nuevo_entra_con_la_clave_que_le_dio_el_admin(self):
        self.s.iniciarSesion(ADMIN_CORREO, ADMIN_CLAVE)
        with silencio():
            self.s.registrarUsuario(Usuario(0, 'Luis', 'Mora', 'luis@ejemplo.com', 'Operador'), 'ClaveLuis1')
        with self.assertRaisesRegex(ValueError, 'contraseña debe'):
            self.s.registrarUsuario(Usuario(0, 'Eva', 'Rey', 'eva@ejemplo.com', 'Operador'), 'abc')
        self.s.cerrarSesion()
        self.assertEqual(self.s.iniciarSesion('luis@ejemplo.com', 'ClaveLuis1').rol, 'Operador')

    def test_politica_y_hash_de_contrasenas(self):
        for mala in ('corta1', 'soloLetrasAqui', '1234567890', ''):
            with self.assertRaises(ValueError):
                seguridad.validar_password(mala)
        seguridad.validar_password('Clave12345')
        a, b = seguridad.hashear_password('Clave12345'), seguridad.hashear_password('Clave12345')
        self.assertNotEqual(a, b)  # la sal es distinta cada vez
        self.assertTrue(seguridad.verificar_password('Clave12345', a))
        self.assertFalse(seguridad.verificar_password('clave12345', a))
        self.assertFalse(seguridad.verificar_password('Clave12345', None))
        self.assertFalse(seguridad.verificar_password('Clave12345', 'basura'))


if __name__ == '__main__':
    unittest.main()
