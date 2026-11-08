class Espacio:

    def __init__(self, id_espacio, codigo, seccion, tipo_vehiculo, estado="Disponible"):
        self.id_espacio = id_espacio      # para la BD
        self.codigo = codigo              # "A-12", para mostrar
        self.seccion = seccion
        self.tipo_vehiculo = tipo_vehiculo
        self.estado = estado

    def __str__(self):
        return f"{self.codigo} [{self.tipo_vehiculo}] - {self.estado}"

    def actualizarEstado(self, estado):
        if estado in ("Disponible", "Ocupado", "Mantenimiento"):
            self.estado = estado
            print("Estado actualizado correctamente.")
            return True
        print("Estado no válido.")
        return False

    def asignarEspacio(self, tipo_vehiculo):
        if self.estado != "Disponible":
            print("El espacio está ocupado.")
            return False
        if self.tipo_vehiculo != tipo_vehiculo:
            print("Tipo de vehículo incorrecto.")
            return False
        self.estado = "Ocupado"
        print("Espacio asignado correctamente.")
        return True

    def liberarEspacio(self):
        if self.estado == "Ocupado":
            self.estado = "Disponible"
            print("Espacio liberado correctamente.")
        else:
            print("El espacio ya está disponible.")

    def consultarDisponibilidad(self):
        return self.estado == "Disponible"
