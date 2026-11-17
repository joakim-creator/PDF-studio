-- Återställning av 202611170200_inloggning (bolag). Tar bort inloggningsloggen och kolumnerna.
DROP TABLE login_events;
ALTER TABLE users DROP COLUMN last_login_at;
ALTER TABLE users DROP COLUMN totp_enabled_at;
