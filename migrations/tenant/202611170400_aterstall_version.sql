-- 202611170400_aterstall_version — versionskällan 'restore': en äldre version återställs som en ny version
-- Uppgift: F1-08 · Återställning: R-004 i docs/databasandringar.md
--
-- Ändras aldrig. Fel rättas med en ny migration.

ALTER TABLE document_versions DROP CONSTRAINT ck_document_versions_source;

ALTER TABLE document_versions ADD CONSTRAINT ck_document_versions_source CHECK (source IN ('upload', 'merge', 'split', 'pages', 'annotate', 'ocr', 'compress', 'restore'));
