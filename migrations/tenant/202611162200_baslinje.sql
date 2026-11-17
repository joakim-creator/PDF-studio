-- 202611162200_baslinje — bolagsdatabasens tabeller: användare, dokument, versioner, delningar,
-- kommentarer, jobb, AI-kostnader och händelselogg
-- Uppgift: F0-04, F0-05 · Återställning: R-002 i docs/databasandringar.md
--
-- Genererad från SQLAlchemy-modellerna 2026-11-16 (models.py).
-- Ändras aldrig. Fel rättas med en ny migration.

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(120) NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	email VARCHAR(255), 
	entra_oid VARCHAR(36), 
	password_hash VARCHAR(255), 
	totp_secret TEXT, 
	is_admin BOOLEAN NOT NULL, 
	active BOOLEAN NOT NULL, 
	failed_logins INTEGER NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_failed_logins CHECK (failed_logins >= 0), 
	UNIQUE (username), 
	UNIQUE (entra_oid)
);

CREATE TABLE audit_events (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	area VARCHAR(32) NOT NULL, 
	action VARCHAR(32) NOT NULL, 
	description TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_events_created_at ON audit_events (created_at);

CREATE INDEX ix_audit_events_user_id ON audit_events (user_id);

CREATE TABLE documents (
	id SERIAL NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	owner_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	purge_after TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_documents_owner_id ON documents (owner_id);

CREATE TABLE user_permissions (
	user_id INTEGER NOT NULL, 
	permission VARCHAR(64) NOT NULL, 
	granted_by INTEGER NOT NULL, 
	granted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id, permission), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(granted_by) REFERENCES users (id)
);

CREATE INDEX ix_user_permissions_granted_by ON user_permissions (granted_by);

CREATE TABLE document_shares (
	document_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	granted_by INTEGER NOT NULL, 
	granted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (document_id, user_id), 
	FOREIGN KEY(document_id) REFERENCES documents (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(granted_by) REFERENCES users (id)
);

CREATE INDEX ix_document_shares_granted_by ON document_shares (granted_by);

CREATE INDEX ix_document_shares_user_id ON document_shares (user_id);

CREATE TABLE document_versions (
	id SERIAL NOT NULL, 
	document_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	parent_version_id INTEGER, 
	storage_key VARCHAR(255) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	page_count INTEGER NOT NULL, 
	size_bytes BIGINT NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_versions_no UNIQUE (document_id, version_no), 
	CONSTRAINT ck_document_versions_no CHECK (version_no >= 1), 
	CONSTRAINT ck_document_versions_pages CHECK (page_count >= 1), 
	CONSTRAINT ck_document_versions_size CHECK (size_bytes >= 1), 
	CONSTRAINT ck_document_versions_source CHECK (source IN ('upload', 'merge', 'split', 'pages', 'annotate', 'ocr', 'compress')), 
	CONSTRAINT ck_document_versions_parent CHECK ((version_no = 1) = (parent_version_id IS NULL)), 
	FOREIGN KEY(document_id) REFERENCES documents (id), 
	FOREIGN KEY(parent_version_id) REFERENCES document_versions (id), 
	UNIQUE (storage_key), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_document_versions_created_by ON document_versions (created_by);

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);

CREATE INDEX ix_document_versions_parent_version_id ON document_versions (parent_version_id);

CREATE TABLE annotations (
	id SERIAL NOT NULL, 
	version_id INTEGER NOT NULL, 
	page INTEGER NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	geometry JSON NOT NULL, 
	body TEXT, 
	author_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_annotations_page CHECK (page >= 1), 
	CONSTRAINT ck_annotations_kind CHECK (kind IN ('highlight', 'underline', 'freetext', 'note', 'ink', 'stamp')), 
	FOREIGN KEY(version_id) REFERENCES document_versions (id), 
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE INDEX ix_annotations_author_id ON annotations (author_id);

CREATE INDEX ix_annotations_version_id ON annotations (version_id);

CREATE TABLE jobs (
	id SERIAL NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	version_id INTEGER NOT NULL, 
	result_version_id INTEGER, 
	requested_by INTEGER NOT NULL, 
	cost_sek NUMERIC(12, 4) NOT NULL, 
	error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_jobs_kind CHECK (kind IN ('ocr', 'word', 'excel', 'podcast', 'compress', 'image')), 
	CONSTRAINT ck_jobs_status CHECK (status IN ('queued', 'running', 'done', 'failed')), 
	CONSTRAINT ck_jobs_cost CHECK (cost_sek >= 0), 
	FOREIGN KEY(version_id) REFERENCES document_versions (id), 
	FOREIGN KEY(result_version_id) REFERENCES document_versions (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_jobs_requested_by ON jobs (requested_by);

CREATE INDEX ix_jobs_result_version_id ON jobs (result_version_id);

CREATE INDEX ix_jobs_status_created ON jobs (status, created_at);

CREATE INDEX ix_jobs_version_id ON jobs (version_id);

CREATE TABLE ai_usage (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	job_id INTEGER, 
	model VARCHAR(64) NOT NULL, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	cost_sek NUMERIC(12, 4) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_ai_usage_tokens CHECK (input_tokens >= 0 AND output_tokens >= 0), 
	CONSTRAINT ck_ai_usage_cost CHECK (cost_sek >= 0), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id)
);

CREATE INDEX ix_ai_usage_created_at ON ai_usage (created_at);

CREATE INDEX ix_ai_usage_job_id ON ai_usage (job_id);

CREATE INDEX ix_ai_usage_user_id ON ai_usage (user_id);
