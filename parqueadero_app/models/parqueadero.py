class Parqueadero:

    def __init__(self, id_parqueadero, razon_social, ubicacion,
                 capacidad, telefono, correo):
        self.id_parqueadero = id_parqueadero   # para la BD
        self.razon_social = razon_social
        self.ubicacion = ubicacion
        self.capacidad = capacidad
        self.telefono = telefono
        self.correo = correo
        self.espacios = []

    def __str__(self):
        return f"{self.razon_social} - {self.ubicacion}"

    @staticmethod
    def crearParqueadero(id_parqueadero):
        """Pide los datos por consola y devuelve un Parqueadero (o None si son inválidos)."""
        print("\n--- CREAR PARQUEADERO ---")
        razon_social = input("Razón social: ").strip()
        ubicacion = input("Ubicación: ").strip()
        capacidad_txt = input("Capacidad (número de espacios): ").strip()
        telefono = input("Teléfono: ").strip()
        correo = input("Correo: ").strip()

        if not razon_social or not ubicacion:
            print("La razón social y la ubicación son obligatorias.")
            return None
        if not capacidad_txt.isdigit() or int(capacidad_txt) <= 0:
            print("La capacidad debe ser un número entero mayor a 0.")
            return None

        parqueadero = Parqueadero(id_parqueadero, razon_social, ubicacion,
                                  int(capacidad_txt), telefono, correo)
        print("Parqueadero creado correctamente.")
        return parqueadero

    def mostrarInformacion(self):
        print("\nINFORMACIÓN DEL PARQUEADERO")
        print("Razón social:", self.razon_social)
        print("Ubicación:", self.ubicacion)
        print("Capacidad:", self.capacidad)
        print("Espacios registrados:", len(self.espacios))
        print("Teléfono:", self.telefono)
        print("Correo:", self.correo)

    def registrarEspacio(self, espacio):
        if len(self.espacios) >= self.capacidad:
            print("Se alcanzó la capacidad máxima.")
            return False
        if self.buscarEspacio(espacio.id_espacio) or self.buscarEspacioPorCodigo(espacio.codigo):
            print("Ya existe un espacio con ese ID o código.")
            return False
        self.espacios.append(espacio)
        print("Espacio registrado correctamente.")
        return True

    def buscarEspacio(self, id_espacio):
        for espacio in self.espacios:
            if espacio.id_espacio == id_espacio:
                return espacio
        return None

    def buscarEspacioPorCodigo(self, codigo):
        for espacio in self.espacios:
            if espacio.codigo.upper() == str(codigo).upper():
                return espacio
        return None

    def buscarEspacioDisponible(self, tipo_vehiculo):
        for espacio in self.espacios:
            if espacio.estado == "Disponible" and espacio.tipo_vehiculo == tipo_vehiculo:
                return espacio
        return None

    def actualizarEspacio(self, id_espacio, estado):
        espacio = self.buscarEspacio(id_espacio)
        if espacio is None:
            print("Espacio no encontrado.")
            return False
        return espacio.actualizarEstado(estado)

    def listarEspacios(self):
        if not self.espacios:
            print("No hay espacios registrados.")
            return
        for espacio in self.espacios:
            print("-", espacio)

    def consultarDisponibilidad(self):
        disponibles = sum(1 for e in self.espacios if e.estado == "Disponible")
        print("Espacios disponibles:", disponibles)
        return disponibles

    def generarReporte(self):
        ocupados = sum(1 for e in self.espacios if e.estado == "Ocupado")
        disponibles = sum(1 for e in self.espacios if e.estado == "Disponible")

        print("\nREPORTE DEL PARQUEADERO")
        print("Razón social:", self.razon_social)
        print("Capacidad:", self.capacidad)
        print("Registrados:", len(self.espacios))
        print("Ocupados:", ocupados)
        print("Disponibles:", disponibles)
