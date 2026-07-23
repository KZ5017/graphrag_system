# ADR-0001: Moduláris monolit és tartós worker

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

Az indexelés hosszú, több adattárat érintő és restart után folytatandó
folyamat. FastAPI request vagy `BackgroundTasks` nem biztosít tartós
életciklust.

## Döntés

Egy Python package készül, külön indítható API- és worker-processzel.
A job queue első verziója PostgreSQL-alapú lease és heartbeat
mechanizmussal.

## Következmény

- nincs korai microservice-komplexitás;
- a job nem vész el API restartkor;
- Redis/Dramatiq később adapterként bevezethető;
- az application service-ek nem függnek FastAPI-tól.

