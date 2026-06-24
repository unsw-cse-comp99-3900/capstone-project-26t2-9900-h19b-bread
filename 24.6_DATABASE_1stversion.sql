-- ============================================================
-- API Publisher Database Schema
-- For PostgreSQL
-- ============================================================

-- 为了方便重复运行，先删除旧表
DROP TABLE IF EXISTS schema_mapping CASCADE;
DROP TABLE IF EXISTS validation_result CASCADE;
DROP TABLE IF EXISTS validation_run CASCADE;
DROP TABLE IF EXISTS auth_metadata CASCADE;
DROP TABLE IF EXISTS api_specification CASCADE;
DROP TABLE IF EXISTS api_version CASCADE;
DROP TABLE IF EXISTS api_submission CASCADE;
DROP TABLE IF EXISTS app_user CASCADE;
DROP TABLE IF EXISTS enterprise CASCADE;

-- 删除旧 ENUM 类型
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
DROP TYPE IF EXISTS mapping_status CASCADE;

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE enterprise_status AS ENUM (
    'ACTIVE',
    'SUSPENDED',
    'INACTIVE'
);

CREATE TYPE user_role AS ENUM (
    'ADMIN',
    'PUBLISHER',
    'VIEWER'
);

CREATE TYPE user_status AS ENUM (
    'ACTIVE',
    'DISABLED'
);

CREATE TYPE api_protocol_type AS ENUM (
    'REST',
    'SOAP'
);

CREATE TYPE api_submission_status AS ENUM (
    'DRAFT',
    'VALIDATING',
    'REJECTED',
    'PUBLISHED',
    'WITHDRAWN'
);

CREATE TYPE api_version_status AS ENUM (
    'DRAFT',
    'VALIDATING',
    'REJECTED',
    'PUBLISHED',
    'ARCHIVED'
);

CREATE TYPE specification_type AS ENUM (
    'OPENAPI',
    'SWAGGER',
    'WSDL'
);

CREATE TYPE specification_source_type AS ENUM (
    'FILE_UPLOAD',
    'URL_REFERENCE'
);

CREATE TYPE auth_method_type AS ENUM (
    'OAUTH2',
    'API_KEY',
    'BASIC',
    'MTLS',
    'OTHER'
);

CREATE TYPE validation_overall_status AS ENUM (
    'PASSED',
    'FAILED',
    'PARTIAL',
    'RUNNING'
);

CREATE TYPE validation_stage_type AS ENUM (
    'SPECIFICATION_VALIDATION',
    'DOMAIN_COMPLIANCE_VALIDATION',
    'SECURITY_VALIDATION'
);

CREATE TYPE validation_stage_status AS ENUM (
    'PASSED',
    'FAILED',
    'NOT_RUN'
);

CREATE TYPE mapping_status AS ENUM (
    'DRAFT',
    'ACTIVE',
    'FAILED',
    'DEPRECATED'
);

-- ============================================================
-- TABLE: enterprise
-- 企业表
-- ============================================================

CREATE TABLE enterprise (
    enterprise_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    registration_number VARCHAR(100) UNIQUE,
    status enterprise_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE: app_user
-- 用户表
-- 注意：不要命名为 user，因为 USER 是 PostgreSQL 里的敏感词
-- ============================================================

CREATE TABLE app_user (
    user_id SERIAL PRIMARY KEY,
    enterprise_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role user_role NOT NULL DEFAULT 'PUBLISHER',
    status user_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_enterprise
        FOREIGN KEY (enterprise_id)
        REFERENCES enterprise (enterprise_id)
        ON DELETE CASCADE
);

-- ============================================================
-- TABLE: api_submission
-- API 主表，保存 API 元数据和生命周期状态
-- ============================================================

CREATE TABLE api_submission (
    api_id SERIAL PRIMARY KEY,
    enterprise_id INT NOT NULL,
    submitted_by INT NOT NULL,

    api_name VARCHAR(255) NOT NULL,
    endpoint_url VARCHAR(1000) NOT NULL,
    protocol_type api_protocol_type NOT NULL,

    input_format VARCHAR(100) NOT NULL,
    output_format VARCHAR(100) NOT NULL,

    capability_category VARCHAR(100) NOT NULL,
    description TEXT,

    status api_submission_status NOT NULL DEFAULT 'DRAFT',

    withdrawn_reason TEXT,
    withdrawn_at TIMESTAMP,
    withdrawn_by INT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_api_enterprise
        FOREIGN KEY (enterprise_id)
        REFERENCES enterprise (enterprise_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_api_submitted_by
        FOREIGN KEY (submitted_by)
        REFERENCES app_user (user_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_api_withdrawn_by
        FOREIGN KEY (withdrawn_by)
        REFERENCES app_user (user_id)
        ON DELETE SET NULL
);

-- ============================================================
-- TABLE: api_version
-- API 版本表，用于支持 update / resubmission / revalidation
-- ============================================================

CREATE TABLE api_version (
    version_id SERIAL PRIMARY KEY,
    api_id INT NOT NULL,
    created_by INT NOT NULL,

    version_number VARCHAR(50) NOT NULL DEFAULT 'v1.0',
    change_note TEXT,
    status api_version_status NOT NULL DEFAULT 'DRAFT',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_version_api
        FOREIGN KEY (api_id)
        REFERENCES api_submission (api_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_version_created_by
        FOREIGN KEY (created_by)
        REFERENCES app_user (user_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_api_version
        UNIQUE (api_id, version_number)
);

-- ============================================================
-- TABLE: api_specification
-- API 规格文件表，保存 OpenAPI / Swagger / WSDL 信息
-- ============================================================

CREATE TABLE api_specification (
    specification_id SERIAL PRIMARY KEY,
    version_id INT NOT NULL UNIQUE,

    spec_type specification_type NOT NULL,
    source_type specification_source_type NOT NULL,

    file_path VARCHAR(1000),
    spec_url VARCHAR(1000),
    raw_content TEXT,
    checksum VARCHAR(255),

    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_spec_version
        FOREIGN KEY (version_id)
        REFERENCES api_version (version_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_spec_source
        CHECK (
            (source_type = 'FILE_UPLOAD' AND file_path IS NOT NULL)
            OR
            (source_type = 'URL_REFERENCE' AND spec_url IS NOT NULL)
        )
);

-- ============================================================
-- TABLE: auth_metadata
-- 认证与安全元数据表
-- ============================================================

CREATE TABLE auth_metadata (
    auth_id SERIAL PRIMARY KEY,
    api_id INT NOT NULL,

    auth_method auth_method_type NOT NULL,
    auth_description TEXT,
    security_scheme_name VARCHAR(255),
    is_complete BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_auth_api
        FOREIGN KEY (api_id)
        REFERENCES api_submission (api_id)
        ON DELETE CASCADE
);

-- ============================================================
-- TABLE: validation_run
-- 一次完整验证流程
-- ============================================================

CREATE TABLE validation_run (
    validation_run_id SERIAL PRIMARY KEY,
    api_id INT NOT NULL,
    version_id INT NOT NULL,

    overall_status validation_overall_status NOT NULL DEFAULT 'RUNNING',

    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    CONSTRAINT fk_validation_api
        FOREIGN KEY (api_id)
        REFERENCES api_submission (api_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_validation_version
        FOREIGN KEY (version_id)
        REFERENCES api_version (version_id)
        ON DELETE CASCADE
);

-- ============================================================
-- TABLE: validation_result
-- 每个验证阶段的结果
-- ============================================================

CREATE TABLE validation_result (
    result_id SERIAL PRIMARY KEY,
    validation_run_id INT NOT NULL,

    stage validation_stage_type NOT NULL,
    status validation_stage_status NOT NULL DEFAULT 'NOT_RUN',

    message TEXT,
    error_detail TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_result_validation_run
        FOREIGN KEY (validation_run_id)
        REFERENCES validation_run (validation_run_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_validation_stage
        UNIQUE (validation_run_id, stage)
);

-- ============================================================
-- TABLE: schema_mapping
-- API 到 API 的 Schema Mapping 表
-- ============================================================

CREATE TABLE schema_mapping (
    mapping_id SERIAL PRIMARY KEY,

    source_api_id INT NOT NULL,
    target_api_id INT NOT NULL,

    source_schema_format VARCHAR(100) NOT NULL,
    target_schema_format VARCHAR(100) NOT NULL,

    mapping_rules TEXT,
    status mapping_status NOT NULL DEFAULT 'DRAFT',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_mapping_source_api
        FOREIGN KEY (source_api_id)
        REFERENCES api_submission (api_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_mapping_target_api
        FOREIGN KEY (target_api_id)
        REFERENCES api_submission (api_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_mapping_not_same_api
        CHECK (source_api_id <> target_api_id)
);

-- ============================================================
-- INDEXES
-- 提升常用查询性能
-- ============================================================

CREATE INDEX idx_user_enterprise_id
    ON app_user (enterprise_id);

CREATE INDEX idx_api_enterprise_id
    ON api_submission (enterprise_id);

CREATE INDEX idx_api_submitted_by
    ON api_submission (submitted_by);

CREATE INDEX idx_api_status
    ON api_submission (status);

CREATE INDEX idx_api_protocol_type
    ON api_submission (protocol_type);

CREATE INDEX idx_api_capability_category
    ON api_submission (capability_category);

CREATE INDEX idx_version_api_id
    ON api_version (api_id);

CREATE INDEX idx_validation_api_id
    ON validation_run (api_id);

CREATE INDEX idx_validation_version_id
    ON validation_run (version_id);

CREATE INDEX idx_validation_result_run_id
    ON validation_result (validation_run_id);

CREATE INDEX idx_mapping_source_api
    ON schema_mapping (source_api_id);

CREATE INDEX idx_mapping_target_api
    ON schema_mapping (target_api_id);

-- ============================================================
-- SAMPLE DATA
-- 可选测试数据，方便你在 DBeaver 里看到表之间的关系
-- ============================================================

INSERT INTO enterprise (
    name,
    registration_number,
    status
) VALUES (
    'Demo Supply Chain Enterprise',
    'ENT-0001',
    'ACTIVE'
);

INSERT INTO app_user (
    enterprise_id,
    name,
    email,
    password_hash,
    role,
    status
) VALUES (
    1,
    'Demo Publisher',
    'publisher@example.com',
    'hashed_password_here',
    'PUBLISHER',
    'ACTIVE'
);

INSERT INTO api_submission (
    enterprise_id,
    submitted_by,
    api_name,
    endpoint_url,
    protocol_type,
    input_format,
    output_format,
    capability_category,
    description,
    status
) VALUES (
    1,
    1,
    'Invoice Validation API',
    'https://api.example.com/invoices/validate',
    'REST',
    'JSON',
    'JSON',
    'invoice validation',
    'Validates submitted e-invoice data against selected business and tax rules.',
    'DRAFT'
);

INSERT INTO api_version (
    api_id,
    created_by,
    version_number,
    change_note,
    status
) VALUES (
    1,
    1,
    'v1.0',
    'Initial API submission.',
    'DRAFT'
);

INSERT INTO api_specification (
    version_id,
    spec_type,
    source_type,
    spec_url,
    checksum
) VALUES (
    1,
    'OPENAPI',
    'URL_REFERENCE',
    'https://api.example.com/openapi.json',
    'demo-checksum-001'
);

INSERT INTO auth_metadata (
    api_id,
    auth_method,
    auth_description,
    security_scheme_name,
    is_complete
) VALUES (
    1,
    'OAUTH2',
    'OAuth 2.0 bearer token authentication is required.',
    'BearerAuth',
    TRUE
);

INSERT INTO validation_run (
    api_id,
    version_id,
    overall_status,
    completed_at
) VALUES (
    1,
    1,
    'PASSED',
    CURRENT_TIMESTAMP
);

INSERT INTO validation_result (
    validation_run_id,
    stage,
    status,
    message,
    error_detail
) VALUES
(
    1,
    'SPECIFICATION_VALIDATION',
    'PASSED',
    'OpenAPI specification is syntactically and structurally valid.',
    NULL
),
(
    1,
    'DOMAIN_COMPLIANCE_VALIDATION',
    'PASSED',
    'API operations and data formats are consistent with selected e-invoicing rules.',
    NULL
),
(
    1,
    'SECURITY_VALIDATION',
    'PASSED',
    'Authentication metadata is complete and acceptable.',
    NULL
);

-- 模拟发布成功
UPDATE api_submission
SET status = 'PUBLISHED',
    updated_at = CURRENT_TIMESTAMP
WHERE api_id = 1;

UPDATE api_version
SET status = 'PUBLISHED'
WHERE version_id = 1;

-- ============================================================
-- USEFUL CHECK QUERIES
-- ============================================================

-- 查看企业发布的 API
SELECT
    e.name AS enterprise_name,
    u.name AS publisher_name,
    a.api_name,
    a.endpoint_url,
    a.protocol_type,
    a.input_format,
    a.output_format,
    a.capability_category,
    a.status
FROM api_submission a
JOIN enterprise e ON a.enterprise_id = e.enterprise_id
JOIN app_user u ON a.submitted_by = u.user_id;

-- 查看某个 API 的验证结果
SELECT
    a.api_name,
    vr.validation_run_id,
    vr.overall_status,
    r.stage,
    r.status,
    r.message,
    r.error_detail
FROM validation_run vr
JOIN api_submission a ON vr.api_id = a.api_id
JOIN validation_result r ON vr.validation_run_id = r.validation_run_id
ORDER BY vr.validation_run_id, r.result_id;

-- 查看已发布 API
SELECT
    api_id,
    api_name,
    endpoint_url,
    protocol_type,
    capability_category,
    status
FROM api_submission
WHERE status = 'PUBLISHED';

-- 查看草稿 API
SELECT
    api_id,
    api_name,
    status,
    created_at,
    updated_at
FROM api_submission
WHERE status = 'DRAFT';