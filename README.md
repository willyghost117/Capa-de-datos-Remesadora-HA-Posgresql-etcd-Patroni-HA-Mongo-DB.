Este es un proyecto Académico para la demostración que una arquitectura HA. En general centra en la capa de datos con Posgresql que pasa pruebas de Faillover.

Contenedor	Función
globalremit-api-gateway	Aplicación Django. Sirve la página web y ejecuta inserciones hacia PostgreSQL por HAProxy.

globalremit-patroni-pg1	Nodo PostgreSQL administrado por Patroni. Puede ser líder o réplica.

globalremit-patroni-pg2	Otro nodo PostgreSQL. Puede ser líder o réplica.

globalremit-patroni-pg3	Otro nodo PostgreSQL. Puede ser líder o réplica.

globalremit-patroni-etcd	Coordinador del clúster. Patroni usa etcd para saber quién es líder y evitar dos líderes al mismo tiempo.

globalremit-patroni-haproxy	Entrada estable hacia PostgreSQL. Redirige las conexiones al nodo que esté como líder.

globalremit-mongo1	Nodo MongoDB del replica set. Puede ser PRIMARY o SECONDARY.

globalremit-mongo2	Nodo MongoDB del replica set. Puede ser PRIMARY o SECONDARY.

globalremit-mongo3	Nodo MongoDB del replica set. Puede ser PRIMARY o SECONDARY.

globalremit-mongo-init	Contenedor temporal que inicializa el replica set de MongoDB. No debe quedar corriendo permanentemente.


Guía Genérica de Despliegue
Requisitos
Git.
Docker Desktop o Docker Engine.
Docker Compose v2.
PowerShell, Bash o terminal equivalente.
Puertos configurados disponibles.
1. Clonar el repositorio
git clone <URL_DEL_REPOSITORIO>
cd <NOMBRE_DEL_REPOSITORIO>

2. Configurar credenciales
Revise las variables del archivo:
Migración/docker-compose.yml
Configure contraseñas seguras para:
PostgreSQL.
Usuario de replicación.
Usuario de la API.
Administrador MongoDB.
Publicador Outbox.
En un despliegue formal deben suministrarse mediante .env, Docker Secrets o un gestor de secretos.

3. Crear el keyfile de MongoDB
Cree la carpeta:
mkdir -p Migración/secrets
Genere una clave aleatoria válida para la autenticación interna del replica set.
En Linux:
openssl rand -base64 756 > Migración/secrets/mongo-keyfile
chmod 400 Migración/secrets/mongo-keyfile
En Windows PowerShell:
New-Item -ItemType Directory -Force ".\Migración\secrets"

$bytes = New-Object byte[] 756
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[IO.File]::WriteAllText(
    "$PWD\Migración\secrets\mongo-keyfile",
    [Convert]::ToBase64String($bytes)
)
$rng.Dispose

4. Validar la configuración
docker compose -f Migración/docker-compose.yml config --quiet

6. Construir y levantar los servicios
docker compose -f Migración/docker-compose.yml up -d --build

8. Revisar los contenedores
docker compose -f Migración/docker-compose.yml ps
La arquitectura debe incluir:
API Gateway.
Publicador Outbox.
HAProxy.
etcd.
Tres nodos PostgreSQL con Patroni.
Tres nodos MongoDB.
Inicializador del replica set.
El inicializador de MongoDB puede finalizar con estado exitoso después de completar su función.

10. Verificar los registros
docker compose -f Migración/docker-compose.yml logs --tail 100
Para seguirlos en tiempo real:
docker compose -f Migración/docker-compose.yml logs -f

12. Inicialización del primer despliegue
En una instalación nueva se debe:
Crear la base PostgreSQL.
Ejecutar el DDL.
Aplicar los datos semilla o restaurar un respaldo.
Crear los roles PostgreSQL.
Inicializar el replica set MongoDB.
Crear el administrador MongoDB.
Aplicar los roles MongoDB.
Restaurar los datos documentales cuando corresponda.
Estos pasos no son necesarios cuando ya existen volúmenes Docker inicializados.

14. Acceso a los servicios
Utilice los puertos publicados en docker-compose.yml:
API Gateway:      http://localhost:<PUERTO_API>
HAProxy Stats:    http://localhost:<PUERTO_STATS>
PostgreSQL:       localhost:<PUERTO_POSTGRESQL>
MongoDB:          localhost:<PUERTO_MONGODB>

15. Detener el proyecto
Sin eliminar datos:
docker compose -f Migración/docker-compose.yml down
Para volver a iniciarlo:
docker compose -f Migración/docker-compose.yml up -d
No utilice down -v salvo que desee eliminar completamente las bases de datos y comenzar desde cero.

