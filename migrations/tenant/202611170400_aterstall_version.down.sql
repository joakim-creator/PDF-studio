-- Återställning av 202611170400_aterstall_version (bolag). Faller om det finns versioner med källan 'restore' —
-- de måste först tas bort eller få en annan källa (se R-004).
ALTER TABLE document_versions DROP CONSTRAINT ck_document_versions_source;
ALTER TABLE document_versions ADD CONSTRAINT ck_document_versions_source CHECK (source IN ('upload', 'merge', 'split', 'pages', 'annotate', 'ocr', 'compress'));
