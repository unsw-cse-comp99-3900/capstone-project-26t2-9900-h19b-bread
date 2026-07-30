-- ============================================================
-- 19.7_database (ER-standard fused schema)
-- File: 19.7database.sql
-- Aligns with: DATABASE/19.7_IDEAL_ER_DIAGRAM.pdf
--
-- ER Layers:
--   A Identity & Publishing : enterprise, app_user, api_submission,
--                             api_version, api_version_event, api_specification
--   B Catalogue Enrichment  : attributes on enterprise / submission / version /
--                             auth_metadata (CSV / xlsx catalogue)
--   C Connection Compatibility : api_schema, schema_field (payload store, optional),
--                                compatibility_result (API A.output → B.input check)
--   D Publish Validation       : validation_run, validation_result
--   E Mapping & Transform      : schema_mapping, mapping_rule, transform_run
--
-- Layer C (connection check) uses api_version metadata only:
--   input_format / output_format / capability_category
--   Result states: COMPATIBLE | INCOMPATIBLE | MISSING_INFORMATION (+ reason)
--   Not field mapping; not deep payload processing; not single-API publish validation.
--   Layer E remains optional and only weakly linked via compatibility_result_id.
--
-- ER rules applied in this revision:
--   1) Every relationship has an explicit FK + ON DELETE policy
--   2) Cardinality enforced by UNIQUE / CHECK where required (1:1, at-most-one)
--   3) No duplicate "truth" columns (field rules live only in mapping_rule)
--   4) Weak entities depend on strong parents (CASCADE)
--   5) Associative entities (mapping / compatibility / transform) use role-named FKs
--   6) Create order follows dependency (parents before children)
-- ============================================================

-- ------------------------------------------------------------
-- DROP (children -> parents)
-- ------------------------------------------------------------
DROP FUNCTION IF EXISTS enforce_connection_schema_roles() CASCADE;
DROP TABLE IF EXISTS transform_run CASCADE;
DROP TABLE IF EXISTS mapping_rule CASCADE;
DROP TABLE IF EXISTS connection_validation_stage_result CASCADE;
DROP TABLE IF EXISTS connection_validation_run CASCADE;
DROP TABLE IF EXISTS compatibility_reason_item CASCADE;
DROP TABLE IF EXISTS compatibility_issue CASCADE;   -- predecessor table name
DROP TABLE IF EXISTS compatibility_result CASCADE;
DROP TABLE IF EXISTS format_alias CASCADE;
DROP TABLE IF EXISTS schema_field CASCADE;
DROP TABLE IF EXISTS api_schema CASCADE;
DROP TABLE IF EXISTS schema_mapping CASCADE;
DROP TABLE IF EXISTS validation_result CASCADE;
DROP TABLE IF EXISTS validation_run CASCADE;
DROP TABLE IF EXISTS auth_metadata CASCADE;
DROP TABLE IF EXISTS api_specification CASCADE;
DROP TABLE IF EXISTS api_version_event CASCADE;
DROP TABLE IF EXISTS api_version CASCADE;
DROP TABLE IF EXISTS api_submission CASCADE;
DROP TABLE IF EXISTS app_user CASCADE;
DROP TABLE IF EXISTS enterprise CASCADE;

DROP TYPE IF EXISTS enterprise_status CASCADE;
DROP TYPE IF EXISTS user_role CASCADE;
DROP TYPE IF EXISTS user_status CASCADE;
DROP TYPE IF EXISTS api_protocol_type CASCADE;
DROP TYPE IF EXISTS api_submission_status CASCADE;
DROP TYPE IF EXISTS api_version_status CASCADE;
DROP TYPE IF EXISTS specification_type CASCADE;
DROP TYPE IF EXISTS specification_source_type CASCADE;
DROP TYPE IF EXISTS auth_method_type CASCADE;
DROP TYPE IF EXISTS validation_overall_status CASCADE;
DROP TYPE IF EXISTS validation_stage_type CASCADE;
DROP TYPE IF EXISTS validation_stage_status CASCADE;
DROP TYPE IF EXISTS mapping_lifecycle_status CASCADE;
DROP TYPE IF EXISTS mapping_completeness CASCADE;
DROP TYPE IF EXISTS mapping_status CASCADE;
DROP TYPE IF EXISTS version_event_type CASCADE;
DROP TYPE IF EXISTS api_category_type CASCADE;
DROP TYPE IF EXISTS schema_direction_type CASCADE;
DROP TYPE IF EXISTS schema_payload_format CASCADE;
DROP TYPE IF EXISTS compatibility_level_type CASCADE;
DROP TYPE IF EXISTS compatibility_reason_severity CASCADE;
DROP TYPE IF EXISTS connection_validation_run_status CASCADE;
DROP TYPE IF EXISTS connection_validation_trigger_type CASCADE;
DROP TYPE IF EXISTS connection_validation_stage_type CASCADE;
DROP TYPE IF EXISTS connection_validation_stage_status CASCADE;
DROP TYPE IF EXISTS transform_output_format CASCADE;
DROP TYPE IF EXISTS transform_mapping_status CASCADE;
DROP TYPE IF EXISTS field_transform_type CASCADE;
DROP TYPE IF EXISTS confidence_level CASCADE;
DROP TYPE IF EXISTS issue_kind_type CASCADE;        -- removed with compatibility_issue
DROP TYPE IF EXISTS issue_severity_type CASCADE;    -- removed with compatibility_issue

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE enterprise_status AS ENUM ('ACTIVE', 'SUSPENDED', 'INACTIVE');
CREATE TYPE user_role AS ENUM ('ADMIN', 'PUBLISHER', 'VIEWER');
CREATE TYPE user_status AS ENUM ('ACTIVE', 'DISABLED');
CREATE TYPE api_protocol_type AS ENUM ('REST', 'SOAP', 'WEB', 'CLI', 'OTHER');
CREATE TYPE api_submission_status AS ENUM (
    'DRAFT', 'VALIDATING', 'REJECTED', 'PUBLISHED', 'WITHDRAWN'
);
CREATE TYPE api_version_status AS ENUM (
    'DRAFT', 'VALIDATING', 'REJECTED', 'PUBLISHED', 'ARCHIVED'
);
CREATE TYPE specification_type AS ENUM ('OPENAPI', 'SWAGGER', 'WSDL');
CREATE TYPE specification_source_type AS ENUM ('FILE_UPLOAD', 'URL_REFERENCE');
CREATE TYPE auth_method_type AS ENUM (
    'OAUTH2', 'API_KEY', 'BASIC', 'TOKEN', 'BEARER', 'MTLS', 'NONE', 'OTHER'
);
CREATE TYPE validation_overall_status AS ENUM ('PASSED', 'FAILED', 'PARTIAL', 'RUNNING');
CREATE TYPE validation_stage_type AS ENUM (
    'SPECIFICATION_VALIDATION',
    'DOMAIN_COMPLIANCE_VALIDATION',
    'SECURITY_VALIDATION'
);
CREATE TYPE validation_stage_status AS ENUM ('PASSED', 'FAILED', 'NOT_RUN');
CREATE TYPE version_event_type AS ENUM (
    'CREATED', 'UPDATED', 'SUBMITTED_FOR_VALIDATION',
    'VALIDATION_PASSED', 'VALIDATION_FAILED',
    'PUBLISHED', 'REJECTED', 'ARCHIVED', 'RESTORED_AS_DRAFT'
);
CREATE TYPE api_category_type AS ENUM ('TRANSFORMATION', 'VALIDATION', 'COMMUNICATION');
CREATE TYPE schema_direction_type AS ENUM ('INPUT', 'OUTPUT');
CREATE TYPE schema_payload_format AS ENUM ('JSON', 'XML');
-- API-to-API connection check (A.output → B.input); not field-level mapping
CREATE TYPE compatibility_level_type AS ENUM (
    'COMPATIBLE', 'INCOMPATIBLE', 'MISSING_INFORMATION'
);
CREATE TYPE compatibility_reason_severity AS ENUM (
    'INFO', 'WARNING', 'ERROR'
);
CREATE TYPE connection_validation_run_status AS ENUM (
    'RUNNING', 'PASSED', 'FAILED', 'CANCELLED', 'STALE'
);
CREATE TYPE connection_validation_trigger_type AS ENUM (
    'MANUAL', 'VERSION_CHANGED', 'MAPPING_UPDATED', 'RETRY'
);
CREATE TYPE connection_validation_stage_type AS ENUM (
    'ELIGIBILITY', 'FORMAT_CHECK', 'SCHEMA_CHECK', 'MAPPING_CHECK',
    'TARGET_VALIDATION', 'ACTIVATION_GATE'
);
CREATE TYPE connection_validation_stage_status AS ENUM (
    'RUNNING', 'PASSED', 'FAILED', 'NOT_RUN', 'MISSING_INFORMATION'
);

-- lifecycle of a mapping package (ER Layer E overview)
CREATE TYPE mapping_lifecycle_status AS ENUM (
    'DRAFT', 'ACTIVE', 'FAILED', 'DEPRECATED'
);
-- engine completeness (mapping_engine.SchemaMapping.status)
CREATE TYPE mapping_completeness AS ENUM (
    'FULL', 'PARTIAL', 'INCOMPATIBLE'
);
CREATE TYPE field_transform_type AS ENUM (
    'rename', 'cast', 'wrap_array', 'unwrap_array',
    'constant', 'drop', 'missing'
);
CREATE TYPE confidence_level AS ENUM ('high', 'medium', 'low');
CREATE TYPE transform_output_format AS ENUM ('JSON', 'XML');
CREATE TYPE transform_mapping_status AS ENUM ('full', 'partial', 'incompatible');

-- Document custom types for DBeaver Data Types / ER diagrams
COMMENT ON TYPE enterprise_status IS 'Custom DataType: enterprise lifecycle';
COMMENT ON TYPE user_role IS 'Custom DataType: app_user role';
COMMENT ON TYPE user_status IS 'Custom DataType: app_user account status';
COMMENT ON TYPE api_protocol_type IS 'Custom DataType: client protocol (REST/SOAP/WEB/CLI)';
COMMENT ON TYPE api_submission_status IS 'Custom DataType: API publication lifecycle';
COMMENT ON TYPE api_version_status IS 'Custom DataType: version lifecycle';
COMMENT ON TYPE specification_type IS 'Custom DataType: OpenAPI/Swagger/WSDL';
COMMENT ON TYPE specification_source_type IS 'Custom DataType: file upload vs URL';
COMMENT ON TYPE auth_method_type IS 'Custom DataType: normalized auth method';
COMMENT ON TYPE validation_overall_status IS 'Custom DataType: validation run overall status';
COMMENT ON TYPE validation_stage_type IS 'Custom DataType: publish validation stage';
COMMENT ON TYPE validation_stage_status IS 'Custom DataType: per-stage status';
COMMENT ON TYPE version_event_type IS 'Custom DataType: version timeline event';
COMMENT ON TYPE api_category_type IS 'Custom DataType from capstone: transformation/validation/communication';
COMMENT ON TYPE schema_direction_type IS 'Custom DataType from capstone schemas.direction';
COMMENT ON TYPE schema_payload_format IS 'Custom DataType from capstone schemas.format';
COMMENT ON TYPE compatibility_level_type IS 'API connection check: COMPATIBLE / INCOMPATIBLE / MISSING_INFORMATION';
COMMENT ON TYPE mapping_lifecycle_status IS 'Custom DataType: mapping package lifecycle';
COMMENT ON TYPE compatibility_reason_severity IS 'Custom DataType: severity of a structured connection-validation reason';
COMMENT ON TYPE connection_validation_run_status IS 'Custom DataType: overall state of an API-to-API connection validation run';
COMMENT ON TYPE connection_validation_trigger_type IS 'Custom DataType: event that initiated a connection validation run';
COMMENT ON TYPE connection_validation_stage_type IS 'Custom DataType: ordered connection validation pipeline stages';
COMMENT ON TYPE connection_validation_stage_status IS 'Custom DataType: per-stage connection validation state';
COMMENT ON TYPE mapping_completeness IS 'Custom DataType from mapping_engine.SchemaMapping.status';
COMMENT ON TYPE field_transform_type IS 'Custom DataType from mapping_engine FieldMapping.transform';
COMMENT ON TYPE confidence_level IS 'Custom DataType from mapping_engine FieldMapping.confidence';
COMMENT ON TYPE transform_output_format IS 'Custom DataType from capstone transform_runs.output_format';
COMMENT ON TYPE transform_mapping_status IS 'Custom DataType: transform mapping completeness';


-- LAYER A — Identity & Publishing
-- ============================================================

-- entity: enterprise (strong)
CREATE TABLE enterprise (
    enterprise_id          SERIAL PRIMARY KEY,
    name                   VARCHAR(255) NOT NULL,
    registration_number    VARCHAR(100),
    website_url            VARCHAR(1000),              -- Layer B catalogue
    status                 enterprise_status NOT NULL DEFAULT 'ACTIVE',
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_enterprise_registration UNIQUE (registration_number)
);

COMMENT ON TABLE enterprise IS 'ER Layer A/B: company identity; website_url from catalogue CSV';

-- entity: app_user (N:1 enterprise)
CREATE TABLE app_user (
    user_id                SERIAL PRIMARY KEY,
    enterprise_id          INT NOT NULL,
    name                   VARCHAR(255) NOT NULL,
    email                  VARCHAR(255) NOT NULL,
    password_hash          VARCHAR(255) NOT NULL,
    role                   user_role NOT NULL DEFAULT 'PUBLISHER',
    status                 user_status NOT NULL DEFAULT 'ACTIVE',
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_app_user_email UNIQUE (email),
    CONSTRAINT fk_app_user_enterprise
        FOREIGN KEY (enterprise_id) REFERENCES enterprise (enterprise_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE app_user IS 'ER Layer A: publisher/admin users belonging to an enterprise';

-- entity: api_submission (centre of ER — stable API identity)
CREATE TABLE api_submission (
    api_id                 SERIAL PRIMARY KEY,
    enterprise_id          INT NOT NULL,
    submitted_by           INT NOT NULL,
    catalogue_id           UUID,                       -- Layer B: CSV id
    api_name               VARCHAR(255) NOT NULL,
    category               api_category_type,          -- Layer B
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    status                 api_submission_status NOT NULL DEFAULT 'DRAFT',
    current_version_id     INT,                        -- FK added after api_version
    withdrawn_reason       TEXT,
    withdrawn_at           TIMESTAMP,
    withdrawn_by           INT,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_api_catalogue_id UNIQUE (catalogue_id),
    CONSTRAINT fk_api_enterprise
        FOREIGN KEY (enterprise_id) REFERENCES enterprise (enterprise_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_api_submitted_by
        FOREIGN KEY (submitted_by) REFERENCES app_user (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_api_withdrawn_by
        FOREIGN KEY (withdrawn_by) REFERENCES app_user (user_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE api_submission IS 'ER centre entity: stable API identity across versions';
COMMENT ON COLUMN api_submission.current_version_id IS 'Role FK: points to the single current api_version (1:0..1)';

-- entity: api_version (N:1 api_submission; self-FK previous_version)
CREATE TABLE api_version (
    version_id             SERIAL PRIMARY KEY,
    api_id                 INT NOT NULL,
    created_by             INT NOT NULL,
    version_number         VARCHAR(50) NOT NULL DEFAULT 'v1.0',
    change_note            TEXT,
    status                 api_version_status NOT NULL DEFAULT 'DRAFT',
    is_current             BOOLEAN NOT NULL DEFAULT FALSE,
    previous_version_id    INT,

    -- snapshot attributes (history-safe)
    api_name               VARCHAR(255) NOT NULL,
    endpoint_url           VARCHAR(1000) NOT NULL,
    protocol_type          api_protocol_type NOT NULL DEFAULT 'REST',
    category               api_category_type,
    capability_category    VARCHAR(100),               -- Layer C connection check
    description            TEXT,
    input_format           VARCHAR(100),               -- Layer C: target accepts this
    output_format          VARCHAR(100),               -- Layer C: source emits this

    -- Layer B catalogue multi-value attributes (display); connection check uses singular fields above
    input_formats          JSONB NOT NULL DEFAULT '[]'::jsonb,
    output_formats         JSONB NOT NULL DEFAULT '[]'::jsonb,
    business_rules         JSONB NOT NULL DEFAULT '[]'::jsonb,
    client_types           JSONB NOT NULL DEFAULT '[]'::jsonb,
    instructions           TEXT,
    documentation_url      VARCHAR(1000),
    network                VARCHAR(255),

    published_at           TIMESTAMP,
    archived_at            TIMESTAMP,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_api_version_number UNIQUE (api_id, version_number),
    CONSTRAINT uq_api_version_identity UNIQUE (api_id, version_id),
    CONSTRAINT fk_version_api
        FOREIGN KEY (api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_version_created_by
        FOREIGN KEY (created_by) REFERENCES app_user (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_version_previous
        FOREIGN KEY (previous_version_id) REFERENCES api_version (version_id)
        ON DELETE SET NULL,
    CONSTRAINT chk_version_not_self_previous
        CHECK (previous_version_id IS NULL OR previous_version_id <> version_id)
);

COMMENT ON TABLE api_version IS 'ER Layer A/B: immutable version snapshot + catalogue fields; history axis for frontend';
COMMENT ON COLUMN api_version.input_format IS 'Primary input format for connection check (API B.input)';
COMMENT ON COLUMN api_version.output_format IS 'Primary output format for connection check (API A.output)';
COMMENT ON COLUMN api_version.capability_category IS 'Capability label used in connection check';

-- deferred 1:0..1 current version pointer
ALTER TABLE api_submission
    ADD CONSTRAINT fk_api_current_version
        FOREIGN KEY (current_version_id) REFERENCES api_version (version_id)
        ON DELETE SET NULL;

-- cardinality: at most one current version per API
CREATE UNIQUE INDEX uq_api_one_current_version
    ON api_version (api_id)
    WHERE is_current = TRUE;

-- entity: api_version_event (weak / N:1 version)
CREATE TABLE api_version_event (
    event_id               SERIAL PRIMARY KEY,
    version_id             INT NOT NULL,
    api_id                 INT NOT NULL,
    actor_user_id          INT,
    event_type             version_event_type NOT NULL,
    from_status            api_version_status,
    to_status              api_version_status,
    message                TEXT,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_event_version
        FOREIGN KEY (version_id) REFERENCES api_version (version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_event_api
        FOREIGN KEY (api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_event_actor
        FOREIGN KEY (actor_user_id) REFERENCES app_user (user_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE api_version_event IS 'ER Layer A: timeline events for a version';

-- entity: api_specification (1:1 api_version)
CREATE TABLE api_specification (
    specification_id       SERIAL PRIMARY KEY,
    version_id             INT NOT NULL,
    spec_type              specification_type NOT NULL,
    source_type            specification_source_type NOT NULL,
    file_path              VARCHAR(1000),
    spec_url               VARCHAR(1000),
    raw_content            TEXT,
    checksum               VARCHAR(255),
    uploaded_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_spec_version UNIQUE (version_id),
    CONSTRAINT fk_spec_version
        FOREIGN KEY (version_id) REFERENCES api_version (version_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_spec_source
        CHECK (
            (source_type = 'FILE_UPLOAD' AND file_path IS NOT NULL)
            OR
            (source_type = 'URL_REFERENCE' AND spec_url IS NOT NULL)
        )
);

COMMENT ON TABLE api_specification IS 'ER Layer A: 1:1 OpenAPI/WSDL artifact per version';

-- ============================================================
-- LAYER B — auth_metadata (N:1 api, optional version)
-- ============================================================

CREATE TABLE auth_metadata (
    auth_id                SERIAL PRIMARY KEY,
    api_id                 INT NOT NULL,
    version_id             INT,
    auth_method            auth_method_type NOT NULL,
    auth_method_raw        VARCHAR(255),               -- CSV original label
    auth_description       TEXT,
    security_scheme_name   VARCHAR(255),
    is_complete            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_auth_api
        FOREIGN KEY (api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_auth_version
        FOREIGN KEY (version_id) REFERENCES api_version (version_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE auth_metadata IS 'ER Layer B: authentication metadata; raw label preserves catalogue text';

-- ============================================================
-- LAYER D — Publish Validation
-- ============================================================

CREATE TABLE validation_run (
    validation_run_id      SERIAL PRIMARY KEY,
    api_id                 INT NOT NULL,
    version_id             INT NOT NULL,
    overall_status         validation_overall_status NOT NULL DEFAULT 'RUNNING',
    started_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at           TIMESTAMP,

    CONSTRAINT fk_validation_api
        FOREIGN KEY (api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_validation_version
        FOREIGN KEY (version_id) REFERENCES api_version (version_id)
        ON DELETE CASCADE
);

CREATE TABLE validation_result (
    result_id              SERIAL PRIMARY KEY,
    validation_run_id      INT NOT NULL,
    stage                  validation_stage_type NOT NULL,
    status                 validation_stage_status NOT NULL DEFAULT 'NOT_RUN',
    message                TEXT,
    error_detail           TEXT,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_validation_stage UNIQUE (validation_run_id, stage),
    CONSTRAINT fk_result_validation_run
        FOREIGN KEY (validation_run_id) REFERENCES validation_run (validation_run_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE validation_run IS 'ER Layer D: one publish-validation execution per version';
COMMENT ON TABLE validation_result IS 'ER Layer D: weak entity — one row per stage within a run';

-- ============================================================
-- LAYER C — API Connection Compatibility (A.output → B.input)
-- Metadata basis: api_version.input_format / output_format / capability_category
-- api_schema / schema_field retained as optional payload store (not required to decide connectability)
-- ============================================================

-- entity: api_schema (N:1 api + N:1 version)  [optional payload store]
CREATE TABLE api_schema (
    schema_id              SERIAL PRIMARY KEY,
    api_id                 INT NOT NULL,
    version_id             INT NOT NULL,               -- ER: always bound to a version
    direction              schema_direction_type NOT NULL,
    format                 schema_payload_format NOT NULL,
    source_key             TEXT NOT NULL DEFAULT 'default',
    source_path            TEXT,
    source_method          TEXT,
    media_type             TEXT,
    status_code            TEXT,
    raw_schema             JSONB NOT NULL,
    normalized_schema      JSONB,
    schema_version         INT NOT NULL DEFAULT 1,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_api_schema_dir_ver_source
        UNIQUE (api_id, version_id, direction, schema_version, source_key),
    CONSTRAINT fk_api_schema_api
        FOREIGN KEY (api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_api_schema_version
        FOREIGN KEY (api_id, version_id) REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE api_schema IS 'ER Layer C (optional): INPUT/OUTPUT payload schema bound to api_version; not used for connection decision';

-- entity: schema_field (weak N:1 api_schema)  [optional field tree]
CREATE TABLE schema_field (
    field_id               SERIAL PRIMARY KEY,
    schema_id              INT NOT NULL,
    field_path             VARCHAR(512) NOT NULL,
    field_name             VARCHAR(255) NOT NULL,
    field_type             VARCHAR(100) NOT NULL,
    is_required            BOOLEAN NOT NULL DEFAULT FALSE,
    nesting_depth          INT NOT NULL DEFAULT 0,
    parent_path            VARCHAR(512),
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_schema_field_path UNIQUE (schema_id, field_path),
    CONSTRAINT fk_schema_field_schema
        FOREIGN KEY (schema_id) REFERENCES api_schema (schema_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE schema_field IS 'ER Layer C (optional): extracted field tree for display/mapping; not used for connection decision';

-- Stage 2 vocabulary: normalizes free-text api_version format arrays.
CREATE TABLE format_alias (
    alias_id               SERIAL PRIMARY KEY,
    raw_value              VARCHAR(100) NOT NULL,
    normalized_value       VARCHAR(100) NOT NULL,
    family                 VARCHAR(50) NOT NULL,
    is_terminal_output     BOOLEAN NOT NULL DEFAULT FALSE,
    notes                  TEXT,

    CONSTRAINT chk_format_alias_raw_not_blank CHECK (btrim(raw_value) <> ''),
    CONSTRAINT chk_format_alias_normalized CHECK (normalized_value ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT chk_format_alias_family CHECK (family ~ '^[A-Z][A-Z0-9_]*$')
);

CREATE UNIQUE INDEX uq_format_alias_raw_ci ON format_alias (lower(btrim(raw_value)));

COMMENT ON TABLE format_alias IS 'Stage 2 vocabulary for deterministic comparison of free-text input/output format values';
COMMENT ON COLUMN format_alias.is_terminal_output IS 'TRUE when the value is a terminal report/result that must not feed another API';

-- associative entity: compatibility_result — version-pair connection check
CREATE TABLE compatibility_result (
    result_id              SERIAL PRIMARY KEY,
    source_api_id          INT NOT NULL,
    target_api_id          INT NOT NULL,
    source_version_id      INT NOT NULL,
    target_version_id      INT NOT NULL,
    -- optional schema refs only (not required for connectability judgment)
    source_schema_id       INT,
    target_schema_id       INT,
    compatibility_level    compatibility_level_type NOT NULL,
    reason_code            VARCHAR(100) NOT NULL,
    reason                 TEXT NOT NULL,
    reason_details         JSONB,
    summary                JSONB,
    full_result            JSONB,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_compat_not_same_api CHECK (source_api_id <> target_api_id),
    CONSTRAINT chk_compat_reason_code CHECK (reason_code ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT uq_compat_version_pair UNIQUE (source_version_id, target_version_id),
    CONSTRAINT fk_compat_source_api
        FOREIGN KEY (source_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_compat_target_api
        FOREIGN KEY (target_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_compat_source_version
        FOREIGN KEY (source_api_id, source_version_id)
        REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_compat_target_version
        FOREIGN KEY (target_api_id, target_version_id)
        REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_compat_source_schema
        FOREIGN KEY (source_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_compat_target_schema
        FOREIGN KEY (target_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE compatibility_result IS 'ER Layer C: API A.output → B.input connection check; keyed by version pair; reason required';
COMMENT ON COLUMN compatibility_result.reason_code IS 'Stable machine-readable primary reason for the final decision';
COMMENT ON COLUMN compatibility_result.reason IS 'Human-readable explanation for UI (format / capability / missing metadata)';
COMMENT ON COLUMN compatibility_result.reason_details IS 'Structured values used to render and diagnose the primary reason';
COMMENT ON COLUMN compatibility_result.source_schema_id IS 'Optional; connection check does not depend on schema compare';
COMMENT ON COLUMN compatibility_result.target_schema_id IS 'Optional; connection check does not depend on schema compare';

-- Ordered structured diagnostics for all failed, skipped, or mapping-required checks.
CREATE TABLE compatibility_reason_item (
    reason_item_id         SERIAL PRIMARY KEY,
    result_id              INT NOT NULL,
    reason_code            VARCHAR(100) NOT NULL,
    stage                  VARCHAR(50) NOT NULL,
    severity               compatibility_reason_severity NOT NULL,
    source_path            VARCHAR(512),
    target_path            VARCHAR(512),
    message                TEXT NOT NULL,
    details                JSONB,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_reason_item_code CHECK (reason_code ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT chk_reason_item_stage CHECK (stage ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT fk_reason_item_result
        FOREIGN KEY (result_id) REFERENCES compatibility_result (result_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE compatibility_reason_item IS 'Structured, queryable diagnostics for a connection compatibility decision';

-- One auditable execution of the A.output -> B.input validation pipeline.
CREATE TABLE connection_validation_run (
    connection_validation_run_id SERIAL PRIMARY KEY,
    source_api_id          INT NOT NULL,
    target_api_id          INT NOT NULL,
    source_version_id      INT NOT NULL,
    target_version_id      INT NOT NULL,
    compatibility_result_id INT,
    status                 connection_validation_run_status NOT NULL DEFAULT 'RUNNING',
    trigger_type           connection_validation_trigger_type NOT NULL DEFAULT 'MANUAL',
    created_by             INT,
    started_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at           TIMESTAMP,

    CONSTRAINT chk_connection_run_not_same_api CHECK (source_api_id <> target_api_id),
    CONSTRAINT chk_connection_run_completion CHECK (
        (status = 'RUNNING' AND completed_at IS NULL)
        OR (status <> 'RUNNING' AND completed_at IS NOT NULL)
    ),
    CONSTRAINT fk_connection_run_source_api
        FOREIGN KEY (source_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_connection_run_target_api
        FOREIGN KEY (target_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_connection_run_source_version
        FOREIGN KEY (source_api_id, source_version_id)
        REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_connection_run_target_version
        FOREIGN KEY (target_api_id, target_version_id)
        REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_connection_run_result
        FOREIGN KEY (compatibility_result_id) REFERENCES compatibility_result (result_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_connection_run_created_by
        FOREIGN KEY (created_by) REFERENCES app_user (user_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE connection_validation_run IS 'Audit history for repeated A.output to B.input connection validation executions';
COMMENT ON COLUMN connection_validation_run.compatibility_result_id IS 'Optional final decision produced by this run';

CREATE TABLE connection_validation_stage_result (
    stage_result_id        SERIAL PRIMARY KEY,
    connection_validation_run_id INT NOT NULL,
    stage                  connection_validation_stage_type NOT NULL,
    status                 connection_validation_stage_status NOT NULL,
    message                TEXT,
    payload                JSONB,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_connection_run_stage UNIQUE (connection_validation_run_id, stage),
    CONSTRAINT fk_connection_stage_run
        FOREIGN KEY (connection_validation_run_id)
        REFERENCES connection_validation_run (connection_validation_run_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE connection_validation_stage_result IS 'Persisted outcome of each stage in a connection validation run, including NOT_RUN stages';

-- ============================================================
-- LAYER E — Schema Mapping & Transform
-- ============================================================

-- associative entity: schema_mapping (API-pair overview)
CREATE TABLE schema_mapping (
    mapping_id             SERIAL PRIMARY KEY,
    source_api_id          INT NOT NULL,
    target_api_id          INT NOT NULL,
    source_version_id      INT NOT NULL,
    target_version_id      INT NOT NULL,
    source_schema_id       INT,
    target_schema_id       INT,
    compatibility_result_id INT,                       -- optional weak link from connection check → map
    source_schema_format   schema_payload_format NOT NULL,
    target_schema_format   schema_payload_format NOT NULL,
    overview_note          TEXT,                       -- human summary only (NOT field rules)
    lifecycle_status       mapping_lifecycle_status NOT NULL DEFAULT 'DRAFT',
    completeness           mapping_completeness NOT NULL DEFAULT 'PARTIAL',
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_schema_mapping_not_same_api CHECK (source_api_id <> target_api_id),
    CONSTRAINT uq_schema_mapping_schema_pair
        UNIQUE (source_schema_id, target_schema_id),
    CONSTRAINT fk_sm_source_api
        FOREIGN KEY (source_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_target_api
        FOREIGN KEY (target_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_source_version
        FOREIGN KEY (source_api_id, source_version_id)
        REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_target_version
        FOREIGN KEY (target_api_id, target_version_id)
        REFERENCES api_version (api_id, version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_source_schema
        FOREIGN KEY (source_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_sm_target_schema
        FOREIGN KEY (target_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_sm_compat_result
        FOREIGN KEY (compatibility_result_id) REFERENCES compatibility_result (result_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE schema_mapping IS 'ER Layer E: API-pair mapping overview; optional weak FK to connection check; field rules in mapping_rule';
COMMENT ON COLUMN schema_mapping.compatibility_result_id IS 'Optional; Layer E does not require Layer C field compare';

-- Enforce the directional schema contract that cannot be expressed by simple FKs.
CREATE FUNCTION enforce_connection_schema_roles()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.source_schema_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM api_schema s
        WHERE s.schema_id = NEW.source_schema_id
          AND s.api_id = NEW.source_api_id
          AND s.version_id = NEW.source_version_id
          AND s.direction = 'OUTPUT'
    ) THEN
        RAISE EXCEPTION 'source_schema_id % must be an OUTPUT schema owned by source API/version',
            NEW.source_schema_id
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.target_schema_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM api_schema s
        WHERE s.schema_id = NEW.target_schema_id
          AND s.api_id = NEW.target_api_id
          AND s.version_id = NEW.target_version_id
          AND s.direction = 'INPUT'
    ) THEN
        RAISE EXCEPTION 'target_schema_id % must be an INPUT schema owned by target API/version',
            NEW.target_schema_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_compatibility_schema_roles
    BEFORE INSERT OR UPDATE OF source_api_id, target_api_id,
        source_version_id, target_version_id, source_schema_id, target_schema_id
    ON compatibility_result
    FOR EACH ROW EXECUTE FUNCTION enforce_connection_schema_roles();

CREATE TRIGGER trg_mapping_schema_roles
    BEFORE INSERT OR UPDATE OF source_api_id, target_api_id,
        source_version_id, target_version_id, source_schema_id, target_schema_id
    ON schema_mapping
    FOR EACH ROW EXECUTE FUNCTION enforce_connection_schema_roles();

COMMENT ON FUNCTION enforce_connection_schema_roles() IS 'Ensures connection source schemas are OUTPUT and target schemas are INPUT for the selected API versions';

-- weak entity: mapping_rule (N:1 schema_mapping)  [was: mapping_rules]
-- Normalized: API/version identity comes from parent schema_mapping (no duplicate FKs)
CREATE TABLE mapping_rule (
    rule_id                SERIAL PRIMARY KEY,
    schema_mapping_id      INT NOT NULL,
    source_field           VARCHAR(512) NOT NULL,
    target_field           VARCHAR(512) NOT NULL,
    transform_type         field_transform_type NOT NULL DEFAULT 'rename',
    source_type            VARCHAR(50),
    target_type            VARCHAR(50),
    confidence             confidence_level NOT NULL DEFAULT 'high',
    note                   TEXT,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_mapping_rule_fields
        UNIQUE (schema_mapping_id, source_field, target_field),
    CONSTRAINT fk_rule_schema_mapping
        FOREIGN KEY (schema_mapping_id) REFERENCES schema_mapping (mapping_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE mapping_rule IS 'ER Layer E: field-level rules; depends on schema_mapping (weak entity)';

-- entity: transform_run (execution log; links mapping + schemas)
CREATE TABLE transform_run (
    transform_run_id       SERIAL PRIMARY KEY,
    schema_mapping_id      INT,
    source_api_id          INT,
    target_api_id          INT,
    source_schema_id       INT,
    target_schema_id       INT,
    source_version_id      INT,
    target_version_id      INT,
    input_data             JSONB NOT NULL,
    output_data            JSONB,
    output_text            TEXT,
    output_format          transform_output_format NOT NULL,
    mapping_status         transform_mapping_status,
    warnings               JSONB NOT NULL DEFAULT '[]'::jsonb,
    success                BOOLEAN NOT NULL DEFAULT TRUE,
    error_message          TEXT,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tr_schema_mapping
        FOREIGN KEY (schema_mapping_id) REFERENCES schema_mapping (mapping_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_tr_source_api
        FOREIGN KEY (source_api_id) REFERENCES api_submission (api_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_tr_target_api
        FOREIGN KEY (target_api_id) REFERENCES api_submission (api_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_tr_source_schema
        FOREIGN KEY (source_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_tr_target_schema
        FOREIGN KEY (target_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_tr_source_version
        FOREIGN KEY (source_version_id) REFERENCES api_version (version_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_tr_target_version
        FOREIGN KEY (target_version_id) REFERENCES api_version (version_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE transform_run IS 'ER Layer E: transform execution log; optional FK to schema_mapping';

-- ============================================================
-- INDEXES (all FK columns + common filters)
-- ============================================================

CREATE INDEX idx_app_user_enterprise ON app_user (enterprise_id);

CREATE INDEX idx_api_enterprise ON api_submission (enterprise_id);
CREATE INDEX idx_api_submitted_by ON api_submission (submitted_by);
CREATE INDEX idx_api_status ON api_submission (status);
CREATE INDEX idx_api_category ON api_submission (category);

CREATE INDEX idx_version_api ON api_version (api_id);
CREATE INDEX idx_version_status ON api_version (status);
CREATE INDEX idx_version_created_at ON api_version (api_id, created_at DESC);
CREATE INDEX idx_version_previous ON api_version (previous_version_id);

CREATE INDEX idx_event_api ON api_version_event (api_id, created_at DESC);
CREATE INDEX idx_event_version ON api_version_event (version_id, created_at DESC);

CREATE INDEX idx_auth_api ON auth_metadata (api_id);
CREATE INDEX idx_auth_version ON auth_metadata (version_id);

CREATE INDEX idx_validation_api ON validation_run (api_id);
CREATE INDEX idx_validation_version ON validation_run (version_id);
CREATE INDEX idx_validation_result_run ON validation_result (validation_run_id);

CREATE INDEX idx_api_schema_api ON api_schema (api_id);
CREATE INDEX idx_api_schema_version ON api_schema (version_id);
CREATE INDEX idx_schema_field_schema ON schema_field (schema_id);
CREATE INDEX idx_schema_field_path ON schema_field (field_path);

CREATE INDEX idx_format_alias_normalized ON format_alias (normalized_value);
CREATE INDEX idx_format_alias_family ON format_alias (family);

CREATE INDEX idx_compat_source_api ON compatibility_result (source_api_id);
CREATE INDEX idx_compat_target_api ON compatibility_result (target_api_id);
CREATE INDEX idx_compat_source_version ON compatibility_result (source_version_id);
CREATE INDEX idx_compat_target_version ON compatibility_result (target_version_id);
CREATE INDEX idx_compat_reason_code ON compatibility_result (reason_code);
CREATE INDEX idx_compat_reason_item_result ON compatibility_reason_item (result_id);
CREATE INDEX idx_compat_reason_item_code ON compatibility_reason_item (reason_code);

CREATE INDEX idx_connection_run_pair
    ON connection_validation_run (source_version_id, target_version_id, started_at DESC);
CREATE INDEX idx_connection_run_status ON connection_validation_run (status);
CREATE INDEX idx_connection_run_result ON connection_validation_run (compatibility_result_id);
CREATE INDEX idx_connection_stage_run ON connection_validation_stage_result (connection_validation_run_id);

CREATE INDEX idx_sm_source_api ON schema_mapping (source_api_id);
CREATE INDEX idx_sm_target_api ON schema_mapping (target_api_id);
CREATE INDEX idx_sm_compat ON schema_mapping (compatibility_result_id);
CREATE INDEX idx_mapping_rule_parent ON mapping_rule (schema_mapping_id);

CREATE INDEX idx_tr_mapping ON transform_run (schema_mapping_id);
CREATE INDEX idx_tr_source_api ON transform_run (source_api_id);
CREATE INDEX idx_tr_target_api ON transform_run (target_api_id);
CREATE INDEX idx_tr_created ON transform_run (created_at DESC);

-- ============================================================
-- SAMPLE DATA (matches ER relationships)
-- ============================================================

INSERT INTO format_alias (raw_value, normalized_value, family, is_terminal_output, notes) VALUES
    ('JSON', 'JSON', 'JSON', FALSE, 'Canonical JSON payload'),
    ('JSON payload', 'JSON', 'JSON', FALSE, 'Catalogue alias'),
    ('XML', 'XML', 'XML', FALSE, 'Canonical XML payload'),
    ('UBL', 'UBL', 'UBL', FALSE, 'Generic UBL document'),
    ('UBL XML', 'UBL_XML', 'UBL', FALSE, 'UBL serialized as XML'),
    ('UBL XML format', 'UBL_XML', 'UBL', FALSE, 'Catalogue alias'),
    ('PDF', 'PDF', 'DOCUMENT', TRUE, 'Human-readable terminal document'),
    ('Validation Report', 'VALIDATION_REPORT', 'REPORT', TRUE, 'Terminal validation output');

INSERT INTO enterprise (name, registration_number, website_url, status) VALUES
    ('Demo Supply Chain Enterprise', 'ENT-0001', 'https://example.com', 'ACTIVE'),
    ('ESS', 'ENT-ESS', 'https://www.ebsoftwareservices.com.au', 'ACTIVE'),
    ('OZEDI Holdings Pty Ltd', 'ENT-OZEDI', 'https://www.ozedi.com.au', 'ACTIVE');

INSERT INTO app_user (enterprise_id, name, email, password_hash, role, status)
VALUES (
    1,
    'Demo Publisher',
    'publisher@example.com',
    'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f',
    'PUBLISHER',
    'ACTIVE'
);

-- API #1 history demo
INSERT INTO api_submission (enterprise_id, submitted_by, api_name, category, is_active, status)
VALUES (1, 1, 'Invoice Validation API', 'VALIDATION', TRUE, 'PUBLISHED');

INSERT INTO api_version (
    api_id, created_by, version_number, change_note, status, is_current, previous_version_id,
    api_name, endpoint_url, protocol_type, category, capability_category, description,
    input_format, output_format, input_formats, output_formats, client_types,
    published_at, archived_at, created_at
) VALUES
(1, 1, 'v1.0', 'Initial API submission.', 'ARCHIVED', FALSE, NULL,
 'Invoice Validation API', 'https://api.example.com/invoices/validate', 'REST', 'VALIDATION',
 'invoice validation', 'Validates e-invoice data.', 'JSON', 'JSON',
 '["JSON"]'::jsonb, '["JSON"]'::jsonb, '["REST"]'::jsonb,
 TIMESTAMP '2026-01-10 10:00:00', TIMESTAMP '2026-03-01 09:00:00', TIMESTAMP '2026-01-10 09:30:00'),
(1, 1, 'v1.1', 'Added tax rule pack support.', 'ARCHIVED', FALSE, 1,
 'Invoice Validation API', 'https://api.example.com/v1.1/invoices/validate', 'REST', 'VALIDATION',
 'invoice validation', 'Adds tax rule packs.', 'JSON', 'JSON',
 '["JSON"]'::jsonb, '["JSON"]'::jsonb, '["REST"]'::jsonb,
 TIMESTAMP '2026-03-01 09:00:00', TIMESTAMP '2026-06-15 11:00:00', TIMESTAMP '2026-02-28 16:00:00'),
(1, 1, 'v2.0', 'Breaking: new response envelope.', 'PUBLISHED', TRUE, 2,
 'Invoice Validation API', 'https://api.example.com/v2/invoices/validate', 'REST', 'VALIDATION',
 'invoice validation', 'v2 envelope + OAuth scopes.', 'JSON', 'JSON',
 '["JSON"]'::jsonb, '["JSON"]'::jsonb, '["REST"]'::jsonb,
 TIMESTAMP '2026-06-15 11:00:00', NULL, TIMESTAMP '2026-06-14 14:20:00');

UPDATE api_submission SET current_version_id = 3 WHERE api_id = 1;

INSERT INTO api_specification (version_id, spec_type, source_type, spec_url, checksum) VALUES
(1, 'OPENAPI', 'URL_REFERENCE', 'https://api.example.com/openapi-v1.json', 'checksum-v1'),
(2, 'OPENAPI', 'URL_REFERENCE', 'https://api.example.com/openapi-v1.1.json', 'checksum-v1.1'),
(3, 'OPENAPI', 'URL_REFERENCE', 'https://api.example.com/openapi-v2.json', 'checksum-v2');

INSERT INTO auth_metadata (api_id, version_id, auth_method, auth_method_raw, auth_description, security_scheme_name, is_complete)
VALUES (1, 3, 'OAUTH2', 'OAuth2', 'OAuth 2.0 bearer token required.', 'BearerAuth', TRUE);

INSERT INTO validation_run (api_id, version_id, overall_status, completed_at)
VALUES (1, 3, 'PASSED', CURRENT_TIMESTAMP);

INSERT INTO validation_result (validation_run_id, stage, status, message) VALUES
(1, 'SPECIFICATION_VALIDATION', 'PASSED', 'OpenAPI specification is valid.'),
(1, 'DOMAIN_COMPLIANCE_VALIDATION', 'PASSED', 'Domain rules satisfied.'),
(1, 'SECURITY_VALIDATION', 'PASSED', 'Auth metadata complete.');

INSERT INTO api_version_event (version_id, api_id, actor_user_id, event_type, from_status, to_status, message, created_at) VALUES
(1, 1, 1, 'CREATED', NULL, 'DRAFT', 'Created v1.0', TIMESTAMP '2026-01-10 09:30:00'),
(1, 1, 1, 'PUBLISHED', 'DRAFT', 'PUBLISHED', 'Published v1.0', TIMESTAMP '2026-01-10 10:00:00'),
(1, 1, 1, 'ARCHIVED', 'PUBLISHED', 'ARCHIVED', 'Superseded by v1.1', TIMESTAMP '2026-03-01 09:00:00'),
(2, 1, 1, 'CREATED', NULL, 'DRAFT', 'Created v1.1', TIMESTAMP '2026-02-28 16:00:00'),
(2, 1, 1, 'PUBLISHED', 'DRAFT', 'PUBLISHED', 'Published v1.1', TIMESTAMP '2026-03-01 09:00:00'),
(2, 1, 1, 'ARCHIVED', 'PUBLISHED', 'ARCHIVED', 'Superseded by v2.0', TIMESTAMP '2026-06-15 11:00:00'),
(3, 1, 1, 'CREATED', NULL, 'DRAFT', 'Created v2.0', TIMESTAMP '2026-06-14 14:20:00'),
(3, 1, 1, 'PUBLISHED', 'DRAFT', 'PUBLISHED', 'Published v2.0 as current', TIMESTAMP '2026-06-15 11:00:00');

-- API #2 ESSAnalyse (catalogue)
INSERT INTO api_submission (enterprise_id, submitted_by, catalogue_id, api_name, category, is_active, status)
VALUES (2, 1, '2f060e74-cbf5-42d3-8e06-fb90a5751554', 'ESSAnalyse', 'VALIDATION', TRUE, 'PUBLISHED');

INSERT INTO api_version (
    api_id, created_by, version_number, change_note, status, is_current,
    api_name, endpoint_url, protocol_type, category, capability_category, description,
    input_format, output_format, input_formats, output_formats, business_rules, client_types,
    instructions, published_at, created_at
) VALUES (
    2, 1, 'v1.0', 'Imported from API catalogue.', 'PUBLISHED', TRUE,
    'ESSAnalyse',
    'https://edi-services.ebxcloud.com/ess-schematron/v1/api/validate',
    'REST', 'VALIDATION', 'validation',
    'Analyse invoice data against CII / Schematron rules.',
    'UBL XML format', 'Validation Report',
    '["UBL XML format"]'::jsonb, '["Validation Report"]'::jsonb,
    '["AUNZ_PEPPOL_1_0_10","AUNZ_UBL_1_0_10"]'::jsonb, '["REST"]'::jsonb,
    'Within the ESS UI, Products-> APIs-> ESS Analyse (Demo)',
    TIMESTAMP '2025-12-22 14:53:34', TIMESTAMP '2025-12-22 14:53:34'
);

UPDATE api_submission SET current_version_id = 4 WHERE api_id = 2;

INSERT INTO auth_metadata (api_id, version_id, auth_method, auth_method_raw, auth_description, is_complete)
VALUES (2, 4, 'OAUTH2', 'OAuth2', 'Catalogue authentication method.', TRUE);

-- API #3 OZEDI Document Send
INSERT INTO api_submission (enterprise_id, submitted_by, catalogue_id, api_name, category, is_active, status)
VALUES (3, 1, '48ee0730-f005-4df1-8fb6-fc759c6ba47f', 'OZEDI Document Send API', 'COMMUNICATION', TRUE, 'PUBLISHED');

INSERT INTO api_version (
    api_id, created_by, version_number, change_note, status, is_current,
    api_name, endpoint_url, protocol_type, category, capability_category, description,
    input_format, output_format, input_formats, output_formats, client_types,
    instructions, documentation_url, network, published_at, created_at
) VALUES (
    3, 1, 'v1.0', 'Imported from API catalogue.', 'PUBLISHED', TRUE,
    'OZEDI Document Send API',
    'https://api-ebusiness.ozedi.com.au/v2/snd/message/send/{client}',
    'REST', 'COMMUNICATION', 'communication',
    'Send UBL documents via PEPPOL network.',
    'UBL', 'Status Codes',
    '["UBL","XML"]'::jsonb, '["Status Codes"]'::jsonb, '["REST"]'::jsonb,
    'Requires valid JWT token, client ID, and upload token.',
    'https://www.ozedi.com.au', 'AU PEPPOL',
    TIMESTAMP '2025-12-22 14:53:34', TIMESTAMP '2025-12-22 14:53:34'
);

UPDATE api_submission SET current_version_id = 5 WHERE api_id = 3;

INSERT INTO auth_metadata (api_id, version_id, auth_method, auth_method_raw, auth_description, is_complete)
VALUES (3, 5, 'TOKEN', 'Token', 'JWT token authentication.', TRUE);

-- Layer C: optional payload store (not used for connection decision)
INSERT INTO api_schema (
    api_id, version_id, direction, format, source_key, source_path, source_method,
    media_type, status_code, raw_schema, normalized_schema, schema_version
) VALUES
(1, 3, 'OUTPUT', 'JSON',
 'sample:output:invoice-json', 'Invoice', NULL, 'application/json', '200',
 '{"type":"object","properties":{"ID":{"type":"string"},"IssueDate":{"type":"string"},"PayableAmount":{"type":"number"}}}'::jsonb,
 '{"fields":[{"path":"Invoice/ID","type":"string","required":true},{"path":"Invoice/IssueDate","type":"date","required":true},{"path":"Invoice/PayableAmount","type":"number","required":true}]}'::jsonb,
 1),
(2, 4, 'INPUT', 'XML',
 'sample:input:ozedi-invoice', 'Invoice', NULL, 'XML', NULL,
 '{"root":"Invoice","fields":["ID","IssueDate","PayableAmount"]}'::jsonb,
 '{"fields":[{"path":"Invoice/ID","type":"string","required":true},{"path":"Invoice/IssueDate","type":"date","required":true},{"path":"Invoice/PayableAmount","type":"number","required":true}]}'::jsonb,
 1),
(3, 5, 'INPUT', 'XML',
 'sample:input:peppol-invoice', 'Invoice', NULL, 'XML', NULL,
 '{"root":"Invoice","fields":["ID","IssueDate"]}'::jsonb,
 '{"fields":[{"path":"Invoice/ID","type":"string","required":true},{"path":"Invoice/IssueDate","type":"date","required":true}]}'::jsonb,
 1);

INSERT INTO schema_field (schema_id, field_path, field_name, field_type, is_required, nesting_depth, parent_path) VALUES
(1, 'Invoice/ID', 'ID', 'string', TRUE, 1, 'Invoice'),
(1, 'Invoice/IssueDate', 'IssueDate', 'date', TRUE, 1, 'Invoice'),
(1, 'Invoice/PayableAmount', 'PayableAmount', 'number', TRUE, 1, 'Invoice'),
(2, 'Invoice/ID', 'ID', 'string', TRUE, 1, 'Invoice'),
(2, 'Invoice/IssueDate', 'IssueDate', 'date', TRUE, 1, 'Invoice'),
(2, 'Invoice/PayableAmount', 'PayableAmount', 'number', TRUE, 1, 'Invoice'),
(3, 'Invoice/ID', 'ID', 'string', TRUE, 1, 'Invoice'),
(3, 'Invoice/IssueDate', 'IssueDate', 'date', TRUE, 1, 'Invoice');

-- Layer C: API-to-API connection check (A.output → B.input) — version pair + reason
-- ESSAnalyse output "Validation Report" cannot feed OZEDI input "UBL"
INSERT INTO compatibility_result (
    source_api_id, target_api_id, source_version_id, target_version_id,
    source_schema_id, target_schema_id,
    compatibility_level, reason_code, reason, reason_details, summary, full_result
) VALUES (
    2, 3, 4, 5,
    NULL, NULL,
    'INCOMPATIBLE',
    'FORMAT_TERMINAL_OUTPUT',
    'Source output format (Validation Report) does not match target input format (UBL).',
    '{"source_output":"VALIDATION_REPORT","target_input":"UBL"}'::jsonb,
    '{"format_check":"fail","capability_check":"skipped"}'::jsonb,
    '{"source_output":"Validation Report","target_input":"UBL","source_capability":"validation","target_capability":"communication"}'::jsonb
);

INSERT INTO compatibility_reason_item (
    result_id, reason_code, stage, severity, message, details
) VALUES (
    1, 'FORMAT_TERMINAL_OUTPUT', 'FORMAT_CHECK', 'ERROR',
    'Validation Report is a terminal output and cannot be used as a downstream API payload.',
    '{"source_output":"VALIDATION_REPORT","target_input":"UBL"}'::jsonb
);

INSERT INTO connection_validation_run (
    source_api_id, target_api_id, source_version_id, target_version_id,
    compatibility_result_id, status, trigger_type, created_by, completed_at
) VALUES (
    2, 3, 4, 5, 1, 'FAILED', 'MANUAL', 1, CURRENT_TIMESTAMP
);

INSERT INTO connection_validation_stage_result (
    connection_validation_run_id, stage, status, message, payload
) VALUES
    (1, 'ELIGIBILITY', 'PASSED', 'Both API versions are published and direction is OUTPUT to INPUT.', NULL),
    (1, 'FORMAT_CHECK', 'FAILED', 'Source output is terminal and cannot be forwarded.',
     '{"reason_code":"FORMAT_TERMINAL_OUTPUT"}'::jsonb),
    (1, 'SCHEMA_CHECK', 'NOT_RUN', 'Skipped because the format gate failed.', NULL),
    (1, 'MAPPING_CHECK', 'NOT_RUN', 'Skipped because the format gate failed.', NULL),
    (1, 'TARGET_VALIDATION', 'NOT_RUN', 'Skipped because the format gate failed.', NULL),
    (1, 'ACTIVATION_GATE', 'FAILED', 'Connection cannot be activated.', NULL);

-- Layer E: mapping package independent of connection check (weak coupling: no required FK)
INSERT INTO schema_mapping (
    source_api_id, target_api_id, source_version_id, target_version_id,
    source_schema_id, target_schema_id, compatibility_result_id,
    source_schema_format, target_schema_format,
    overview_note, lifecycle_status, completeness
) VALUES (
    1, 2, 3, 4, 1, 2, NULL, 'JSON', 'XML',
    'Map the JSON invoice output to the UBL XML validation input.',
    'ACTIVE', 'FULL'
);

INSERT INTO mapping_rule (
    schema_mapping_id, source_field, target_field, transform_type,
    source_type, target_type, confidence, note
) VALUES
(1, 'Invoice/ID', 'Invoice/ID', 'rename', 'string', 'string', 'high', 'Direct match'),
(1, 'Invoice/IssueDate', 'Invoice/IssueDate', 'rename', 'date', 'date', 'high', 'Direct match'),
(1, 'Invoice/PayableAmount', 'Invoice/PayableAmount', 'rename', 'number', 'number', 'high', 'Direct match');

INSERT INTO transform_run (
    schema_mapping_id, source_api_id, target_api_id,
    source_schema_id, target_schema_id, source_version_id, target_version_id,
    input_data, output_data, output_format, mapping_status, warnings, success
) VALUES (
    1, 1, 2, 1, 2, 3, 4,
    '{"Invoice":{"ID":"INV-1","IssueDate":"2026-07-01","PayableAmount":120.5}}'::jsonb,
    '{"Invoice":{"ID":"INV-1","IssueDate":"2026-07-01","PayableAmount":120.5}}'::jsonb,
    'XML', 'full', '[]'::jsonb, TRUE
);

-- ============================================================
-- ER-aligned verification queries
-- ============================================================

-- A: current catalogue view
SELECT s.api_id, s.catalogue_id, s.api_name, s.category,
       v.version_number, v.endpoint_url, v.input_formats, v.network, e.name AS company
FROM api_submission s
JOIN api_version v ON s.current_version_id = v.version_id
JOIN enterprise e ON s.enterprise_id = e.enterprise_id
WHERE s.status = 'PUBLISHED'
ORDER BY s.api_name;

-- A: version history chain
SELECT version_id, version_number, status, is_current, previous_version_id, created_at
FROM api_version
WHERE api_id = 1
ORDER BY created_at;

-- C: API-to-API connection check (version pair + reason)
SELECT cr.result_id, cr.compatibility_level, cr.reason_code, cr.reason,
       sv.api_name AS source_api, sv.output_format AS source_output,
       tv.api_name AS target_api, tv.input_format AS target_input
FROM compatibility_result cr
JOIN api_version sv ON sv.version_id = cr.source_version_id
JOIN api_version tv ON tv.version_id = cr.target_version_id
WHERE cr.source_api_id = 2 AND cr.target_api_id = 3;

-- C: latest connection-validation run with all persisted stages
SELECT cvr.connection_validation_run_id, cvr.status AS run_status,
       cvsr.stage, cvsr.status AS stage_status, cvsr.message
FROM connection_validation_run cvr
JOIN connection_validation_stage_result cvsr
    ON cvsr.connection_validation_run_id = cvr.connection_validation_run_id
WHERE cvr.source_version_id = 4 AND cvr.target_version_id = 5
ORDER BY cvr.started_at DESC, cvsr.stage;

-- E: mapping package with field rules (normalized join; independent of Layer C)
SELECT sm.mapping_id, sm.completeness, sm.lifecycle_status, sm.compatibility_result_id,
       mr.source_field, mr.target_field, mr.transform_type, mr.confidence
FROM schema_mapping sm
JOIN mapping_rule mr ON mr.schema_mapping_id = sm.mapping_id
WHERE sm.source_api_id = 1 AND sm.target_api_id = 2;

-- Optional weak link: connection check ↔ mapping ↔ transform
SELECT cr.compatibility_level, cr.reason, sm.mapping_id, sm.completeness,
       tr.transform_run_id, tr.success, tr.mapping_status
FROM compatibility_result cr
LEFT JOIN schema_mapping sm
    ON sm.source_api_id = cr.source_api_id AND sm.target_api_id = cr.target_api_id
LEFT JOIN transform_run tr ON tr.schema_mapping_id = sm.mapping_id
WHERE cr.result_id = 1;
