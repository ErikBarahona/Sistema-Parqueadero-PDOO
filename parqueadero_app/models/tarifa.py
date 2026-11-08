import math
from datetime import date


class Tarifa:
    """Valores en pesos colombianos, por hora/fracción y por día."""

    def __init__(self, id_tarifa, tipo_vehiculo, precio_hora, precio_dia, fecha_vigencia):
        if precio_hora <= 0 or precio_dia <= 0:
            raise ValueError('Los valores de la tarifa deben ser mayores que cero.')
        self.id_tarifa = id_tarifa
        self.tipo_vehiculo = tipo_vehiculo
        self.precio_hora = precio_hora
        self.precio_dia = precio_dia
        self.fecha_vigencia = (date.fromisoformat(fecha_vigencia)
                               if isinstance(fecha_vigencia, str) else fecha_vigencia)

    def __str__(self):
        return f'Tarifa {self.tipo_vehiculo} (hasta {self.fecha_vigencia})'

    def validarVigencia(self, fecha=None):
        return (fecha or date.today()) <= self.fecha_vigencia

    @staticmethod
    def obtenerTarifaPorTipo(tarifas, tipo_vehiculo, fecha=None):
        vigentes = [t for t in tarifas if t.tipo_vehiculo == tipo_vehiculo and t.validarVigencia(fecha)]
        return max(vigentes, key=lambda t: t.id_tarifa) if vigentes else None

    def calcularCosto(self, horas):
        """Cobra cada hora iniciada (mínimo una), sin superar el valor diario por 24 h."""
        horas = max(1, math.ceil(horas))
        dias, horas_restantes = divmod(horas, 24)
        return dias * self.precio_dia + min(horas_restantes * self.precio_hora, self.precio_dia)

    def mostrarTarifa(self):
        print('TARIFA DEL PARQUEADERO')
        print(f'Tipo de vehículo: {self.tipo_vehiculo}')
        print(f'Precio por hora: ${self.precio_hora:,.0f}')
        print(f'Precio por día: ${self.precio_dia:,.0f}')
        print(f'Vigente hasta: {self.fecha_vigencia}')
