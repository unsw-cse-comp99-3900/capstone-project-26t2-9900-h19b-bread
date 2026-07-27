# Validation Pipeline Rules — Reference

Owner: Backend Member 2 (Validation Pipeline)
Scope: the full submission validation pipeline — structural validation (FR-4),
e-invoicing domain compliance (FR-5), security metadata (FR-6), and the broad
"metadata consistency" checks (FR-3) that verify submission-form metadata against
the actual uploaded specification. Covers **both REST/OpenAPI and SOAP/WSDL**.

Implementation: `app/services/validation_service.py`
Entry point: `validate_specification(ValidationRequest) -> ValidationResponse`

---

## 1. Pipeline overview

The pipeline runs a fixed 3-stage model. The stages are baked into the database
`validation_stage_type` ENUM and the frontend, so the FR-3 metadata checks are
**folded into the existing stages** rather than adding a 4th stage.

| # | Stage (enum)                     | FR    | What it checks |
|---|----------------------------------|-------|----------------|
| 1 | `SPECIFICATION_VALIDATION`       | FR-4  | parse + structural validity; protocol / endpoint / format metadata consistency |
| 2 | `DOMAIN_COMPLIANCE_VALIDATION`   | FR-5  | is this really an e-invoicing API; capability_category consistency |
| 3 | `SECURITY_VALIDATION`            | FR-6  | authentication metadata vs. declared security |

Stage ordering is strict: **if FR-4 does not pass, FR-5 and FR-6 are reported as
`NOT_RUN`** (they depend on a parsed, valid spec). Each stage returns `PASS`,
`FAIL`, or `NOT_RUN`. `overall_status` is `PASS` only when every executed
(non-`NOT_RUN`) stage passed.

## 2. Severity model

- **Blocking (`severity="error"`)** → fails the stage, rejects publication.
- **Non-blocking (`severity="warning"`)** → surfaced to the publisher (FR-7) but
  does not fail the stage.

A stage fails only if it holds at least one non-warning error (`_has_blocking`).
This lets us report soft inconsistencies without rejecting otherwise valid APIs.

---

## 3. FR-4 — Specification validation

### REST / OpenAPI
- Parse YAML/JSON (`parse_openapi`). Parse failure → `PARSE_ERROR` (FAIL).
- Structural validation via `openapi-spec-validator` (`validate_spec`).
  Invalid structure → `OPENAPI_INVALID_STRUCTURE` (FAIL); unexpected error →
  `VALIDATION_INTERNAL_ERROR` (FAIL).

### SOAP / WSDL
- Parse XML (`parse_wsdl`). Malformed XML → `WSDL_MALFORMED_XML` (FAIL);
  root element not `<definitions>` → `WSDL_INVALID_STRUCTURE` (FAIL).
- Structural completeness (`_validate_wsdl_structure`, the WSDL analogue of
  `validate_spec`):
  - no `<portType>` → `WSDL_NO_PORTTYPE` (FAIL)
  - `<portType>` present but no `<operation>` → `WSDL_NO_OPERATION` (FAIL)

---

## 4. FR-3 — Metadata consistency (folded into FR-4 / FR-5)

| Metadata check                    | Reported under stage |
|-----------------------------------|----------------------|
| protocol ↔ spec type              | SPECIFICATION (FR-4) |
| endpoint_url ↔ spec endpoints     | SPECIFICATION (FR-4) |
| input/output format ↔ spec        | SPECIFICATION (FR-4) |
| capability_category               | DOMAIN (FR-5)        |

### 4.1 protocol ↔ spec type — blocking
Before parsing, the raw content is sniffed: content starting with `<` is XML/WSDL.
- Declared REST but content looks like XML/WSDL → `METADATA_PROTOCOL_SPEC_MISMATCH` (FAIL).
- Declared SOAP but content is not XML → `METADATA_PROTOCOL_SPEC_MISMATCH` (FAIL).

### 4.2 endpoint_url ↔ spec endpoints — warning
Compares the **host** of `endpoint_url` against the hosts declared in the spec.
- REST: hosts from OpenAPI `servers[].url`.
- SOAP: hosts from every `<soap:address location="...">`.
- No endpoints declared → `METADATA_ENDPOINT_UNVERIFIABLE` (warning).
- Host not among declared endpoints → `METADATA_ENDPOINT_MISMATCH` (warning).

Rationale: staging/production hosts legitimately differ, so a mismatch informs
but does not reject.

### 4.3 input/output format ↔ spec — warning
Declared format is mapped to a token (`JSON→json`, `XML→xml`, `UBL→xml`,
`PDF→pdf`, `CSV→csv`, `YAML→yaml`).
- REST: tokens are checked against media types collected from all
  `requestBody.content` (input) and `responses.*.content` (output) keys. If the
  spec declares no content types, the check is skipped.
- SOAP: message payloads are inherently XML, so any declared format whose token
  is not `xml` (e.g. JSON) is flagged.
- Mismatch → `METADATA_INPUT_FORMAT_MISMATCH` / `METADATA_OUTPUT_FORMAT_MISMATCH`
  (warning).

### 4.4 capability_category — blocking (invalid) / warning (inconsistent)
Accepted categories: `invoice creation`, `validation`, `transmission`, `archiving`.
Runs for both REST and SOAP (matched against the stage's textual "haystack").
- Value not recognized → `METADATA_CAPABILITY_INVALID` (FAIL).
- Recognized but no matching operation names/summaries →
  `METADATA_CAPABILITY_INCONSISTENT` (warning).

---

## 5. FR-5 — E-invoicing domain compliance

Aligned with EN 16931 / UBL 2.1 / PEPPOL BIS Billing 3.0. Signal extraction is
protocol-specific; the scoring/decision is shared (`_evaluate_domain_signals`).

### Signals
- **strong** = number of the 9 core invoice field categories matched among the
  spec's field names (0..9). Categories: invoice number, invoice date, invoice
  type code, currency, seller, buyer, totals, tax, line items.
- **standard** = +2 if the spec references a recognized standard
  (`ubl`, `peppol`, `en16931`, `bis billing`).
- **keyword** = weak textual keywords (invoice/tax/billing/…), capped at +2.
- **score** = strong + standard + min(keyword, 2).

Field-name / haystack source:
- REST: property names from `components.schemas` **and** inline path schemas;
  haystack from title/description/tags/paths/operations.
- SOAP: names of XSD `element`/`attribute`/`complexType`/`simpleType` under
  `<types>`; haystack from portType/operation/service names, `<documentation>`,
  and all namespace URIs / `targetNamespace` (where UBL/PEPPOL markers live).

### Hard gate + decision
A submission can PASS only with **structural or standard** evidence
(`strong >= 1 OR standard`). This blocks "keyword-only" fakes.
- not (strong ≥ 1 or standard) → `DOMAIN_NOT_EINVOICING` (FAIL)
- eligible and score ≥ 4 → PASS (no error)
- eligible and 2 ≤ score < 4 → PASS + `DOMAIN_INSUFFICIENT_SIGNALS` (warning)
- eligible and score < 2 → `DOMAIN_NOT_EINVOICING` (FAIL)
- parsed spec unavailable → `DOMAIN_SPEC_UNAVAILABLE` (FAIL)

---

## 6. FR-6 — Security & authentication metadata

`auth_method` is submission-form metadata (distinct from the spec's own security
declaration). Accepted values: `OAuth2`, `API Key`, `Basic`, `mTLS`
(aliases normalized, e.g. `OAuth 2.0` → `OAUTH2`).

### Rule 1 (both protocols)
- Missing → `SECURITY_AUTH_METHOD_MISSING` (FAIL).
- Not an accepted value → `SECURITY_AUTH_METHOD_UNSUPPORTED` (FAIL).

### REST
- No `components.securitySchemes` → `SECURITY_SCHEME_MISSING` (FAIL).
- `auth_method` not matching any declared scheme type →
  `SECURITY_AUTH_METADATA_MISMATCH` (FAIL).
- Schemes declared but not applied at root/operation level →
  `SECURITY_REQUIREMENT_MISSING` (FAIL).
- Parsed spec unavailable → `SECURITY_SPEC_UNAVAILABLE` (FAIL).

### SOAP
Evidence detected from WSDL: `<wsp:Policy>`, WS-SecurityPolicy tokens
(`UsernameToken`→BASIC, `X509Token`/`TransportBinding`→MTLS,
`IssuedToken`/`SamlToken`→OAUTH2), and HTTPS `<soap:address>`→MTLS. `API_KEY`
has no standard place in WSDL and is never positively detectable.
- No policy / token / HTTPS transport at all → `SECURITY_REQUIREMENT_MISSING`
  (FAIL). *(Decision 1: parity with REST — security must be declared.)*
- `BASIC` / `MTLS` declared but not reflected by the WSDL →
  `SECURITY_AUTH_METADATA_MISMATCH` (FAIL). *(strongly detectable → strict.)*
- `OAUTH2` / `API_KEY` declared but not verifiable from the WSDL →
  `SECURITY_AUTH_UNVERIFIABLE` (warning). *(Decision 2: format limitation, not a
  user error — do not block.)*
- Parsed spec unavailable → `SECURITY_SPEC_UNAVAILABLE` (FAIL).

---

## 7. Error codes summary

| Code                             | Stage         | Severity | Protocol |
|----------------------------------|---------------|----------|----------|
| PARSE_ERROR                      | specification | error    | REST     |
| OPENAPI_INVALID_STRUCTURE        | specification | error    | REST     |
| VALIDATION_INTERNAL_ERROR        | specification | error    | REST     |
| WSDL_MALFORMED_XML               | specification | error    | SOAP     |
| WSDL_INVALID_STRUCTURE           | specification | error    | SOAP     |
| WSDL_NO_PORTTYPE                 | specification | error    | SOAP     |
| WSDL_NO_OPERATION                | specification | error    | SOAP     |
| METADATA_PROTOCOL_SPEC_MISMATCH  | specification | error    | both     |
| METADATA_ENDPOINT_UNVERIFIABLE   | specification | warning  | both     |
| METADATA_ENDPOINT_MISMATCH       | specification | warning  | both     |
| METADATA_INPUT_FORMAT_MISMATCH   | specification | warning  | both     |
| METADATA_OUTPUT_FORMAT_MISMATCH  | specification | warning  | both     |
| DOMAIN_NOT_EINVOICING            | domain        | error    | both     |
| DOMAIN_INSUFFICIENT_SIGNALS      | domain        | warning  | both     |
| DOMAIN_SPEC_UNAVAILABLE          | domain        | error    | both     |
| METADATA_CAPABILITY_INVALID      | domain        | error    | both     |
| METADATA_CAPABILITY_INCONSISTENT | domain        | warning  | both     |
| SECURITY_AUTH_METHOD_MISSING     | security      | error    | both     |
| SECURITY_AUTH_METHOD_UNSUPPORTED | security      | error    | both     |
| SECURITY_SCHEME_MISSING          | security      | error    | REST     |
| SECURITY_AUTH_METADATA_MISMATCH  | security      | error    | both     |
| SECURITY_REQUIREMENT_MISSING     | security      | error    | both     |
| SECURITY_AUTH_UNVERIFIABLE       | security      | warning  | SOAP     |
| SECURITY_SPEC_UNAVAILABLE        | security      | error    | both     |

## 8. Inputs

`ValidationRequest` carries the submission-form metadata (all optional so
existing callers keep working): `protocol`, `spec_content`, `auth_method`,
`endpoint_url`, `input_format`, `output_format`, `capability_category`.
`app/routers/submissions.py` populates them from `SubmissionRequest`.

## 9. Tests (48 total)

- `tests/test_validation_domain.py` — FR-5 scoring, hard gate, REST + SOAP.
- `tests/test_validation_security.py` — FR-6 Rule 1/2/3, REST + SOAP decisions.
- `tests/test_validation_metadata.py` — FR-3 metadata consistency (REST + SOAP),
  WSDL structure, and full-pipeline behaviour (incl. an end-to-end SOAP pass).

Run: `cd backend && pytest tests/ -q`
