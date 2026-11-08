import re


class Vehiculo:
    def __init__(self, id_vehiculo, placa, marca, color, tipo_vehiculo, cliente=None):
        self.id_vehiculo = id_vehiculo
        self.placa = placa.strip().upper().replace('-', '').replace(' ', '')
        self.marca = marca
        self.color = color
        self.tipo_vehiculo = tipo_vehiculo
        self.cliente = cliente

    def __str__(self):
        return f'{self.placa} ({self.tipo_vehiculo})'

    def validarPlaca(self):
        """Comprobación básica; no reemplaza la validación oficial de tránsito."""
        if re.fullmatch(r'[A-Z0-9]{5,8}', self.placa):
            print('Placa válida:', self.placa)
            return True
        print('La placa debe tener de 5 a 8 caracteres alfanuméricos.')
        return False

    def actualizarDatos(self, marca, color, tipo_vehiculo):
        self.marca = marca
        self.color = color
        self.tipo_vehiculo = tipo_vehiculo
        print('Datos del vehículo actualizados.')
