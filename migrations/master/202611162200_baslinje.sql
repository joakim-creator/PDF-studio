-- 202611162200_baslinje — masterdatabasens bolagsregister (tenants)
-- Uppgift: F0-04 · Återställning: R-001 i docs/databasandringar.md
--
-- Genererad från SQLAlchemy-modellerna 2026-11-16 (core/models_master.py).
-- Ändras aldrig. Fel rättas med en ny migration.

CREATE TABLE tenants (
	id SERIAL NOT NULL, 
	slug VARCHAR(64) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	database_url TEXT NOT NULL, 
	entra_tenant_id VARCHAR(36), 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug), 
	UNIQUE (entra_tenant_id)
);
