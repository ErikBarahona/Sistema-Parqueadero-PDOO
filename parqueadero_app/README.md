# Sistema de parqueaderos MULTISEDES — Programación orientada a objetos

Proyecto en **Python 3**, con interfaz por consola. Conserva las clases del diagrama UML original: `Parqueadero`, `Espacio`, `Usuario`, `Cliente`, `Vehiculo`, `Tarifa`, `Ingreso` y `Factura`.

## Ejecutar

1. Crea la base de datos en MariaDB ejecutando `parqueadero_mariadb.sql`.
   - Si **ya tenías la base creada** (versión anterior), ejecuta en su lugar `migracion_login.sql`, que agrega a la tabla `usuario` las columnas de acceso.
2. Instala las dependencias: `pip install -r requirements.txt`
3. Copia `.env.example` como `.env` y completa host, usuario, contraseña y nombre de la base de datos.
4. **Define la contraseña del administrador** (una sola vez): `python establecer_password.py`. Pide el correo o la cédula del usuario y la contraseña nueva.
5. Ejecuta `python main.py` (o `py main.py` en Windows) e inicia sesión.

Los datos **se guardan en MariaDB** (ya no se usa `data/registros.json`). Cada operación se ejecuta en una transacción: si algo falla, no queda nada a medias. Al iniciar, la sede activa es la primera registrada; con la opción 21 se cambia (la selección dura mientras el programa esté abierto).

## Acceso y roles

Al abrir el programa se pide **correo o cédula** y **contraseña**. El menú muestra solo las opciones del rol de quien inició sesión, y el servicio (`services/sistema.py`) también las verifica, así que la misma regla servirá cuando exista la versión web.

| Rol | Puede |
|---|---|
| **Administrador** | Todo: crear parqueaderos, espacios, tarifas y usuarios, poner espacios en mantenimiento, reportes, exportar CSV, restablecer contraseñas |
| **Operador** | Clientes, vehículos, ingresos, salidas, pagos, consultas, cambiar de sede y cambiar su propia contraseña |

- Las contraseñas **no se guardan**: solo su hash (PBKDF2-SHA256 con sal). Deben tener mínimo 8 caracteres, con letras y números.
- Tras **5 intentos fallidos** la cuenta se bloquea 15 minutos. Un administrador puede desbloquearla restableciendo la contraseña (opción 24).
- Cada ingreso queda a nombre del usuario que inició sesión; ya no se pregunta quién registra.
- Si olvidas la contraseña del administrador, ejecuta de nuevo `python establecer_password.py` (requiere las credenciales del `.env`).

## Ingreso de vehículos

- Si la placa pertenece a un vehículo registrado con un cliente, el ingreso lo identifica por ese cliente.
- Si la placa **no está registrada**, el vehículo entra igual como **visitante**: el sistema pide solo el tipo (Carro, Moto o Bicicleta) y lo guarda sin cliente. Si luego se registra esa placa (opción 7) con un cliente, el visitante queda asociado a él.

## Uso con varios parqueaderos

- **Opción 1 — Crear parqueadero:** no existe límite de uno. Cada sede recibe un ID consecutivo y queda seleccionada al crearla.
- **Opción 20 — Listar parqueaderos:** muestra el ID, nombre, ubicación, capacidad, libres y ocupados de todas las sedes. Un asterisco `*` marca la actual.
- **Opción 21 — Seleccionar parqueadero:** indica el ID de la sede donde trabajarás. El encabezado del menú confirma la sede seleccionada.
- **Opción 22 — Reporte consolidado:** muestra la ocupación, los ingresos recaudados y los pagos pendientes por sede, además de los totales.
- Las opciones **2, 3, 4, 8–16 y 19** corresponden a la **sede activa**. Las opciones 5, 6, 7, 17 y 18 manejan registros compartidos en todo el sistema.
- Una misma placa puede volver a usarse en otra sede **una vez que haya salido de la primera**. Nunca se permiten dos ingresos activos para la misma placa en sedes distintas.
- Cada sede tiene **sus propios códigos de espacio**, por eso es válido utilizar `A-01` en varias sedes sin conflicto.
- Las facturas y los ingresos tienen **consecutivos únicos** en toda la red de parqueaderos, para evitar confusiones.
- Cada exportación CSV se guarda como `reportes/historial_parqueadero_ID.csv`; así no se sobreescribe el historial de otra sede.
- **No hay restricción de acceso por sede:** cualquier usuario con sesión puede seleccionar cualquier sede; la selección solo determina en cuál se opera.

## Pasos para probarlo

1. **Crear parqueadero (opción 1):** define razón social, ubicación y capacidad, por ejemplo `5` espacios. Puedes crear más sedes con la misma opción.
2. **Crear espacios:** registra `A-01` para `Carro` y `M-01` para `Moto`.
3. **Crear usuario (opción 5, solo administrador):** asigna rol `Operador` o `Administrador`, correo o cédula, y una contraseña. Con esos datos inicia sesión.
4. **Crear cliente:** registra a la persona y anota su ID.
5. **Registrar vehículo:** agrega una placa, por ejemplo `ABC123`, y asóciala con el cliente.
6. **Configurar tarifa:** crea una tarifa vigente para el tipo del vehículo. Por ejemplo, hora `3000` COP, día `20000` COP y vigencia futura `2027-12-31`.
7. **Registrar ingreso:** indica la placa y el código del espacio (o déjalo vacío para asignarlo automáticamente). Queda a nombre del usuario con sesión.
8. **Consultar espacios:** ahora aparecerá ocupado.
9. **Registrar salida:** el sistema calcula el cobro por hora o fracción, genera una factura y libera el espacio.
10. **Registrar pago:** paga con efectivo, tarjeta o transferencia. Consulta reportes, facturas e historial.
11. **Exportar CSV:** opción 16, crea `reportes/historial_parqueadero_1.csv` para abrirlo en Excel (el número depende del ID de la sede).
12. **Crear una segunda sede (opción 1):** asigna otro nombre y ubicación, registra sus espacios y tarifas y comprueba que no afectan los de la primera.
13. **Seleccionar sede (opción 21):** alterna entre ambas y consulta su información.
14. **Reiniciar el programa:** comprueba que las dos sedes, los vehículos, los ingresos y las facturas siguen guardados.

## Cómo se relacionan las clases

- `SistemaParqueadero` administra **0..* `Parqueadero`** y mantiene un parqueadero seleccionado.
- Cada `Parqueadero` tiene sus propios `Espacio`, `Tarifa`, `Ingreso` y `Factura`.
- Un `Cliente` puede tener varios `Vehiculo`, y un vehículo puede no tener cliente registrado. Los clientes y vehículos se comparten entre sedes.
- Cada `Ingreso` conecta un `Usuario`, un `Vehiculo`, un `Espacio` y la `Tarifa` aplicable.
- Un `Ingreso` tiene como máximo una `Factura`, que conserva su estado de pago.
- `services/sistema.py` contiene **SistemaParqueadero**, una clase de coordinación que orquesta los objetos anteriores y guarda los datos en MariaDB (la conexión está en `services/db.py`). No sustituye las clases del diagrama.

## Reglas importantes

- Un mismo vehículo **no puede tener dos ingresos activos, aunque sean de distintas sedes**.
- Dos vehículos **no pueden ocupar el mismo espacio** simultáneamente.
- Los espacios en **mantenimiento** no aceptan ingresos hasta que se habiliten; un espacio ocupado no puede ponerse en mantenimiento.
- Solo se pueden asignar espacios que correspondan al tipo de vehículo (`Carro`, `Moto`, `Bicicleta`).
- Para ingresar se requiere una **tarifa vigente** correspondiente al tipo de vehículo.
- Se cobra **por hora o fracción**, como mínimo una hora, con límite de precio diario en bloques de 24 horas.
- Los cobros se registran como **pendientes** hasta que se indique un pago.
- Los informes de dinero **recaudado** solo suman facturas efectivamente pagadas.

## Ejecutar pruebas

Desde la carpeta `parqueadero_app`:

```bash
python -m unittest discover -s tests -v
```

Las pruebas usan una base SQLite en memoria (`tests/fake_db.py`), así que **no modifican tu base de datos real**.

## Alcance académico y mejoras futuras

Este programa es una demostración por consola y no tiene integración con una pasarela de pagos. Para producción, convendría agregar auditoría, restricción de operadores por sede, respaldos de la base de datos y HTTPS (en la versión web), además de proteger el archivo `.env`.

### Ajuste sugerido al diagrama UML

La relación `Cliente — Vehiculo` debería expresarse como **un cliente tiene 0..* vehículos; un vehículo tiene 0..1 cliente**, si se permiten visitantes no registrados. También conviene agregar a `Factura` los atributos `estado_pago`, `fecha_pago` y el método `registrarPago()`, que ya están representados funcionalmente en el código.

## Diagrama de clases actualizado

Se incluye `diagrama_actualizado.puml`, que pueden abrir en un editor compatible con **PlantUML** para obtener el diagrama visual con las clases originales, la relación multisedes y la clase coordinadora. La relación `Ingreso` → `Tarifa` muestra la tarifa aplicada a cada estadía; la factura se genera al registrar la salida.
