from datetime import datetime

from models.factura import Factura


class Ingreso:
    """Una estadía: un vehículo ocupando un espacio, atendido por un usuario."""

    def __init__(self, id_ingreso, usuario, espacio, vehiculo, tarifa):
        self.id_ingreso = id_ingreso
        self.usuario = usuario
        self.espacio = espacio
        self.vehiculo = vehiculo
        self.tarifa = tarifa
        self.entrada = None       # datetime completo (soporta estadías de varios días)
        self.salida = None
        self.tiempo = 0           # horas

    # --- Vistas cómodas de fecha/hora ---
    @property
    def fecha(self):
        return self.entrada.date() if self.entrada else None

    @property
    def hora_entrada(self):
        return self.entrada.time() if self.entrada else None

    @property
    def hora_salida(self):
        return self.salida.time() if self.salida else None

    # --- IDs solo para la base de datos ---
    @property
    def id_usuario(self):
        return self.usuario.id_usuario

    @property
    def id_espacio(self):
        return self.espacio.id_espacio

    @property
    def id_vehiculo(self):
        return self.vehiculo.id_vehiculo

    @property
    def id_tarifa(self):
        return self.tarifa.id_tarifa

    # --- Lógica ---
    def registrarIngreso(self):
        if self.entrada is not None:
            print("Este ingreso ya fue registrado.")
            return False
        if not self.tarifa.validarVigencia():
            print("La tarifa está vencida.")
            return False
        if self.tarifa.tipo_vehiculo != self.vehiculo.tipo_vehiculo:
            print("La tarifa no corresponde al tipo de vehículo.")
            return False
        if not self.espacio.asignarEspacio(self.vehiculo.tipo_vehiculo):
            return False

        self.entrada = datetime.now()
        print("Ingreso registrado correctamente.")
        print("Vehículo:", self.vehiculo.placa)
        print("Espacio:", self.espacio.codigo)
        print("Hora:", self.entrada.strftime("%H:%M:%S"))
        return True

    def registrarSalida(self):
        if self.entrada is None:
            print("No existe un ingreso registrado.")
            return 0
        if self.salida is not None:
            print("La salida ya fue registrada.")
            return self.tarifa.calcularCosto(self.tiempo)

        self.salida = datetime.now()
        self.calcularTiempo()
        self.espacio.liberarEspacio()

        valor = self.tarifa.calcularCosto(self.tiempo)
        print("Salida registrada correctamente.")
        print("Tiempo:", round(self.tiempo, 2), "horas")
        print(f"Valor a pagar: ${valor:,.0f}")
        return valor

    def calcularTiempo(self):
        if self.entrada is None or self.salida is None:
            return 0
        self.tiempo = max(0, (self.salida - self.entrada).total_seconds() / 3600)
        return self.tiempo

    def generarFactura(self):
        if self.entrada is None or self.salida is None:
            print("Debe registrar entrada y salida.")
            return None
        self.calcularTiempo()
        factura = Factura(self)
        factura.generarFactura()
        return factura

    def consultarHistorial(self):
        print("HISTORIAL DEL INGRESO")
        print("Fecha:", self.fecha)
        print("Usuario:", self.usuario.nombre_completo)
        print("Espacio:", self.espacio.codigo)
        print("Vehículo:", self.vehiculo.placa)
        print("Tarifa:", self.tarifa.tipo_vehiculo)
        print("Hora entrada:", self.hora_entrada)
        print("Hora salida:", self.hora_salida)
        print("Tiempo:", round(self.tiempo, 2), "horas")
