# Especificación de requisitos

## Contexto, objetivos y alcance

Producto: workspace de control de calidad para equipos que necesitan justificar la preparación de una entrega. Actores: implementador (`engineer`) y revisor (`reviewer`), con sujetos y credenciales distintos. Resultado: una versión con snapshot verificable, atribución de operadores y commits de origen. Fuera del alcance inicial: directorio corporativo de usuarios, ejecución remota de pruebas, planificación financiera y despliegue de los productos registrados.

Las necesidades se derivan de escenarios de control de cambios y entrega. No se atribuyen entrevistas con clientes ni validaciones externas que no se hayan realizado. El documento organiza propósito, funciones, interfaces, restricciones y aceptación; no afirma certificación ni conformidad formal con una norma.

## Requisitos y trazabilidad

| ID     | Necesidad / criterio de aceptación                               | Implementación                       | Evidencia automatizada                                                            |
| ------ | ---------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------- |
| RF-01  | Crear proyectos y consultar su alcance aislado                   | `DeliveryService.project`, dashboard | `test_project_isolation`                                                          |
| RF-02  | Registrar requisitos con aceptación y prioridad                  | `requirement`, modelos HTTP          | `test_invalid_project_input`, recorrido de entrega                                |
| RF-03  | Aplicar aprobación antes de implementación                       | `transition`, `advance`              | `test_illegal_domain_transition`                                                  |
| RF-04  | Verificar exclusivamente con evidencia aprobada                  | `evidence`                           | `test_evidence_requires_implementation`, `test_failed_retest_blocks_release`      |
| RF-05  | Invalidar verificación cuando cambie el requisito                | `revise`                             | `test_revision_invalidates_evidence_preserves_release`                            |
| RF-06  | Bloquear entrega por requisitos pendientes o riesgo alto abierto | `evaluate_gate`, `release`           | `test_empty_gate`, `test_high_risk_mitigation`                                    |
| RF-07  | Conservar instantánea y huella de cada versión                   | `snapshot_digest`, `release`         | `test_complete_delivery_and_snapshot`, `test_snapshot_digest_order_and_tampering` |
| RF-08  | Registrar cada mutación y preservar el historial                 | `event`, triggers SQLite             | `test_sqlite_persistence_rollback_and_immutability`                               |
| RNF-01 | Rechazar cambios basados en versiones obsoletas con HTTP 409     | `check_version`                      | `test_stale_update`, `test_concurrent_optimistic_writers`                         |
| RNF-02 | Proteger datos de negocio mediante API key                       | dependencia HTTP                     | `test_authentication`, `test_short_key_rejected`                                  |
| RNF-03 | Preservar datos tras reiniciar                                   | SQLite WAL + volumen                 | prueba de persistencia local y job `container`                                    |
| RNF-04 | Mantener cobertura del backend ≥ 90 %                            | pytest-cov                           | gate en CI                                                                        |
| RNF-05 | Permitir operación por teclado y tamaños móviles                 | HTML semántico, CSS responsive       | inspección de HTML/CSS; validación visual y accesibilidad pendientes |
| RNF-06 | Exponer diagnósticos y correlación sin registrar credenciales    | health, X-Request-ID                 | `test_health_and_security_headers`                                                |

## Historias y casos de uso

- Como responsable de una entrega, quiero definir criterios observables para decidir si una función está lista. Aceptación: requisito creado en borrador con revisión 1.
- Como operador, quiero conocer un conflicto de edición para no sobrescribir cambios ajenos. Aceptación: solo una de dos escrituras simultáneas con la misma versión se confirma.
- Como responsable de calidad, quiero que una regresión bloquee una versión. Aceptación: registrar una prueba fallida revierte el requisito a implementado.
- Como responsable de una entrega, quiero exportar su evidencia para revisarla después. Aceptación: cambios posteriores no modifican su snapshot ni su huella.

Caso extendido «Registrar entrega»: operador autenticado elige proyecto y etiqueta única; el servicio abre transacción, obtiene alcance, evidencia y riesgos, evalúa el gate, persiste snapshot y auditoría, confirma y devuelve HTTP 201. Si el gate falla o la etiqueta existe, devuelve HTTP 409 y no agrega una entrega ni un evento parcial.

## Interfaces y restricciones

REST JSON bajo `/api`; contrato en `/openapi.json` con esquema de API key. `/api/me` devuelve sujeto y rol autenticados. Identificadores UUID, campos limitados y claves extra rechazadas. Todos los requisitos registrados, incluidas prioridades `should` y `could`, forman parte del gate actual. Prioridad indica orden de trabajo, no exclusión de alcance. Credenciales individuales, una instancia, SQLite local en volumen, timeout de escritura de 10 s.

## Controles de identidad y commit

| ID    | Criterio de aceptación                                                                                 | Evidencia                                                                                          |
| ----- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| RF-09 | Auditoría atribuye el sujeto autenticado e ignora suplantación mediante `X-Actor`                      | `test_authenticated_identity_and_untrusted_header`                                                 |
| RF-10 | Implementador no aprueba, verifica ni autoriza entregas; revisor no modifica alcance ni implementación | `test_engineer_cannot_approve_verify_or_release`, `test_reviewer_cannot_implement_or_modify_scope` |
| RF-11 | Evidencia solo se acepta para el SHA completo del commit implementado                                  | `test_commit_is_required_and_evidence_must_match`                                                  |
| RF-12 | Un cambio de rol no permite revisar la propia implementación                                           | `test_role_change_does_not_allow_self_review`                                                      |
| RF-13 | Migración conserva entregas históricas y reinicia requisitos sin atribución verificable                | `test_legacy_migration_invalidates_unattributed_verification`                                      |

El SHA se valida como 40 caracteres hexadecimales en minúsculas. Es una asociación al commit; la autenticidad de reportes externos requiere integración adicional con CI o firmas.
