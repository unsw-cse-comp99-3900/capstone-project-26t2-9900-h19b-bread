# 19.7_database Setup

This README describes how to apply **`19.7database.sql`** (schema id: `19.7_database`).

It is an ER-standard fused PostgreSQL schema for:

- API identity and publication
- Version history (frontend history list)
- Catalogue-style metadata
- Publish validation
- Compatibility assessment
- Schema mapping and transform runs

---

## 1. Requirements

- PostgreSQL (local Docker or any running instance)
- A SQL client such as DBeaver

---

## 2. Apply the script

1. Connect to your PostgreSQL database.
2. Open `19.7database.sql`.
3. Execute the **entire** script (Execute SQL Script / `Alt + X`).
4. Refresh the database navigator / ER diagram.

The script begins with `DROP ... CASCADE`, so re-running it **removes existing tables, types, and sample data**, then recreates them.

---

## 3. ER layers and tables

Centre entity: `api_submission`.

| Layer | Role | Tables |
|---|---|---|
| A | Identity and publishing | `enterprise`, `app_user`, `api_submission`, `api_version`, `api_version_event`, `api_specification` |
| B | Catalogue enrichment | `auth_metadata` (+ catalogue columns on A tables) |
| C | Compatibility engine | `api_schema`, `schema_field`, `compatibility_result`, `compatibility_issue` |
| D | Publish validation | `validation_run`, `validation_result` |
| E | Mapping and transform | `schema_mapping`, `mapping_rule`, `transform_run` |

**16 tables** in total.

### Important design points (from the SQL header)

1. Every relationship has an explicit FK and `ON DELETE` policy.
2. Cardinality is enforced with `UNIQUE` / partial unique indexes where needed.
3. Field mapping truth lives only in `mapping_rule` (not a TEXT blob on `schema_mapping`).
4. Weak entities cascade with their parents.
5. Associative entities use role-named FKs (`source_*` / `target_*`).
6. Create order follows parent → child dependency.

### Core relationships

- `enterprise` 1—N `app_user`
- `enterprise` 1—N `api_submission`
- `api_submission` 1—N `api_version`
- `api_submission.current_version_id` → current `api_version` (at most one `is_current` per API)
- `api_version.previous_version_id` → previous version
- `api_version` 1—1 `api_specification`
- `api_version` 1—N `api_schema` (INPUT / OUTPUT)
- `api_schema` 1—N `schema_field`
- `validation_run` 1—N `validation_result`
- `compatibility_result` 1—N `compatibility_issue`
- `schema_mapping` 1—N `mapping_rule`
- `transform_run` may reference `schema_mapping`

---

## 4. Custom ENUM types

PostgreSQL `CREATE TYPE ... AS ENUM` types used by this script:

| Type | Purpose |
|---|---|
| `enterprise_status` | Enterprise lifecycle |
| `user_role` / `user_status` | User role and account status |
| `api_protocol_type` | REST, SOAP, WEB, CLI, OTHER |
| `api_submission_status` | API publication lifecycle |
| `api_version_status` | Version lifecycle |
| `specification_type` / `specification_source_type` | Spec artifact metadata |
| `auth_method_type` | Normalized auth method |
| `validation_overall_status` / `validation_stage_type` / `validation_stage_status` | Publish validation |
| `version_event_type` | Version timeline events |
| `api_category_type` | TRANSFORMATION, VALIDATION, COMMUNICATION |
| `schema_direction_type` | INPUT, OUTPUT |
| `schema_payload_format` | JSON, XML |
| `compatibility_level_type` | Direct / needs mapping / incompatible |
| `mapping_lifecycle_status` | Mapping package lifecycle |
| `mapping_completeness` | FULL, PARTIAL, INCOMPATIBLE |
| `field_transform_type` | rename, cast, wrap_array, … |
| `confidence_level` | high, medium, low |
| `transform_output_format` / `transform_mapping_status` | Transform run |
| `issue_kind_type` / `issue_severity_type` | Compatibility issues |

In DBeaver these appear under **Data types**.

Catalogue multi-value fields on `api_version` use JSONB:

- `input_formats`, `output_formats`, `business_rules`, `client_types`

Also on versions / submissions: `catalogue_id`, `instructions`, `documentation_url`, `network`, `website_url` (enterprise), `auth_method_raw`.

---

## 5. Sample data in the script

After execution you get:

- Enterprises: Demo Supply Chain, ESS, OZEDI
- User: `publisher@example.com`
- `Invoice Validation API` with versions `v1.0` / `v1.1` / `v2.0`
- Catalogue-style APIs: `ESSAnalyse`, `OZEDI Document Send API`
- One compatibility result + issues
- One `schema_mapping` with field `mapping_rule` rows
- One `transform_run`

---

## 6. Verification queries (included at end of SQL)

```sql
-- Published catalogue view
SELECT s.api_id, s.catalogue_id, s.api_name, s.category,
       v.version_number, v.endpoint_url, v.input_formats, v.network, e.name AS company
FROM api_submission s
JOIN api_version v ON s.current_version_id = v.version_id
JOIN enterprise e ON s.enterprise_id = e.enterprise_id
WHERE s.status = 'PUBLISHED'
ORDER BY s.api_name;

-- Version history chain
SELECT version_id, version_number, status, is_current, previous_version_id, created_at
FROM api_version
WHERE api_id = 1
ORDER BY created_at;

-- Mapping package + field rules
SELECT sm.mapping_id, sm.completeness, sm.lifecycle_status,
       mr.source_field, mr.target_field, mr.transform_type, mr.confidence
FROM schema_mapping sm
JOIN mapping_rule mr ON mr.schema_mapping_id = sm.mapping_id
WHERE sm.source_api_id = 2 AND sm.target_api_id = 3;

-- Compatibility -> mapping -> transform
SELECT cr.compatibility_level, sm.mapping_id, sm.completeness,
       tr.transform_run_id, tr.success, tr.mapping_status
FROM compatibility_result cr
LEFT JOIN schema_mapping sm ON sm.compatibility_result_id = cr.result_id
LEFT JOIN transform_run tr ON tr.schema_mapping_id = sm.mapping_id
WHERE cr.result_id = 1;
```

---

## 7. Quick checklist

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

SELECT typname
FROM pg_type
WHERE typtype = 'e'
ORDER BY typname;
```

Expect **16 tables** and the ENUM types listed in section 4.

---

## 8. Notes

- Do not store plain-text passwords; `app_user.password_hash` expects a hash.
- Expand ER table boxes in DBeaver if only headers are visible.
- Schema file: `19.7database.sql`  
- Schema id in comments: `19.7_database`
