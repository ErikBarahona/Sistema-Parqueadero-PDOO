import math
from datetime import datetime


class Factura:
    consecutivo = 1
    METODOS_PAGO = ('Efectivo', 'Tarjeta', 'Transferencia')

    def __init__(self, ingreso, numero=None, parqueadero=None):
        if ingreso.salida is None:
            raise ValueError('No es posible facturar un ingreso sin salida.')
        if numero is None:
            numero = Factura.consecutivo
        self.numero = numero
        self.id_factura = numero  # nombre usado en el diagrama UML
        Factura.consecutivo = max(Factura.consecutivo, numero + 1)

        self.ingreso = ingreso
        self.parqueadero = parqueadero
        self.cliente = ingreso.vehiculo.cliente
        self.vehiculo = ingreso.vehiculo
        self.tarifa = ingreso.tarifa
        self.horas = max(1, math.ceil(ingreso.tiempo))
        self.fecha = datetime.now()
        self.total = self.tarifa.calcularCosto(ingreso.tiempo)
        self.metodo_pago = None
        self.fecha_pago = None

    @property
    def pagada(self):
        return self.fecha_pago is not None

    def registrarPago(self, metodo_pago):
        if self.pagada:
            print('Esta factura ya fue pagada.')
            return False
        if metodo_pago not in self.METODOS_PAGO:
            print('Método de pago no válido.')
            return False
        self.metodo_pago = metodo_pago
        self.fecha_pago = datetime.now()
        print(f'Pago registrado: ${self.total:,.0f} ({metodo_pago}).')
        return True

    def generarFactura(self):
        print('\n' + '=' * 44)
        print('          FACTURA DEL PARQUEADERO')
        print('=' * 44)
        if self.parqueadero:
            print(f'Sede: {self.parqueadero.razon_social} (ID {self.parqueadero.id_parqueadero})')
            print(f'Ubicación: {self.parqueadero.ubicacion}')
        print(f'Factura Nro.: {self.numero}')
        print(f'Fecha: {self.fecha.strftime("%d/%m/%Y %H:%M")}')
        if self.cliente:
            print(f'Cliente: {self.cliente.nombre_completo} | CC: {self.cliente.cedula}')
        else:
            print('Cliente: No registrado')
        print(f'Vehículo: {self.vehiculo.placa} ({self.vehiculo.tipo_vehiculo})')
        print(f'Espacio: {self.ingreso.espacio.codigo}')
        print(f'Entrada: {self.ingreso.entrada.strftime("%d/%m/%Y %H:%M")}')
        print(f'Salida: {self.ingreso.salida.strftime("%d/%m/%Y %H:%M")}')
        print(f'Tiempo facturado: {self.horas} hora(s)')
        print(f'Tarifa por hora: ${self.tarifa.precio_hora:,.0f}')
        print(f'TOTAL: ${self.total:,.0f}')
        print(f'Estado: {"PAGADA" if self.pagada else "PENDIENTE"}')
        if self.pagada:
            print(f'Método de pago: {self.metodo_pago}')
        print('=' * 44)

    def imprimirFactura(self):
        self.generarFactura()

    def obtenerTotal(self):
        return self.total
