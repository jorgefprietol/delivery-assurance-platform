# Experiencia de proyecto — Jorge Prieto

**Delivery Assurance Platform · Proyecto independiente de ingeniería de software · 2026**

Diseño e implementación de una plataforma de control de calidad de entregas, con trazabilidad entre requisitos, criterios de aceptación, evidencias de pruebas y riesgos. Definición de una arquitectura modular mediante puertos y adaptadores, con API REST, persistencia transaccional, control de concurrencia y snapshots históricos de versiones.

Implementación de un workspace web responsive y un servicio FastAPI contenedorizado. Automatización de controles de calidad y publicación de imágenes OCI mediante GitHub Actions, con pruebas unitarias, integración y aceptación HTTP, cobertura, auditoría de dependencias, SBOM y procedencia de construcción.

Implementación de identidades vinculadas a credenciales individuales, autorización por roles, separación entre implementación y revisión y evidencias asociadas al SHA del commit. Migración transaccional e idempotente para conservar historial sin atribuir identidades o commits a datos anteriores.

El repositorio contiene especificación de requisitos, diagramas UML, decisiones de arquitectura, plan de calidad, registro de riesgos y procedimientos de operación. Los resultados se acreditan mediante código, pruebas y ejecuciones del pipeline; no se atribuye empleo, clientes, producción ni métricas de negocio externas.

## Redacción breve para CV

«Desarrollé una plataforma de aseguramiento de entregas con trazabilidad de requisitos, gestión de riesgos y evidencia de aceptación; diseñé un backend modular con control transaccional y concurrencia, y automaticé pruebas y publicación de contenedores mediante GitHub Actions.»

## Evidencias

- Código y documentación: https://github.com/jorgefprietol/delivery-assurance-platform
- Validación automatizada: https://github.com/jorgefprietol/delivery-assurance-platform/actions
- Contrato de servicio: `/openapi.json` en una instancia en ejecución.
- Evidencia de versiones: JSON exportado por el workspace con snapshot y huella SHA-256.
