# Operación y recuperación

## Configuración

`API_KEY`: mínimo 32 caracteres; genera 32 bytes aleatorios con `scripts/setup.ps1`. `APP_PORT`: 18130 por defecto, loopback. `DATABASE_PATH`: `/data/delivery.db` en el contenedor. `DELIVERY_SUBNET`: `10.254.120.0/28` por defecto; permite elegir un rango libre si Docker agota los pools automáticos o hay conflicto con redes del host. `.env`, bases y artefactos se excluyen del repositorio y del contexto de construcción.

```powershell
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail 100
Invoke-RestMethod http://127.0.0.1:18130/health/ready
```

Liveness informa que el proceso responde; readiness consulta la base. No exponen datos de negocio. El contrato se obtiene en `/openapi.json`. Los datos `/api` necesitan `X-API-Key`. Los logs incluyen ruta, estado y correlación del request; no registran headers ni bodies.

## Backup consistente

Usa la API de backup de SQLite para incluir operaciones WAL confirmadas. Copiar solo el archivo `.db` de una base activa puede producir un backup incompleto.

```powershell
docker compose exec delivery python -c "import sqlite3; s=sqlite3.connect('/data/delivery.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close(); s.close()"
New-Item -ItemType Directory -Force backups
$containerId = docker compose ps -q delivery
docker cp "${containerId}:/data/backup.db" ./backups/delivery.db
```

Guarda backups fuera del equipo, controla acceso y acuerda retención. Los backups contienen el workspace. No se incluyen datos reales de terceros en evidencias públicas.

## Recuperación

Detén el servicio, conserva el volumen anterior y monta el backup en un volumen nuevo mediante un contenedor de mantenimiento. Ajusta propietario a UID 10001. Verifica `PRAGMA integrity_check`, arranca con el volumen recuperado, consulta proyectos, requisitos y versiones y compara sus huellas. Realiza el ejercicio en una copia antes de reemplazar el workspace operativo. Nunca uses `docker compose down -v` para un workspace cuyos datos deseas conservar.

## Actualización y rollback

Cada commit aprobado produce una imagen `ghcr.io/jorgefprietol/delivery-assurance-platform:sha-<commit>`. Para usarla, crea un override Compose con `services.delivery.image` apuntando a la etiqueta y ejecuta `docker compose -f compose.yaml -f override.yaml up -d --no-build --wait`. Verifica health y smoke en un workspace aislado; el smoke crea datos sintéticos. Con un esquema compatible, rollback significa volver a la etiqueta anterior manteniendo el volumen. Si cambia el esquema, se necesita plan de migración y recuperación antes de publicar.

No existe despliegue automático a un servidor externo en el baseline. La publicación a GHCR utiliza el token temporal de Actions, no un secreto persistente del usuario. La visibilidad de un paquete GHCR se administra separadamente de la visibilidad del repositorio.
