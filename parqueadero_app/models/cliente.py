class Cliente:
    """Dueño de uno o varios vehículos."""

    def __init__(self, id_cliente, nombre, apellido, cedula, telefono, correo):
        self.id_cliente = id_cliente      
        self.nombre = nombre
        self.apellido = apellido
        self.cedula = cedula
        self.telefono = telefono
        self.correo = correo
        self.vehiculos = []

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    def __str__(self):
        return f"{self.nombre_completo} - CC {self.cedula}"

    def registrarCliente(self):
        if self.nombre.strip() != "" and self.cedula.strip() != "":
            print("Cliente registrado correctamente.")
            print("Nombre:", self.nombre_completo)
            print("Cédula:", self.cedula)
            return True
        print("Nombre y cédula son obligatorios.")
        return False

    def actualizarDatos(self, nombre, apellido, telefono, correo):
        self.nombre = nombre
        self.apellido = apellido
        self.telefono = telefono
        self.correo = correo
        print("Datos del cliente actualizados.")

    def agregarVehiculo(self, vehiculo):
        if vehiculo not in self.vehiculos:
            self.vehiculos.append(vehiculo)
            vehiculo.cliente = self       # relación en ambos sentidos
            print("Vehículo asociado al cliente.")

    def consultarVehiculos(self):
        print("VEHÍCULOS DEL CLIENTE:", self.nombre_completo)
        if not self.vehiculos:
            print("No hay vehículos registrados.")
            return
        for v in self.vehiculos:
            print(f"- Placa: {v.placa} | Marca: {v.marca} | Color: {v.color} | Tipo: {v.tipo_vehiculo}")
