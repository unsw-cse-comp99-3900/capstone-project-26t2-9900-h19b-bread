# Software Quality gap analysis and refactoring plan

Audit date: 11 August 2026
Branch: `feature/refactor`
Audited commit: `1e03467`

## 1. Scope and evidence boundary

This audit compares the current checkout against:

- the four-page UNSW Software Quality Specification supplied on 11 August 2026;
- the project's approved proposal and its thirteen functional requirements;
- the original client project specification and expected deliverables; and
- evidence that can be reproduced from the current checkout.

The Software Quality PDF says `26T1`, while this repository and proposal are for `26T2`. The marking categories appear applicable, but the term label should be confirmed with the tutor before submission.

The assessment distinguishes source inspection, automated tests, static checks, builds, and live deployment. One does not substitute for another. Docker Compose configuration is valid, but Docker Desktop was not running during this audit, so current live-container and HTTP checks remain pending.

## 2. Executive conclusion

The score-focused refactor has addressed the identified source-level P0 security defects, introduced reproducible backend and frontend coverage gates, added frontend component/interaction tests, removed frontend lint errors, and added a Playwright critical-workflow suite. FR-12, the formal test report, and the installation manual are intentionally outside the current scope. Live authenticated browser workflows also remain unproven because the Docker stack and test credentials were unavailable.

Conservative post-refactor estimate: **13.25/20**, with a plausible range of **12.25-15.75/20** depending on the final demo, live-stack evidence, and the tutor's treatment of deferred FR-12.

| Category | Current estimate | Main reason the next band is not yet defensible |
| --- | ---: | --- |
| Completeness | 4.5 / 7.5 | The Publisher objectives are substantially implemented, but FR-12 and the Publisher-to-Discovery-to-Composition scenario are intentionally deferred. |
| Technical Quality | 3.75 / 5 | Non-trivial validation/mapping logic is supported by stronger password storage, closed-by-default registration, SSRF controls, tenant authorization, and regression tests; performance evidence and some layering remain weak. |
| Code Style and Testing | 4 / 5 | Backend: 189 passing tests and 71.40% branch-aware coverage. Frontend: 30 passing tests, enforced coverage thresholds, clean lint, and a Playwright suite; authenticated live E2E and deeper router/repository coverage remain gaps. |
| User Experience | 1 / 2.5 (provisional) | This is primarily demo-assessed. The standalone UI is usable, but unified navigation is missing and no repeatable UI/usability test evidence exists. |

## 3. Reproduced evidence

| Check | Result | Interpretation |
| --- | --- | --- |
| Backend suite | `189 passed, 19 warnings` | Includes password migration, registration-boundary, SSRF, redirect, and tenant-isolation regressions. |
| Backend coverage | 71.40% with branch measurement | `.coveragerc` enforces a 70% overall minimum; security-critical modules have direct regression coverage, although route/repository depth can improve. |
| Frontend tests | `30 passed` across 13 test files | Vitest/RTL tests cover authentication, session expiry, registration validation, dashboard/detail interactions, schema mapping, layout, and service helpers. |
| Frontend coverage | 57.25% statements, 39.78% branches, 60.08% functions, 57.93% lines | V8 thresholds are enforced at 50/35/45/50 respectively. |
| Frontend lint | Passed | ESLint completes with zero errors. |
| Frontend production build | Passed outside the restricted sandbox | TypeScript and Vite build succeed; the restricted run's `spawn EPERM` is environmental. The main JS bundle is about 1.40 MB before gzip and triggers a chunk-size warning. |
| Compose configuration | Passed | `docker compose --env-file docker/.env config --quiet` succeeds. |
| Live Compose stack | Not run in this audit | Docker Desktop was not running; current container health and HTTP behaviour are not proven. |
| Playwright critical workflows | 1 passed, 2 skipped | The unauthenticated session-expiry redirect passed against the development server; authenticated dashboard and publication workflows require configured backend credentials. |
| Generated API contract | 29 paths | The FastAPI application generates an OpenAPI contract covering auth, submissions, validation, lifecycle, version history, mapping, and connection validation. |
| CI quality gates | Missing | No committed `.github` workflow, coverage gate, Python lint/type-check configuration, or frontend test gate was found. |

## 4. Functional-requirement matrix

Status definitions: **Implemented** means source and automated evidence support the requirement; **Partial** means an important acceptance condition or integration is missing; **Evidence gap** means the feature may work but the required proof is absent.

| FR | Status | Current evidence | Gap or risk |
| --- | --- | --- | --- |
| FR-1 Authentication and authorization | Implemented with operational caveat | Salted scrypt password storage with legacy migration, closed-by-default public registration, fixed `PUBLISHER` assignment, and enterprise-scoped version reads | Existing database volumes are not rewritten by initializer changes and must be migrated/reset or remediated separately. |
| FR-2 OpenAPI/WSDL file and URL upload | Implemented | File, pasted content, and URL routes; URL adapter restricts schemes/ports, rejects non-global destinations, validates redirects, and caps time/size | A live integration test against the deployed network path remains desirable. |
| FR-3 Metadata capture | Implemented | Structured frontend form, Pydantic/database fields, and component tests | The main form remains oversized and should eventually be decomposed. |
| FR-4 Specification validation | Implemented | OpenAPI validation, WSDL parsing, failure results, positive/negative tests | Document supported versions and validator limitations in the user guide. |
| FR-5 E-invoicing domain validation | Implemented | Modular domain rules and REST/SOAP tests | Rules are project-defined rather than a complete PEPPOL/EN16931 conformance engine; state this limitation precisely. |
| FR-6 Security metadata validation | Implemented | Modular checks for accepted methods, declarations, and consistency | This validates submitted API metadata; it does not compensate for the Publisher application's own security defects. |
| FR-7 Validation feedback | Implemented | Structured stage/status/message models, UI display, and component interaction tests | Broader live resubmission coverage remains desirable. |
| FR-8 Publish to central repository | Partial | Validated records persist to the project PostgreSQL schema | No demonstrated Discovery/Composition consumer contract or real downstream hand-off. |
| FR-9 Draft and resubmission | Implemented, evidence gap | Draft route, version/lifecycle workflow, and browser scenario definition | The credential-dependent browser workflow was skipped and still needs live execution. |
| FR-10 Enterprise API listing | Implemented | Enterprise-scoped dashboard queries plus filter/pagination interaction tests | Add deployed cross-tenant workflow evidence. |
| FR-11 Update and withdrawal | Implemented | Version writes, lifecycle transitions, withdrawal route and tests | Add full workflow tests against PostgreSQL, including unauthorized and concurrent attempts. |
| FR-12 Unified UI integration | Deferred by current scope | Publisher has its own React shell | No Discovery or Composition routes/navigation are present; no FR-12 feature work was added in this refactor. |
| FR-13 API schema mapping | Implemented | Schema extraction, comparison, mapping rules, transformation preview, persisted evidence, acceptance tests | Clarify supported JSON/XML transformations and explicitly keep PDF-to-XML as future work. |

## 5. Deliverable gaps

The original client specification asks for more than source code. The following are missing or incomplete in the tracked checkout:

1. **Formal test report:** measured coverage and automated gates now exist, but the requested report narrative is intentionally deferred.
2. **Live end-to-end evidence:** component/interaction tests and Playwright scenarios exist, but authenticated Compose workflows have not yet been executed.
3. **Documented Publisher-to-Discovery-to-Composition scenario:** no repeatable scenario demonstrates one published API being discovered and composed.
4. **Unified ecosystem integration evidence:** source routes and navigation are Publisher-only.
5. **User guide:** current READMEs are primarily developer/deployment guides and do not fully explain preparation, validation remediation, versioning, withdrawal, and schema-mapping workflows for an enterprise user.
6. **PDF installation manual:** no tracked installation-manual PDF was found. The school submission explicitly requires one alongside the ZIP.
7. **Complete technical design documentation:** validation rules are documented, but the current architecture, repository/downstream interfaces, data model, trust boundaries, and known limitations are not collected into one current technical document.
8. **Representative demonstration package:** REST/WSDL test fixtures exist, but the tracked `docs/` samples do not form the required documented end-to-end ecosystem demonstration.
9. **Submission automation/evidence:** there is no repeatable clean-package check for required files, excluded secrets/caches, size, and checksum.

## 6. Highest-priority defects

### P0 - implemented in source on `feature/refactor`

1. **Registration boundary:** the public request can no longer choose role or enterprise; public registration is disabled by default and, when explicitly enabled, uses a server-configured enterprise and the `PUBLISHER` role.
2. **Password storage:** new passwords use salted scrypt; a successful login migrates a valid legacy SHA-256 hash. Minimum password length is 12 characters.
3. **SSRF protection:** the URL-fetch adapter restricts scheme/port, rejects non-global resolved addresses, checks redirects, caps response size/time, and returns controlled errors.
4. **Tenant authorization:** version-history/specification reads enforce enterprise ownership unless the actor is an administrator; cross-tenant denial tests were added.
5. **Role model consistency:** unsupported `MANAGER` references were removed to match the database enum.
6. **Seed credential:** fresh initialization installs the old demo user as disabled with no usable predictable password. Existing volumes still require explicit remediation.

### P1 - secure the marks for testing and completeness

1. Extend backend coverage into PostgreSQL transaction/unique-conflict/lifecycle-race paths; current security regression tests and the 70% overall gate are in place.
2. Expand frontend tests around upload, withdrawal, version editing, and detailed validation remediation; the Vitest/RTL foundation and current coverage gates are in place.
3. Run the authenticated dashboard and secure publication Playwright scenarios against a live Compose environment, then extend them to invalid/correction, WSDL, cross-tenant, update/withdraw, and mapping workflows.
4. Raise the present backend 70% and frontend 50/35/45/50 thresholds after the weakest routers, repositories, and large UI modules receive direct tests.
5. FR-12 and the Publisher-to-Discovery-to-Composition demonstration remain intentionally deferred by the current request.

### P2 - improve maintainability, performance, and UX evidence

1. Move SQL and network access out of route handlers into service/repository/adaptor layers. Keep FastAPI routers focused on transport and authorization.
2. Split `APIInfoForm.tsx`, `SchemaMappingPage.tsx`, `HomePage.tsx`, and `ApiDetailPage.tsx` into smaller state hooks and presentational components. Split the 775-line submission router by workflow.
3. Frontend lint errors are fixed without disabling the rule; retain the clean-lint gate while continuing module decomposition.
4. Add Python formatting/lint/type-check configuration (for example Ruff plus mypy or Pyright) and run it with ESLint, tests, and builds in CI.
5. Code-split heavy frontend pages and measure initial-load performance. Add backend load tests for listing, submission, and validation with documented data volume and percentile latency.
6. Conduct scripted usability/accessibility testing: keyboard navigation, labels, focus after errors, loading/empty/error states, destructive confirmation, narrow viewport, and session-expiry recovery.

### P3 - make the submission independently markable

1. Expand the README testing section into a concise test strategy and link to a committed test/coverage report.
2. Write current technical architecture, user guide, limitations, and troubleshooting documents.
3. Generate and visually verify the required PDF installation manual. Include the exact Compose command with `--env-file docker/.env`, environment preparation, health checks, URLs, sample accounts only when safe, reset/data-loss warnings, and troubleshooting.
4. Add a clean-package script/check based on a verified commit. Ensure the ZIP contains Docker files, source, fixtures, and manuals but excludes `.git`, real `.env`, virtual environments, `node_modules`, caches, logs, debug files, and generated output.
5. Record ZIP size, entry inspection, SHA-256, clean-clone installation result, container health, HTTP checks, and the complete automated-test results before Moodle submission.

## 7. Recommended implementation sequence and exit gates

| Phase | Target | Exit gate |
| --- | --- | --- |
| 1. Security baseline | P0 items 1-6 | New regression tests pass; cross-tenant and SSRF attempts are denied; no caller can self-assign privilege; no weak/predictable credential is installed. |
| 2. Test foundation | Backend integration, frontend component, and coverage tooling | Coverage reports are generated reproducibly; critical happy/sad cases are automated; lint and test commands all return zero. |
| 3. Completeness | FR-8/FR-12 and ecosystem demo | A fresh Compose environment can publish, discover, and compose the documented sample, or a tutor-approved substitute and limitation is recorded. |
| 4. Refactor and NFR | Layering, module size, performance, accessibility | No lint/type errors; performance targets and test data are documented; usability checklist has no unresolved critical issue. |
| 5. Submission evidence | Guides, PDF manual, clean ZIP | A separate tester follows only the submitted manual and completes the scenario from a clean machine/check-out. |

## 8. Final verification checklist

- Backend tests, frontend tests, lint, type checking, coverage gates, and production build all pass.
- Compose config passes; all three containers become healthy; backend, frontend, OpenAPI, and SPA routes return expected HTTP results.
- Security regressions cover password verification/migration, registration privilege, SSRF including redirects/DNS resolution, token staleness, and cross-tenant reads/writes.
- At least one REST and one SOAP happy path plus representative invalid inputs are demonstrated.
- The ecosystem end-to-end scenario and all original acceptance criteria have traceable evidence.
- The README links to the test report, user guide, architecture, OpenAPI, limitations, and installation manual.
- The final ZIP is created from the intended commit, checked for required/forbidden entries, under 200 MB or handled per the Moodle exception, and submitted with the PDF installation manual.
