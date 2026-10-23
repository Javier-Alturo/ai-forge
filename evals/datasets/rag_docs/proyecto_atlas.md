# Proyecto Atlas (documento técnico ficticio)

Atlas es la plataforma interna de reservas de la empresa ficticia Acme Labs.

## Stack
- Backend en Python 3.12 con FastAPI.
- Base de datos PostgreSQL 16.
- Caché con Redis; los resultados de búsqueda se guardan con un TTL de 15 minutos.

## Equipo y entregas
El líder técnico del proyecto es Mateo Gil. La versión 2.0 se desplegó a producción el 3 de marzo de 2026.

## Objetivos de servicio
El SLO de latencia es de 300 milisegundos en el percentil 95 para el endpoint de búsqueda.
Las alertas se envían al canal #atlas-oncall.
