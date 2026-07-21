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
--   C Compatibility Engine  : api_schema, schema_field,
--                             compatibility_result, compatibility_issue
--   D Publish Validation    : validation_run, validation_result
--   E Mapping & Transform   : schema_mapping, mapping_rule, transform_run
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
DROP TABLE IF EXISTS transform_run CASCADE;
DROP TABLE IF EXISTS mapping_rule CASCADE;
DROP TABLE IF EXISTS compatibility_issue CASCADE;
DROP TABLE IF EXISTS compatibility_result CASCADE;
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
DROP TYPE IF EXISTS transform_output_format CASCADE;
DROP TYPE IF EXISTS transform_mapping_status CASCADE;
DROP TYPE IF EXISTS field_transform_type CASCADE;
DROP TYPE IF EXISTS confidence_level CASCADE;
DROP TYPE IF EXISTS issue_kind_type CASCADE;
DROP TYPE IF EXISTS issue_severity_type CASCADE;

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
CREATE TYPE compatibility_level_type AS ENUM (
    'DIRECTLY_COMPATIBLE', 'COMPATIBLE_WITH_MAPPING', 'INCOMPATIBLE'
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

-- From capstone compatibility_engine.py (kind / severity on issues)
CREATE TYPE issue_kind_type AS ENUM ('blocking', 'mapping', 'info');
CREATE TYPE issue_severity_type AS ENUM ('error', 'warning', 'information');

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
COMMENT ON TYPE compatibility_level_type IS 'Custom DataType from capstone compatibility_level';
COMMENT ON TYPE mapping_lifecycle_status IS 'Custom DataType: mapping package lifecycle';
COMMENT ON TYPE mapping_completeness IS 'Custom DataType from mapping_engine.SchemaMapping.status';
COMMENT ON TYPE field_transform_type IS 'Custom DataType from mapping_engine FieldMapping.transform';
COMMENT ON TYPE confidence_level IS 'Custom DataType from mapping_engine FieldMapping.confidence';
COMMENT ON TYPE transform_output_format IS 'Custom DataType from capstone transform_runs.output_format';
COMMENT ON TYPE transform_mapping_status IS 'Custom DataType: transform mapping completeness';
COMMENT ON TYPE issue_kind_type IS 'Custom DataType from compatibility_engine issue kind';
COMMENT ON TYPE issue_severity_type IS 'Custom DataType from compatibility_engine issue severity';


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
    capability_category    VARCHAR(100),
    description            TEXT,
    input_format           VARCHAR(100),
    output_format          VARCHAR(100),

    -- Layer B catalogue multi-value attributes
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
-- LAYER C — Compatibility Engine
-- ============================================================

-- entity: api_schema (N:1 api + N:1 version)  [was: schemas]
CREATE TABLE api_schema (
    schema_id              SERIAL PRIMARY KEY,
    api_id                 INT NOT NULL,
    version_id             INT NOT NULL,               -- ER: always bound to a version
    direction              schema_direction_type NOT NULL,
    format                 schema_payload_format NOT NULL,
    raw_schema             JSONB NOT NULL,
    normalized_schema      JSONB,
    schema_version         INT NOT NULL DEFAULT 1,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_api_schema_dir_ver
        UNIQUE (api_id, version_id, direction, schema_version),
    CONSTRAINT fk_api_schema_api
        FOREIGN KEY (api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_api_schema_version
        FOREIGN KEY (version_id) REFERENCES api_version (version_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE api_schema IS 'ER Layer C: INPUT/OUTPUT payload schema bound to api_version';

-- entity: schema_field (weak N:1 api_schema)  [was: schema_fields]
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

COMMENT ON TABLE schema_field IS 'ER Layer C: extracted field tree for compare/matrix';

-- associative entity: compatibility_result  [was: compatibility_results]
CREATE TABLE compatibility_result (
    result_id              SERIAL PRIMARY KEY,
    source_api_id          INT NOT NULL,
    target_api_id          INT NOT NULL,
    source_schema_id       INT,
    target_schema_id       INT,
    source_version_id      INT,
    target_version_id      INT,
    compatibility_level    compatibility_level_type NOT NULL,
    summary                JSONB,
    full_result            JSONB,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_compat_not_same_api CHECK (source_api_id <> target_api_id),
    CONSTRAINT uq_compat_schema_pair UNIQUE (source_schema_id, target_schema_id),
    CONSTRAINT fk_compat_source_api
        FOREIGN KEY (source_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_compat_target_api
        FOREIGN KEY (target_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_compat_source_schema
        FOREIGN KEY (source_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_compat_target_schema
        FOREIGN KEY (target_schema_id) REFERENCES api_schema (schema_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_compat_source_version
        FOREIGN KEY (source_version_id) REFERENCES api_version (version_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_compat_target_version
        FOREIGN KEY (target_version_id) REFERENCES api_version (version_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE compatibility_result IS 'ER Layer C: associative entity source API/schema <-> target API/schema';

-- weak entity: compatibility_issue
CREATE TABLE compatibility_issue (
    issue_id               SERIAL PRIMARY KEY,
    result_id              INT NOT NULL,
    code                   VARCHAR(100) NOT NULL,
    kind                   issue_kind_type NOT NULL,
    severity               issue_severity_type NOT NULL,
    source_path            VARCHAR(512),
    target_path            VARCHAR(512),
    message                TEXT NOT NULL,
    suggestion             TEXT,

    CONSTRAINT fk_issue_result
        FOREIGN KEY (result_id) REFERENCES compatibility_result (result_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE compatibility_issue IS 'ER Layer C: issues belonging to one compatibility_result';

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
    compatibility_result_id INT,                       -- optional link from compare → map
    source_schema_format   schema_payload_format NOT NULL,
    target_schema_format   schema_payload_format NOT NULL,
    overview_note          TEXT,                       -- human summary only (NOT field rules)
    lifecycle_status       mapping_lifecycle_status NOT NULL DEFAULT 'DRAFT',
    completeness           mapping_completeness NOT NULL DEFAULT 'PARTIAL',
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_schema_mapping_not_same_api CHECK (source_api_id <> target_api_id),
    CONSTRAINT uq_schema_mapping_pair_versions
        UNIQUE (source_api_id, target_api_id, source_version_id, target_version_id),
    CONSTRAINT fk_sm_source_api
        FOREIGN KEY (source_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_target_api
        FOREIGN KEY (target_api_id) REFERENCES api_submission (api_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_source_version
        FOREIGN KEY (source_version_id) REFERENCES api_version (version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_target_version
        FOREIGN KEY (target_version_id) REFERENCES api_version (version_id)
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

COMMENT ON TABLE schema_mapping IS 'ER Layer E: API-pair mapping overview; field rules are children in mapping_rule';

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

CREATE INDEX idx_compat_source_api ON compatibility_result (source_api_id);
CREATE INDEX idx_compat_target_api ON compatibility_result (target_api_id);
CREATE INDEX idx_compat_issue_result ON compatibility_issue (result_id);

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

INSERT INTO enterprise (name, registration_number, website_url, status) VALUES
    ('Demo Supply Chain Enterprise', 'ENT-0001', 'https://example.com', 'ACTIVE'),
    ('ESS', 'ENT-ESS', 'https://www.ebsoftwareservices.com.au', 'ACTIVE'),
    ('OZEDI Holdings Pty Ltd', 'ENT-OZEDI', 'https://www.ozedi.com.au', 'ACTIVE');

INSERT INTO app_user (enterprise_id, name, email, password_hash, role, status)
VALUES (1, 'Demo Publisher', 'publisher@example.com', 'hashed_password_here', 'PUBLISHER', 'ACTIVE');

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

-- Layer C sample schemas
INSERT INTO api_schema (api_id, version_id, direction, format, raw_schema, normalized_schema, schema_version) VALUES
(2, 4, 'INPUT', 'XML',
 '{"root":"Invoice","fields":["ID","IssueDate","PayableAmount"]}'::jsonb,
 '{"fields":[{"path":"Invoice/ID","type":"string","required":true},{"path":"Invoice/IssueDate","type":"date","required":true},{"path":"Invoice/PayableAmount","type":"number","required":true}]}'::jsonb,
 1),
(3, 5, 'INPUT', 'XML',
 '{"root":"Invoice","fields":["ID","IssueDate"]}'::jsonb,
 '{"fields":[{"path":"Invoice/ID","type":"string","required":true},{"path":"Invoice/IssueDate","type":"date","required":true}]}'::jsonb,
 1);

INSERT INTO schema_field (schema_id, field_path, field_name, field_type, is_required, nesting_depth, parent_path) VALUES
(1, 'Invoice/ID', 'ID', 'string', TRUE, 1, 'Invoice'),
(1, 'Invoice/IssueDate', 'IssueDate', 'date', TRUE, 1, 'Invoice'),
(1, 'Invoice/PayableAmount', 'PayableAmount', 'number', TRUE, 1, 'Invoice'),
(2, 'Invoice/ID', 'ID', 'string', TRUE, 1, 'Invoice'),
(2, 'Invoice/IssueDate', 'IssueDate', 'date', TRUE, 1, 'Invoice');

INSERT INTO compatibility_result (
    source_api_id, target_api_id, source_schema_id, target_schema_id,
    source_version_id, target_version_id, compatibility_level, summary, full_result
) VALUES (
    2, 3, 1, 2, 4, 5, 'COMPATIBLE_WITH_MAPPING',
    '{"matched":2,"missing_on_target":1}'::jsonb,
    '{"level":"compatible_with_mapping","notes":"PayableAmount missing on target."}'::jsonb
);

INSERT INTO compatibility_issue (
    result_id, code, kind, severity, source_path, target_path, message, suggestion
) VALUES (
    1, 'MISSING_TARGET_FIELD', 'mapping', 'warning',
    'Invoice/PayableAmount', NULL,
    'Source field PayableAmount has no counterpart on target schema.',
    'Add a mapping rule or provide a default value before transform.'
);

-- Layer E: overview then field rules then transform
INSERT INTO schema_mapping (
    source_api_id, target_api_id, source_version_id, target_version_id,
    source_schema_id, target_schema_id, compatibility_result_id,
    source_schema_format, target_schema_format,
    overview_note, lifecycle_status, completeness
) VALUES (
    2, 3, 4, 5, 1, 2, 1, 'XML', 'XML',
    'Map common Invoice header fields; drop or default PayableAmount.',
    'ACTIVE', 'PARTIAL'
);

INSERT INTO mapping_rule (
    schema_mapping_id, source_field, target_field, transform_type,
    source_type, target_type, confidence, note
) VALUES
(1, 'Invoice/ID', 'Invoice/ID', 'rename', 'string', 'string', 'high', 'Direct match'),
(1, 'Invoice/IssueDate', 'Invoice/IssueDate', 'rename', 'date', 'date', 'high', 'Direct match'),
(1, 'Invoice/PayableAmount', 'Invoice/PayableAmount', 'drop', 'number', NULL, 'medium', 'Not on target');

INSERT INTO transform_run (
    schema_mapping_id, source_api_id, target_api_id,
    source_schema_id, target_schema_id, source_version_id, target_version_id,
    input_data, output_data, output_format, mapping_status, warnings, success
) VALUES (
    1, 2, 3, 1, 2, 4, 5,
    '{"Invoice":{"ID":"INV-1","IssueDate":"2026-07-01","PayableAmount":120.5}}'::jsonb,
    '{"Invoice":{"ID":"INV-1","IssueDate":"2026-07-01"}}'::jsonb,
    'JSON', 'partial', '["Dropped Invoice/PayableAmount"]'::jsonb, TRUE
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

-- E: mapping package with field rules (normalized join)
SELECT sm.mapping_id, sm.completeness, sm.lifecycle_status,
       mr.source_field, mr.target_field, mr.transform_type, mr.confidence
FROM schema_mapping sm
JOIN mapping_rule mr ON mr.schema_mapping_id = sm.mapping_id
WHERE sm.source_api_id = 2 AND sm.target_api_id = 3;

-- C→E flow: compatibility → mapping → transform
SELECT cr.compatibility_level, sm.mapping_id, sm.completeness,
       tr.transform_run_id, tr.success, tr.mapping_status
FROM compatibility_result cr
LEFT JOIN schema_mapping sm ON sm.compatibility_result_id = cr.result_id
LEFT JOIN transform_run tr ON tr.schema_mapping_id = sm.mapping_id
WHERE cr.result_id = 1;
