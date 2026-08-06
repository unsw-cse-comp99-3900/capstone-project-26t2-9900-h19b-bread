import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Input,
  Row,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
  Select,
} from "antd";
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import PublisherLayout from "../../components/PublisherLayout";
import {
  buildMatrix,
  compareApiSchemas,
  compareSchemas,
  inferJsonSchema,
  listApiSchemas,
  transformApiPreview,
  transformPreview,
  type ApiSchemaCompareResponse,
  type ApiSchemaSummary,
  type ApiSchemaTransformPreviewResponse,
  type SchemaCompareResponse,
  type TransformPreviewResponse,
} from "../../services/schemaMapping";
import {
  validateConnection,
  type ConnectionValidationResult,
  type ConnectionValidationStageStatus,
} from "../../services/connectionValidation";
import "./SchemaMapping.scss";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

function parseJsonObject(raw: string, label: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) throw new Error(`${label} is empty.`);
  const parsed: unknown = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const compatColor = (level: string): string => {
  const v = level.toLowerCase();
  if (v.includes("incompat")) return "error";
  if (v.includes("partial") || v.includes("mapping")) return "warning";
  if (v.includes("full") || v.includes("compatible")) return "success";
  return "default";
};

const validationCompatColor = (level: string): string => {
  if (level === "INCOMPATIBLE") return "error";
  if (level === "NOT_ASSESSABLE") return "default";
  if (level === "COMPATIBLE_WITH_MAPPING") return "warning";
  return "success";
};

const stageColor = (status: ConnectionValidationStageStatus): string => {
  if (status === "PASSED") return "success";
  if (status === "FAILED") return "error";
  if (status === "MISSING_INFORMATION") return "warning";
  if (status === "RUNNING") return "processing";
  return "default";
};

const hasDirection = (direction: string, expected: "INPUT" | "OUTPUT") =>
  direction.toUpperCase() === expected;

const TECHNICAL_ENDPOINT_SEGMENTS = new Set([
  "auth",
  "callback",
  "callbacks",
  "connectivity",
  "count",
  "counts",
  "health",
  "healthcheck",
  "login",
  "logout",
  "metrics",
  "oauth",
  "oauth2",
  "openapi",
  "ping",
  "setting",
  "settings",
  "status",
  "swagger",
  "token",
  "tokens",
  "tool",
  "tools",
  "version",
  "versions",
  "webhook",
  "webhooks",
  "web_hooks",
]);

const isTechnicalEndpointSchema = (schema: ApiSchemaSummary) => {
  const endpoint = schema.source_path ?? schema.source_key;
  const pathSegments = endpoint.toLowerCase().match(/[a-z0-9_]+/g) ?? [];
  return pathSegments.some((segment) => TECHNICAL_ENDPOINT_SEGMENTS.has(segment));
};

const SchemaMappingPage: React.FC = () => {
  const navigate = useNavigate();
  const { id: apiId } = useParams<{ id?: string }>();

  const [sourceName, setSourceName] = useState("Source");
  const [targetName, setTargetName] = useState("Target");
  const [sourceText, setSourceText] = useState(
    '{\n  "type": "object",\n  "properties": {\n    "invoiceId": { "type": "string" },\n    "total": { "type": "number" }\n  },\n  "required": ["invoiceId"]\n}',
  );
  const [targetText, setTargetText] = useState(
    '{\n  "type": "object",\n  "properties": {\n    "id": { "type": "string" },\n    "amount": { "type": "number" }\n  },\n  "required": ["id", "amount"]\n}',
  );
  const [sampleText, setSampleText] = useState(
    '{\n  "invoiceId": "INV-001",\n  "total": 120.5\n}',
  );
  const [matrixText, setMatrixText] = useState(
    '[\n  { "name": "A", "schema": { "type": "object", "properties": { "a": { "type": "string" } } } },\n  { "name": "B", "schema": { "type": "object", "properties": { "a": { "type": "string" }, "b": { "type": "number" } } } }\n]',
  );

  const [comparing, setComparing] = useState(false);
  const [transforming, setTransforming] = useState(false);
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [dbLoading, setDbLoading] = useState(false);
  const [dbComparing, setDbComparing] = useState(false);
  const [dbTransforming, setDbTransforming] = useState(false);
  const [comparison, setComparison] = useState<SchemaCompareResponse | null>(
    null,
  );
  const [transform, setTransform] = useState<TransformPreviewResponse | null>(
    null,
  );
  const [matrix, setMatrix] = useState<Array<
    Array<Record<string, unknown>>
  > | null>(null);
  const [outputFormat, setOutputFormat] = useState<"json" | "xml">("json");
  const [apiSchemas, setApiSchemas] = useState<ApiSchemaSummary[]>([]);
  const [sourceSchemaId, setSourceSchemaId] = useState<number | null>(null);
  const [targetSchemaId, setTargetSchemaId] = useState<number | null>(null);
  const [dbComparison, setDbComparison] =
    useState<ApiSchemaCompareResponse | null>(null);
  const [dbTransform, setDbTransform] =
    useState<ApiSchemaTransformPreviewResponse | null>(null);
  const [dbSampleText, setDbSampleText] = useState(
    '{\n  "Invoice": {\n    "ID": "INV-001",\n    "IssueDate": "2026-07-22",\n    "PayableAmount": 120.5\n  }\n}',
  );
  const [dbOutputFormat, setDbOutputFormat] = useState<"json" | "xml">("json");
  const [validationSourceSchemaId, setValidationSourceSchemaId] = useState<number | null>(null);
  const [validationTargetSchemaId, setValidationTargetSchemaId] = useState<number | null>(null);
  const [validationSampleText, setValidationSampleText] = useState("");
  const [validationLoading, setValidationLoading] = useState(false);
  const [validationResult, setValidationResult] = useState<ConnectionValidationResult | null>(null);

  const loadDbSchemas = async () => {
    setDbLoading(true);
    try {
      const schemas = await listApiSchemas();
      setApiSchemas(schemas);
      const businessSchemas = schemas.filter((schema) => !isTechnicalEndpointSchema(schema));
      const outputSchema = businessSchemas.find((schema) => hasDirection(schema.direction, "OUTPUT"));
      const inputSchema = businessSchemas.find((schema) => hasDirection(schema.direction, "INPUT"));
      const currentSource = businessSchemas.find((schema) => schema.schema_id === sourceSchemaId);
      const currentTarget = businessSchemas.find((schema) => schema.schema_id === targetSchemaId);
      const currentValidationSource = businessSchemas.find((schema) => schema.schema_id === validationSourceSchemaId);
      const currentValidationTarget = businessSchemas.find((schema) => schema.schema_id === validationTargetSchemaId);
      if (!currentSource) {
        setSourceSchemaId(businessSchemas[0]?.schema_id ?? null);
      }
      if (!currentTarget) {
        setTargetSchemaId(businessSchemas[1]?.schema_id ?? null);
      }
      if (outputSchema && (!currentValidationSource || !hasDirection(currentValidationSource.direction, "OUTPUT"))) {
        setValidationSourceSchemaId(outputSchema.schema_id);
      } else if (!outputSchema) {
        setValidationSourceSchemaId(null);
      }
      if (inputSchema && (!currentValidationTarget || !hasDirection(currentValidationTarget.direction, "INPUT"))) {
        setValidationTargetSchemaId(inputSchema.schema_id);
      } else if (!inputSchema) {
        setValidationTargetSchemaId(null);
      }
    } finally {
      setDbLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDbSchemas();
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const issueRows = useMemo(() => {
    if (!comparison?.issues) return [];
    return comparison.issues.map((issue, index) => ({
      key: String(index),
      type: String(issue.code ?? issue.type ?? issue.issue_type ?? "issue"),
      path: String(
        issue.source_path && issue.target_path
          ? `${issue.source_path} → ${issue.target_path}`
          : (issue.path ?? issue.field ?? "—"),
      ),
      message: String(issue.message ?? issue.detail ?? JSON.stringify(issue)),
    }));
  }, [comparison]);

  const dbIssueRows = useMemo(() => {
    const issues = dbComparison?.comparison.issues;
    if (!issues) return [];
    return issues.map((issue, index) => ({
      key: String(index),
      type: String(issue.code ?? issue.type ?? "issue"),
      path: String(
        issue.source_path && issue.target_path
          ? `${issue.source_path} → ${issue.target_path}`
          : (issue.path ?? "—"),
      ),
      message: String(issue.message ?? JSON.stringify(issue)),
    }));
  }, [dbComparison]);

  const businessSchemas = useMemo(
    () => apiSchemas.filter((schema) => !isTechnicalEndpointSchema(schema)),
    [apiSchemas],
  );

  const schemaOptions = useMemo(
    () =>
      businessSchemas.map((schema) => {
        const operation = [schema.source_method, schema.source_path]
          .filter(Boolean)
          .join(" ");
        const response = schema.status_code ? ` ${schema.status_code}` : "";
        const source = operation || schema.source_path || schema.source_key;
        const media = schema.media_type || schema.format;
        return {
          value: schema.schema_id,
          label: `${schema.api_name} · ${schema.direction}${response} ${media} · ${source} · ${schema.version_number} (#${schema.schema_id})`,
        };
      }),
    [businessSchemas],
  );

  const sourceSchemaOptions = useMemo(
    () => schemaOptions.filter((option) => hasDirection(businessSchemas.find((schema) => schema.schema_id === option.value)?.direction ?? "", "OUTPUT")),
    [businessSchemas, schemaOptions],
  );
  const targetSchemaOptions = useMemo(
    () => schemaOptions.filter((option) => hasDirection(businessSchemas.find((schema) => schema.schema_id === option.value)?.direction ?? "", "INPUT")),
    [businessSchemas, schemaOptions],
  );

  const validationSourceSchema = useMemo(
    () => apiSchemas.find((schema) => schema.schema_id === validationSourceSchemaId) ?? null,
    [apiSchemas, validationSourceSchemaId],
  );
  const validationTargetSchema = useMemo(
    () => apiSchemas.find((schema) => schema.schema_id === validationTargetSchemaId) ?? null,
    [apiSchemas, validationTargetSchemaId],
  );

  const handleInferSourceFromSample = async () => {
    try {
      const data = JSON.parse(sampleText);
      const res = await inferJsonSchema(data);
      const schema =
        (res as { schema?: Record<string, unknown> }).schema ??
        (res as unknown as Record<string, unknown>);
      setSourceText(JSON.stringify(schema, null, 2));
      message.success("Source schema inferred from sample JSON.");
    } catch {
      // interceptor / parse error
    }
  };

  const handleCompare = async () => {
    setComparing(true);
    setComparison(null);
    try {
      const source_schema = parseJsonObject(sourceText, "Source schema");
      const target_schema = parseJsonObject(targetText, "Target schema");
      const res = await compareSchemas({
        source_schema,
        target_schema,
        source_name: sourceName,
        target_name: targetName,
      });
      setComparison(res);
      message.success("Comparison completed.");
    } catch (err) {
      if (err instanceof Error && err.message.includes("schema")) {
        message.error(err.message);
      }
    } finally {
      setComparing(false);
    }
  };

  const handleTransform = async () => {
    setTransforming(true);
    setTransform(null);
    try {
      const source_schema = parseJsonObject(sourceText, "Source schema");
      const target_schema = parseJsonObject(targetText, "Target schema");
      const data = parseJsonObject(sampleText, "Sample data");
      const res = await transformPreview({
        source_schema,
        target_schema,
        data,
        format: outputFormat,
        source_name: sourceName,
        target_name: targetName,
      });
      setTransform(res);
      message.success("Transform preview ready.");
    } catch (err) {
      if (err instanceof Error && err.message.includes("empty")) {
        message.error(err.message);
      }
    } finally {
      setTransforming(false);
    }
  };

  const handleMatrix = async () => {
    setMatrixLoading(true);
    setMatrix(null);
    try {
      const parsed = JSON.parse(matrixText) as Array<{
        name: string;
        schema: Record<string, unknown>;
      }>;
      if (!Array.isArray(parsed) || parsed.length < 1) {
        throw new Error("Matrix input must be a non-empty array.");
      }
      const res = await buildMatrix(parsed);
      setMatrix(res.matrix);
      message.success("Compatibility matrix built.");
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "Invalid matrix input.",
      );
    } finally {
      setMatrixLoading(false);
    }
  };

  const handleDbCompare = async () => {
    if (sourceSchemaId == null || targetSchemaId == null) {
      message.error("Select both source and target schemas.");
      return;
    }
    setDbComparing(true);
    setDbComparison(null);
    setDbTransform(null);
    try {
      const res = await compareApiSchemas({
        source_schema_id: sourceSchemaId,
        target_schema_id: targetSchemaId,
        save_mapping: true,
      });
      setDbComparison(res);
      message.success(`Saved mapping #${res.mapping_id}.`);
    } finally {
      setDbComparing(false);
    }
  };

  const handleDbTransform = async () => {
    const mappingId = dbComparison?.mapping_id;
    if (!mappingId) {
      message.error("Run Compare & save first.");
      return;
    }
    setDbTransforming(true);
    setDbTransform(null);
    try {
      const data = parseJsonObject(dbSampleText, "Sample data");
      const res = await transformApiPreview({
        mapping_id: mappingId,
        data,
        format: dbOutputFormat,
        save_run: true,
      });
      setDbTransform(res);
      message.success(`Transform run #${res.transform_run_id} saved.`);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    } finally {
      setDbTransforming(false);
    }
  };

  const handleValidateConnection = async () => {
    if (!validationSourceSchema || !validationTargetSchema) {
      message.error("Select a published OUTPUT source and INPUT target schema.");
      return;
    }
    if (validationSourceSchema.version_id === validationTargetSchema.version_id) {
      message.error("Source and target must be different API versions.");
      return;
    }
    setValidationLoading(true);
    setValidationResult(null);
    try {
      const sample_data = validationSampleText.trim()
        ? parseJsonObject(validationSampleText, "Sample data")
        : undefined;
      const result = await validateConnection({
        source_api_id: validationSourceSchema.api_id,
        source_version_id: validationSourceSchema.version_id,
        target_api_id: validationTargetSchema.api_id,
        target_version_id: validationTargetSchema.version_id,
        source_schema_id: validationSourceSchema.schema_id,
        target_schema_id: validationTargetSchema.schema_id,
        sample_data,
      });
      setValidationResult(result);
      if (result.activation_allowed) {
        message.success("Connection validation passed. Connection can be activated.");
      } else {
        message.warning("Connection cannot be activated. Review the validation results.");
      }
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    } finally {
      setValidationLoading(false);
    }
  };

  return (
    <PublisherLayout>
      <div className="smp-page">
        <div className="smp-toolbar">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(apiId ? `/apis/${apiId}` : "/homepage")}
          >
            {apiId ? "Back to API Detail" : "Back to Dashboard"}
          </Button>
          {apiId && <Tag color="blue">API #{apiId}</Tag>}
        </div>

        <Card className="smp-hero" bordered={false}>
          <Space align="start" size={12}>
            <SwapOutlined
              style={{ fontSize: 22, color: "#1a6fd4", marginTop: 4 }}
            />
            <div>
              <Title level={3} style={{ margin: 0 }}>
                Schema Mapping
              </Title>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                Compare schemas, preview transforms, and check multi-schema
                compatibility. Paste JSON Schema objects below (or infer source
                schema from sample data).
              </Paragraph>
            </div>
          </Space>
        </Card>

        <Tabs
          items={[
            {
              key: "connection-validation",
              label: "Connection Validation",
              children: (
                <div className="smp-panel">
                  <Alert
                    showIcon
                    type="info"
                    message="Validate before connecting"
                    description="Only published OUTPUT schemas can be sources and published INPUT schemas can be targets. A connection remains disabled unless the validation result allows activation."
                  />
                  <Card title="Connection contract" className="smp-card" bordered={false}>
                    <Row gutter={[12, 12]}>
                      <Col xs={24} lg={12}>
                        <Text type="secondary">Source API version (OUTPUT)</Text>
                        <Select
                          value={validationSourceSchemaId ?? undefined}
                          onChange={setValidationSourceSchemaId}
                          options={sourceSchemaOptions}
                          loading={dbLoading}
                          placeholder="Choose a source output"
                          style={{ width: "100%", marginTop: 6 }}
                        />
                      </Col>
                      <Col xs={24} lg={12}>
                        <Text type="secondary">Target API version (INPUT)</Text>
                        <Select
                          value={validationTargetSchemaId ?? undefined}
                          onChange={setValidationTargetSchemaId}
                          options={targetSchemaOptions}
                          loading={dbLoading}
                          placeholder="Choose a target input"
                          style={{ width: "100%", marginTop: 6 }}
                        />
                      </Col>
                    </Row>
                    <Text type="secondary" style={{ display: "block", marginTop: 16 }}>
                      Sample source payload (optional)
                    </Text>
                    <TextArea
                      rows={8}
                      value={validationSampleText}
                      onChange={(e) => setValidationSampleText(e.target.value)}
                      className="smp-code"
                      style={{ marginTop: 6 }}
                    />
                    <Space wrap style={{ marginTop: 12 }}>
                      <Button loading={dbLoading} onClick={() => void loadDbSchemas()}>
                        Reload schemas
                      </Button>
                      <Button
                        type="primary"
                        loading={validationLoading}
                        onClick={() => void handleValidateConnection()}
                      >
                        Validate connection
                      </Button>
                    </Space>
                  </Card>

                  {validationResult && (
                    <Card title="Validation result" className="smp-card" bordered={false}>
                      <Space wrap style={{ marginBottom: 12 }}>
                        <Tag color={validationCompatColor(validationResult.compatibility_level)}>
                          {validationResult.compatibility_level}
                        </Tag>
                        <Tag color={validationResult.activation_allowed ? "success" : "error"}>
                          {validationResult.activation_allowed ? "Connection enabled" : "Connection blocked"}
                        </Tag>
                        <Tag>run #{validationResult.connection_validation_run_id}</Tag>
                      </Space>
                      <Alert
                        showIcon
                        type={validationResult.activation_allowed ? "success" : "warning"}
                        message={validationResult.reason}
                        description={`Reason code: ${validationResult.reason_code}`}
                      />
                      <Title level={5} style={{ marginTop: 18 }}>Validation stages</Title>
                      <div className="smp-stages">
                        {validationResult.stages.map((stage) => (
                          <div className="smp-stage" key={stage.stage}>
                            <Tag color={stageColor(stage.status)}>{stage.status}</Tag>
                            <div>
                              <Text strong>{stage.stage}</Text>
                              <div><Text type="secondary">{stage.message}</Text></div>
                            </div>
                          </div>
                        ))}
                      </div>
                      <Title level={5} style={{ marginTop: 18 }}>Issues</Title>
                      <Table
                        size="small"
                        pagination={false}
                        dataSource={validationResult.reasons.map((reason, index) => ({ ...reason, key: index }))}
                        columns={[
                          { title: "Severity", dataIndex: "severity", width: 110, render: (severity: string) => <Tag color={severity === "ERROR" ? "error" : severity === "WARNING" ? "warning" : "blue"}>{severity}</Tag> },
                          { title: "Stage", dataIndex: "stage", width: 160 },
                          { title: "Path", width: 200, render: (_, row: { source_path: string | null; target_path: string | null }) => row.source_path || row.target_path ? `${row.source_path ?? "—"} → ${row.target_path ?? "—"}` : "—" },
                          { title: "Message", dataIndex: "message" },
                        ]}
                        locale={{ emptyText: "No validation issues reported." }}
                      />
                      <Collapse
                        style={{ marginTop: 16 }}
                        items={[{
                          key: "business-rules",
                          label: "Business rules diagnostics (informational)",
                          children: <pre className="smp-pre">{JSON.stringify(validationResult.business_rules_diagnostics, null, 2)}</pre>,
                        }]}
                      />
                    </Card>
                  )}

                </div>
              ),
            },
            {
              key: "database",
              label: "Database Flow",
              children: (
                <div className="smp-panel">
                  <Card
                    title="Saved API schemas"
                    className="smp-card"
                    bordered={false}
                    size="small"
                  >
                    <Row gutter={[12, 12]}>
                      <Col xs={24} lg={12}>
                        <Text type="secondary">Source schema</Text>
                        <Select
                          value={sourceSchemaId ?? undefined}
                          onChange={setSourceSchemaId}
                          options={schemaOptions}
                          loading={dbLoading}
                          style={{ width: "100%", marginTop: 6 }}
                        />
                      </Col>
                      <Col xs={24} lg={12}>
                        <Text type="secondary">Target schema</Text>
                        <Select
                          value={targetSchemaId ?? undefined}
                          onChange={setTargetSchemaId}
                          options={schemaOptions}
                          loading={dbLoading}
                          style={{ width: "100%", marginTop: 6 }}
                        />
                      </Col>
                    </Row>
                    <Space wrap style={{ marginTop: 14 }}>
                      <Button
                        loading={dbLoading}
                        onClick={() => void loadDbSchemas()}
                      >
                        Reload schemas
                      </Button>
                      <Button
                        type="primary"
                        loading={dbComparing}
                        onClick={() => void handleDbCompare()}
                      >
                        Compare & save mapping
                      </Button>
                    </Space>
                  </Card>

                  {dbComparison && (
                    <Card
                      title="Saved comparison"
                      className="smp-card"
                      bordered={false}
                    >
                      <Space wrap style={{ marginBottom: 12 }}>
                        <Text>{dbComparison.source_schema.api_name}</Text>
                        <Text type="secondary">→</Text>
                        <Text>{dbComparison.target_schema.api_name}</Text>
                        <Tag
                          color={compatColor(
                            dbComparison.comparison.compatibility,
                          )}
                        >
                          {dbComparison.comparison.compatibility}
                        </Tag>
                        <Tag>result #{dbComparison.comparison_result_id}</Tag>
                        <Tag>mapping #{dbComparison.mapping_id}</Tag>
                      </Space>
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 12 }}
                        message="Summary"
                        description={
                          <pre className="smp-pre">
                            {JSON.stringify(
                              dbComparison.comparison.summary,
                              null,
                              2,
                            )}
                          </pre>
                        }
                      />
                      <Title level={5}>Mapping rules</Title>
                      <pre className="smp-pre">
                        {JSON.stringify(dbComparison.mapping, null, 2)}
                      </pre>
                      <Title level={5}>Issues</Title>
                      <Table
                        size="small"
                        pagination={false}
                        dataSource={dbIssueRows}
                        columns={[
                          { title: "Type", dataIndex: "type", width: 180 },
                          { title: "Path", dataIndex: "path", width: 240 },
                          { title: "Message", dataIndex: "message" },
                        ]}
                        locale={{ emptyText: "No issues reported." }}
                      />
                    </Card>
                  )}

                  <Card
                    title="Transform run"
                    className="smp-card"
                    bordered={false}
                    size="small"
                    extra={
                      <Select
                        size="small"
                        value={dbOutputFormat}
                        onChange={setDbOutputFormat}
                        options={[
                          { value: "json", label: "JSON out" },
                          { value: "xml", label: "XML out" },
                        ]}
                        style={{ width: 110 }}
                      />
                    }
                  >
                    <TextArea
                      rows={8}
                      value={dbSampleText}
                      onChange={(e) => setDbSampleText(e.target.value)}
                      className="smp-code"
                    />
                    <Button
                      style={{ marginTop: 12 }}
                      loading={dbTransforming}
                      onClick={() => void handleDbTransform()}
                    >
                      Preview & save transform run
                    </Button>
                  </Card>

                  {dbTransform && (
                    <Card
                      title="Saved transform preview"
                      className="smp-card"
                      bordered={false}
                    >
                      <Space style={{ marginBottom: 12 }} wrap>
                        <Tag>run #{dbTransform.transform_run_id}</Tag>
                        <Tag>mapping #{dbTransform.mapping_id}</Tag>
                        <Tag>{dbTransform.mapping_status}</Tag>
                        <Tag color="blue">{dbTransform.format}</Tag>
                      </Space>
                      <Title level={5}>Result</Title>
                      <pre className="smp-pre">
                        {typeof dbTransform.result === "string"
                          ? dbTransform.result
                          : JSON.stringify(dbTransform.result, null, 2)}
                      </pre>
                      <Title level={5}>Generated transform code</Title>
                      <pre className="smp-pre">
                        {dbTransform.transform_code}
                      </pre>
                    </Card>
                  )}
                </div>
              ),
            },
            {
              key: "compare",
              label: "Compare & Transform",
              children: (
                <div className="smp-panel">
                  <Row gutter={[16, 16]}>
                    <Col xs={24} lg={12}>
                      <Card
                        title="Source schema"
                        className="smp-card"
                        bordered={false}
                        size="small"
                        extra={
                          <Input
                            size="small"
                            value={sourceName}
                            onChange={(e) => setSourceName(e.target.value)}
                            style={{ width: 140 }}
                          />
                        }
                      >
                        <TextArea
                          rows={14}
                          value={sourceText}
                          onChange={(e) => setSourceText(e.target.value)}
                          className="smp-code"
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card
                        title="Target schema"
                        className="smp-card"
                        bordered={false}
                        size="small"
                        extra={
                          <Input
                            size="small"
                            value={targetName}
                            onChange={(e) => setTargetName(e.target.value)}
                            style={{ width: 140 }}
                          />
                        }
                      >
                        <TextArea
                          rows={14}
                          value={targetText}
                          onChange={(e) => setTargetText(e.target.value)}
                          className="smp-code"
                        />
                      </Card>
                    </Col>
                  </Row>

                  <Card
                    title="Sample source data"
                    className="smp-card"
                    bordered={false}
                    size="small"
                    extra={
                      <Space>
                        <Select
                          size="small"
                          value={outputFormat}
                          onChange={setOutputFormat}
                          options={[
                            { value: "json", label: "JSON out" },
                            { value: "xml", label: "XML out" },
                          ]}
                          style={{ width: 110 }}
                        />
                        <Button
                          size="small"
                          onClick={() => void handleInferSourceFromSample()}
                        >
                          Infer source schema
                        </Button>
                      </Space>
                    }
                  >
                    <TextArea
                      rows={8}
                      value={sampleText}
                      onChange={(e) => setSampleText(e.target.value)}
                      className="smp-code"
                    />
                  </Card>

                  <Space wrap>
                    <Button
                      type="primary"
                      loading={comparing}
                      onClick={() => void handleCompare()}
                    >
                      Run comparison
                    </Button>
                    <Button
                      loading={transforming}
                      onClick={() => void handleTransform()}
                    >
                      Transform preview
                    </Button>
                    {transform?.transform_code && (
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={() =>
                          downloadText("transform.py", transform.transform_code)
                        }
                      >
                        Download transform code
                      </Button>
                    )}
                  </Space>

                  {comparison && (
                    <Card
                      title="Comparison result"
                      className="smp-card"
                      bordered={false}
                    >
                      <Space style={{ marginBottom: 12 }} wrap>
                        <Text>{comparison.source}</Text>
                        <Text type="secondary">→</Text>
                        <Text>{comparison.target}</Text>
                        <Tag color={compatColor(comparison.compatibility)}>
                          {comparison.compatibility}
                        </Tag>
                      </Space>
                      {comparison.summary && (
                        <Alert
                          type="info"
                          showIcon
                          style={{ marginBottom: 12 }}
                          message="Summary"
                          description={
                            <pre className="smp-pre">
                              {JSON.stringify(comparison.summary, null, 2)}
                            </pre>
                          }
                        />
                      )}
                      <Table
                        size="small"
                        pagination={false}
                        dataSource={issueRows}
                        columns={[
                          { title: "Type", dataIndex: "type", width: 140 },
                          { title: "Path", dataIndex: "path", width: 180 },
                          { title: "Message", dataIndex: "message" },
                        ]}
                        locale={{ emptyText: "No issues reported." }}
                      />
                    </Card>
                  )}

                  {transform && (
                    <Card
                      title="Transform preview"
                      className="smp-card"
                      bordered={false}
                    >
                      <Space style={{ marginBottom: 12 }}>
                        <Tag>{transform.mapping_status}</Tag>
                        <Tag color="blue">{transform.format}</Tag>
                      </Space>
                      <Title level={5}>Result</Title>
                      <pre className="smp-pre">
                        {typeof transform.result === "string"
                          ? transform.result
                          : JSON.stringify(transform.result, null, 2)}
                      </pre>
                      <Title level={5}>Mapping</Title>
                      <pre className="smp-pre">
                        {JSON.stringify(transform.mapping, null, 2)}
                      </pre>
                    </Card>
                  )}
                </div>
              ),
            },
            {
              key: "matrix",
              label: "Compatibility Matrix",
              children: (
                <div className="smp-panel">
                  <Card
                    title="Schemas array"
                    className="smp-card"
                    bordered={false}
                    size="small"
                  >
                    <Paragraph type="secondary">
                      Provide an array of objects with <Text code>name</Text>{" "}
                      and <Text code>schema</Text>.
                    </Paragraph>
                    <TextArea
                      rows={14}
                      value={matrixText}
                      onChange={(e) => setMatrixText(e.target.value)}
                      className="smp-code"
                    />
                  </Card>
                  <Button
                    type="primary"
                    loading={matrixLoading}
                    onClick={() => void handleMatrix()}
                  >
                    Build matrix
                  </Button>
                  {matrix && (
                    <Card title="Matrix" className="smp-card" bordered={false}>
                      <pre className="smp-pre">
                        {JSON.stringify(matrix, null, 2)}
                      </pre>
                    </Card>
                  )}
                </div>
              ),
            },
          ]}
        />
      </div>
    </PublisherLayout>
  );
};

export default SchemaMappingPage;
