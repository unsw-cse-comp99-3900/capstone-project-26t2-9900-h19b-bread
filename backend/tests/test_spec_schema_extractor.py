from app.services.schema_mapping.spec_schema_extractor import (
    extract_payload_schemas,
    flatten_schema_fields,
)


def test_extract_openapi_request_and_response_schemas():
    spec = """
openapi: 3.0.3
info:
  title: Invoice API
  version: 1.0.0
paths:
  /invoices:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/InvoiceRequest'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/InvoiceResponse'
components:
  schemas:
    InvoiceRequest:
      type: object
      required: [invoiceNumber, totalAmount]
      properties:
        invoiceNumber:
          type: string
        totalAmount:
          type: number
    InvoiceResponse:
      type: object
      properties:
        submissionId:
          type: string
"""

    schemas = extract_payload_schemas(
        spec_type="OPENAPI",
        spec_content=spec,
        input_format="JSON",
        output_format="JSON",
    )

    assert [schema["direction"] for schema in schemas] == ["INPUT", "OUTPUT"]
    assert schemas[0]["source_key"] == "openapi|input|post|/invoices|application/json"
    assert schemas[0]["source_path"] == "/invoices"
    assert schemas[0]["source_method"] == "POST"
    assert schemas[0]["media_type"] == "application/json"
    assert schemas[1]["source_key"] == "openapi|output|post|/invoices|application/json|201"
    assert schemas[1]["status_code"] == "201"
    assert schemas[0]["schema"]["properties"]["invoiceNumber"]["type"] == "string"
    assert schemas[1]["schema"]["properties"]["submissionId"]["type"] == "string"


def test_extract_swagger_body_and_response_schemas():
    spec = """
swagger: '2.0'
info:
  title: Invoice API
  version: 1.0.0
paths:
  /invoices:
    post:
      parameters:
        - in: body
          name: invoice
          schema:
            $ref: '#/definitions/InvoiceRequest'
      responses:
        '200':
          description: OK
          schema:
            allOf:
              - $ref: '#/definitions/BaseResponse'
              - type: object
                properties:
                  submissionId:
                    type: string
definitions:
  InvoiceRequest:
    type: object
    required: [invoiceNumber]
    properties:
      invoiceNumber:
        type: string
  BaseResponse:
    type: object
    properties:
      status:
        type: string
"""

    schemas = extract_payload_schemas(
        spec_type="SWAGGER",
        spec_content=spec,
        input_format="JSON",
        output_format="JSON",
    )

    assert [schema["direction"] for schema in schemas] == ["INPUT", "OUTPUT"]
    assert schemas[0]["schema"]["properties"]["invoiceNumber"]["type"] == "string"
    assert schemas[1]["schema"]["properties"]["status"]["type"] == "string"
    assert schemas[1]["schema"]["properties"]["submissionId"]["type"] == "string"


def test_extract_swagger_parameter_schema_when_no_body_schema():
    spec = """
swagger: '2.0'
info:
  title: Search API
  version: 1.0.0
paths:
  /invoices:
    get:
      parameters:
        - in: query
          name: invoiceNumber
          type: string
          required: true
      responses:
        '200':
          description: OK
          schema:
            type: object
            properties:
              found:
                type: boolean
"""

    schemas = extract_payload_schemas(
        spec_type="OPENAPI",
        spec_content=spec,
        input_format="JSON",
        output_format="JSON",
    )

    assert [schema["direction"] for schema in schemas] == ["INPUT", "OUTPUT"]
    assert schemas[0]["schema"]["properties"]["invoiceNumber"]["type"] == "string"
    assert schemas[0]["schema"]["required"] == ["invoiceNumber"]
    assert schemas[1]["schema"]["properties"]["found"]["type"] == "boolean"


def test_extract_openapi_keeps_distinct_operations_media_types_and_status_codes():
    spec = """
openapi: 3.0.3
info:
  title: Multi Payload API
  version: 1.0.0
paths:
  /invoices:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                invoiceNumber:
                  type: string
          application/xml:
            schema:
              type: object
              properties:
                Invoice:
                  type: string
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  accepted:
                    type: boolean
        '202':
          description: Accepted
          content:
            application/json:
              schema:
                type: object
                properties:
                  jobId:
                    type: string
  /credit-notes:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                creditNoteNumber:
                  type: string
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                type: object
                properties:
                  creditNoteId:
                    type: string
"""

    schemas = extract_payload_schemas(
        spec_type="OPENAPI",
        spec_content=spec,
        input_format="JSON",
        output_format="JSON",
    )

    assert [schema["source_key"] for schema in schemas] == [
        "openapi|input|post|/invoices|application/json",
        "openapi|input|post|/invoices|application/xml",
        "openapi|input|post|/credit-notes|application/json",
        "openapi|output|post|/invoices|application/json|200",
        "openapi|output|post|/invoices|application/json|202",
        "openapi|output|post|/credit-notes|application/json|201",
    ]
    assert schemas[1]["format"] == "XML"
    assert schemas[2]["schema"]["properties"]["creditNoteNumber"]["type"] == "string"
    assert schemas[4]["status_code"] == "202"
    assert schemas[4]["schema"]["properties"]["jobId"]["type"] == "string"


def test_extract_wsdl_request_and_response_schemas():
    spec = """<?xml version="1.0"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:xsd="http://www.w3.org/2001/XMLSchema"
             xmlns:tns="https://example.test">
  <types>
    <xsd:schema targetNamespace="https://example.test">
      <xsd:element name="SubmitInvoiceRequest">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="invoiceNumber" type="xsd:string"/>
            <xsd:element name="totalAmount" type="xsd:decimal"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
      <xsd:element name="SubmitInvoiceResponse">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="submissionId" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
    </xsd:schema>
  </types>
</definitions>
"""

    schemas = extract_payload_schemas(
        spec_type="WSDL",
        spec_content=spec,
        input_format="XML",
        output_format="XML",
    )

    assert [schema["direction"] for schema in schemas] == ["INPUT", "OUTPUT"]
    request_schema = schemas[0]["schema"]["properties"]["SubmitInvoiceRequest"]
    assert request_schema["properties"]["invoiceNumber"]["type"] == "string"
    assert request_schema["properties"]["totalAmount"]["type"] == "number"


def test_flatten_schema_fields_records_nested_paths():
    schema = {
        "type": "object",
        "required": ["Invoice"],
        "properties": {
            "Invoice": {
                "type": "object",
                "required": ["ID"],
                "properties": {"ID": {"type": "string"}},
            }
        },
    }

    fields = flatten_schema_fields(schema)

    assert fields == [
        {
            "field_path": "Invoice",
            "field_name": "Invoice",
            "field_type": "object",
            "is_required": True,
            "nesting_depth": 1,
            "parent_path": None,
        },
        {
            "field_path": "Invoice/ID",
            "field_name": "ID",
            "field_type": "string",
            "is_required": True,
            "nesting_depth": 2,
            "parent_path": "Invoice",
        },
    ]