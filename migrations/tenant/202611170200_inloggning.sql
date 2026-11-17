-- 202611170200_inloggning — inloggningsloggen och kolumnerna för engångskod och senaste inloggning
-- Uppgift: F0-13 · Återställning: R-003 i docs/databasandringar.md
--
-- Genererad från SQLAlchemy-modellerna 2026-11-17 (models.py).
-- Ändras aldrig. Fel rättas med en ny migration.

ALTER TABLE users ADD COLUMN totp_enabled_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP WITH TIME ZONE;

CREATE TABLE login_events (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	username VARCHAR(120) NOT NULL, 
	method VARCHAR(16) NOT NULL, 
	outcome VARCHAR(20) NOT NULL, 
	ip VARCHAR(45) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_login_events_method CHECK (method IN ('password', 'totp', 'microsoft')), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_login_events_created_at ON login_events (created_at);

CREATE INDEX ix_login_events_user_id ON login_events (user_id);
