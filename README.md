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

