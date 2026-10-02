# Riesgos, planificación y deuda técnica

## Registro de riesgos del producto

| Riesgo | P × I | Control actual | Evolución |
| --- | --- | --- | --- |
| Pérdida del volumen | 3 × 5 | Persistencia Docker y procedimiento de backup | Backups programados y ejercicios de restore |
| Sobrescritura concurrente | 3 × 4 | Versiones y transacciones; prueba con escritores simultáneos | Mantener contrato al migrar persistencia |
| Evidencia obsoleta | 4 × 4 | Revisión vinculada, invalidación y snapshots | Integración con reportes firmados de CI |
| Credencial compartida comprometida | 3 × 5 | API key aleatoria, loopback, archivos ignorados | OIDC, RBAC, rotación y secretos gestionados |
| Dependencias vulnerables | 3 × 4 | Auditoría runtime y versiones fijadas | Escaneo de imagen completa y política de remediación |
| Crecimiento de datos y bloqueo | 3 × 3 | Índice, WAL, timeout y una instancia | Paginación, medición y PostgreSQL si se necesita |
| Falsa atribución de garantías | 2 × 4 | Documentar evidencia declarada y límites | Revisión de documentación en cada versión |

## Proceso incremental

La unidad de trabajo es un requisito con criterio observable. Flujo Kanban propuesto: definición, aprobado, implementación, verificación y entrega. Se usa aprobación para estabilizar alcance y revisiones para gestionar cambios. Cada incremento necesita evidencia de aceptación, revisión técnica y respuesta a riesgos altos. El repositorio conserva el baseline inicial implementado; no representa un historial ficticio de sprints ni trabajo de un equipo externo.

Baseline: núcleo transaccional, API, UI, contenedor y CI con publicación OCI. Siguiente incremento: identidades individuales y separación de aprobación/verificación. Después: paginación, PostgreSQL, integración con artefactos CI y observabilidad operacional. Las fechas se acuerdan según capacidad; no se inventan estimaciones de un equipo.

## Deuda técnica explícita

Identidad de operador compartida; consulta sin paginación; almacenamiento JSON con relaciones comprobadas por el servicio; evolución de esquema aún sin framework de migraciones; evidencia declarativa; una sola instancia; sin medición de carga, auditoría formal de accesibilidad ni pruebas de penetración. Las decisiones simplifican el baseline y se acompañan de condiciones concretas para revisarlas.

Modernización propuesta: escribir un adaptador PostgreSQL que conserve transacciones y casos de concurrencia, ejecutar el mismo plan de pruebas, migrar snapshots con verificación de huellas y hacer corte con backup y rollback. Evitar reescritura total y preservar contratos HTTP.
