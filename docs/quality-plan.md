# Plan de calidad y validación

## Estrategia

Pruebas unitarias: transiciones válidas e inválidas, límites de riesgos y determinismo de huellas. Integración: contrato HTTP, autenticación, campos inválidos, aislamiento de proyectos, auditoría, revisiones, regresiones y conflicto de versión. Persistencia: rollback de escritura y evento juntos, reapertura de base y triggers de inmutabilidad. Concurrencia: dos conexiones independientes compiten con una versión y producen 200/409. Sistema: contenedor real, smoke HTTP y reinicio con preservación de datos. UI: conexión, estados vacíos y operaciones sobre un workspace sintético.

Los escenarios externos se abordan como caja negra sobre HTTP; las reglas puras y rollback se comprueban también con acceso directo al dominio y adaptador. Las pruebas de esta plataforma son distintas de las evidencias que sus operadores registran para otros productos.

## Criterios de salida

- Lint, formato, pruebas y cobertura del backend ≥ 90 % aprobados.
- Dependencias runtime sin vulnerabilidades conocidas reportadas por `pip-audit` en el momento del análisis.
- Imagen construida y aceptación HTTP aprobada antes de publicar.
- Persistencia confirmada después de reiniciar el servicio.
- Documentación sincronizada con las restricciones de la implementación.

## Métricas

El workspace calcula porcentaje de requisitos verificados y riesgos altos abiertos; este porcentaje mide presencia de evidencia aprobada, no cobertura de código del producto registrado. CI calcula cobertura del backend y conserva JUnit, cobertura XML y auditoría de dependencias. Disponibilidad, latencia y usabilidad no tienen resultados atribuidos sin mediciones.

Objetivos para un entorno futuro: acordar carga y dataset representativos, medir latencias p50/p95 y tasa de errores, medir recuperación mediante ejercicios de restore y realizar sesiones observadas con operadores. No se usan cifras de productividad, disponibilidad o satisfacción sin evidencia.

## Usabilidad y revisión técnica

La interfaz muestra el estado actual, las acciones válidas y los bloqueos; evita marcar un requisito como verificado manualmente. Campos con etiquetas, estados vacíos, errores comprensibles y foco visible apoyan la operación. La revisión técnica de un cambio debe comprobar requisito, evidencia, diseño, riesgo y recuperación. Evaluaciones con usuarios y herramientas de accesibilidad se mantienen como trabajo pendiente.
