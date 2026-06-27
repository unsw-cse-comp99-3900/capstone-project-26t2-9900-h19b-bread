# Backend API Contract for Frontend Integration

## Base URL

Local backend URL:

```text
http://127.0.0.1:8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

---

## 1. Login API

### Endpoint

```http
POST /api/v1/auth/login
```

### Description

This endpoint provides mock authentication for Sprint 1 frontend integration.  
After a successful login, the backend returns a mock token. The frontend can store this token and use it to simulate authenticated access.

### Request Body

```json
{
  "email": "publisher@example.com",
  "password": "password123"
}
```

### Success Response

```json
{
  "status": "success",
  "token": "mock-token-publisher-user-001",
  "user": {
    "user_id": "user_001",
    "email": "publisher@example.com",
    "role": "publisher",
    "enterprise_id": "ent_001"
  },
  "message": "Login successful."
}
```

### Failed Response

```json
{
  "status": "fail",
  "token": null,
  "user": null,
  "message": "Invalid email or password."
}
```

### Frontend Logic

- If `status` is `"success"`, store `token` in local storage or frontend state.
- If `status` is `"success"`, redirect the user to the dashboard or upload page.
- If `status` is `"fail"`, display the error message to the user.
- For Sprint 1 testing, use:

```text
email: publisher@example.com
password: password123
```

### Example Frontend Token Handling

```js
localStorage.setItem("token", response.token);
```

For later API requests, the frontend may include:

```http
Authorization: Bearer mock-token-publisher-user-001
```

> Note: This is a mock token for Sprint 1 frontend-backend integration, not a full JWT implementation.

---

## 2. API Submission Endpoint

### Endpoint

```http
POST /api/v1/submissions
```

### Description

This endpoint receives API metadata and uploaded specification content from the frontend.  
It internally connects with the FR-4 + FR-7 validation logic and returns the validation result to the frontend.

### Request Body

```json
{
  "api_name": "Invoice Creation API",
  "endpoint_url": "https://example.com/api/invoices",
  "protocol": "REST",
  "input_format": "JSON",
  "output_format": "JSON",
  "auth_method": "OAuth2",
  "description": "Creates electronic invoices",
  "capability_category": "invoice creation",
  "spec_content": "<uploaded file raw content>"
}
```

### Field Explanation

| Field | Description |
|---|---|
| `api_name` | Name of the API. |
| `endpoint_url` | API endpoint URL. |
| `protocol` | API protocol. Expected value: `REST` or `SOAP`. |
| `input_format` | Input data format, such as `JSON` or `XML`. |
| `output_format` | Output data format, such as `JSON` or `XML`. |
| `auth_method` | Authentication method, such as `OAuth2`, `API Key`, `Basic`, or `mTLS`. |
| `description` | Brief functional description of the API. |
| `capability_category` | E-invoicing capability, such as `invoice creation`, `validation`, `transmission`, or `archiving`. |
| `spec_content` | Full raw text content of the uploaded OpenAPI/WSDL file. |

### Success / Validated Response

```json
{
  "submission_id": "sub_001",
  "status": "validated",
  "validation": {
    "overall_status": "pass",
    "stages": [
      {
        "stage": "specification_validation",
        "status": "pass"
      }
    ],
    "errors": []
  }
}
```

### Failed / Rejected Response

```json
{
  "submission_id": "sub_001",
  "status": "rejected",
  "validation": {
    "overall_status": "fail",
    "stages": [
      {
        "stage": "specification_validation",
        "status": "fail"
      }
    ],
    "errors": [
      {
        "code": "...",
        "message": "...",
        "path": "...",
        "severity": "error"
      }
    ]
  }
}
```

### Frontend Logic

- The frontend should read the uploaded file content as raw text.
- Send the metadata and `spec_content` together to `POST /api/v1/submissions`.
- If `status` is `"validated"` or `validation.overall_status` is `"pass"`, allow the user to continue.
- If `status` is `"rejected"` or `validation.overall_status` is `"fail"`, display `validation.errors` to the user.
- Validation failure still returns HTTP 200, so the frontend should check `status` or `validation.overall_status`, not only the HTTP status code.

---

## 3. Validation API Used Internally

### Endpoint

```http
POST /api/v1/validation/spec
```

### Description

This endpoint is implemented by the validation module for FR-4 + FR-7.  
The submission endpoint uses this validation logic to determine whether the uploaded API specification is valid.

### Request Body

```json
{
  "protocol": "REST",
  "spec_content": "<uploaded file raw content>"
}
```

### Response

```json
{
  "overall_status": "pass",
  "stages": [
    {
      "stage": "specification_validation",
      "status": "pass"
    }
  ],
  "errors": []
}
```

### Validation Rules

- Request format error: HTTP 422.
- Invalid specification: HTTP 200 + `overall_status: "fail"`.
- Valid specification: HTTP 200 + `overall_status: "pass"`.

---

## 4. Notes for Frontend Team

- Main frontend integration endpoints are:

```text
POST /api/v1/auth/login
POST /api/v1/submissions
```

- Login now returns a `token` field.
- The token is currently a mock token for Sprint 1.
- The frontend can store the token and attach it to later requests as a simulated Bearer token.
- The submission endpoint handles metadata plus uploaded file content.
- The submission endpoint returns validation feedback from the FR-4 + FR-7 validation logic.
