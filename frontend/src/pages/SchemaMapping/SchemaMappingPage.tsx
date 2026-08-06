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
  SwapOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import PublisherLayout from "../../components/PublisherLayout";
import {
  compareApiSchemas,
  listApiSchemas,
  transformApiPreview,
  type ApiSchemaCompareResponse,
  type ApiSchemaSummary,
  type ApiSchemaTransformPreviewResponse,
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
  const focusedApiId = apiId ? Number(apiId) : null;

  const [dbLoading, setDbLoading] = useState(false);
  const [dbComparing, setDbComparing] = useState(false);
  const [dbTransforming, setDbTransforming] = useState(false);
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

  const applySchemaDefaults = (schemas: ApiSchemaSummary[]) => {
    const focused = focusedApiId != null
      ? schemas.filter((schema) => schema.api_id === focusedApiId)
      : [];
    const pool = focused.length > 0 ? focused : schemas;

    const outputSchema =
      pool.find((schema) => hasDirection(schema.direction, "OUTPUT"))
      ?? schemas.find((schema) => hasDirection(schema.direction, "OUTPUT"));
    const inputSchema =
      schemas.find((schema) =>
        hasDirection(schema.direction, "INPUT")
        && (focusedApiId == null || schema.api_id !== focusedApiId),
      )
      ?? pool.find((schema) => hasDirection(schema.direction, "INPUT"))
      ?? schemas.find((schema) => hasDirection(schema.direction, "INPUT"));

    setSourceSchemaId((prev) => prev ?? outputSchema?.schema_id ?? pool[0]?.schema_id ?? null);
    setTargetSchemaId((prev) => {
      if (prev != null) return prev;
      const fallback = schemas.find((schema) => schema.schema_id !== (outputSchema?.schema_id ?? pool[0]?.schema_id));
      return inputSchema?.schema_id ?? fallback?.schema_id ?? null;
    });
    setValidationSourceSchemaId((prev) => prev ?? outputSchema?.schema_id ?? null);
    setValidationTargetSchemaId((prev) => prev ?? inputSchema?.schema_id ?? null);
  };

  const loadDbSchemas = async () => {
    setDbLoading(true);
    try {
      const schemas = await listApiSchemas();
      setApiSchemas(schemas);
      applySchemaDefaults(schemas);
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
  }, [focusedApiId]);

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
          label: `${schema.api_name} · ${schema.direction}${response} ${media} · ${source} · ${schema.version_number}`,
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
        message.success("Connection validation passed.");
      } else {
        message.warning("Connection cannot be activated. Review the results.");
      }
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    } finally {
      setValidationLoading(false);
    }
  };

  const summaryEntries = useMemo(() => {
    const summary = dbComparison?.comparison.summary;
    if (!summary) return [];
    return Object.entries(summary).map(([key, value]) => ({
      key,
      value: typeof value === "string" || typeof value === "number" || typeof value === "boolean"
        ? String(value)
        : JSON.stringify(value),
    }));
  }, [dbComparison]);

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
          {apiId && <Tag color="blue">Focused API #{apiId}</Tag>}
        </div>

        <Card className="smp-hero" bordered={false}>
          <Space align="start" size={12}>
            <SwapOutlined style={{ fontSize: 22, color: "#1a6fd4", marginTop: 4 }} />
            <div>
              <Title level={3} style={{ margin: 0 }}>
                Schema Mapping
              </Title>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                Validate API connections and build mappings from published schemas
                stored in the platform.
                {focusedApiId != null
                  ? " Source schemas for this API are preselected when available."
                  : ""}
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
                    description="Use a published OUTPUT schema as source and a published INPUT schema as target. Activation stays blocked until validation allows it."
                  />
                  <Card title="Connection contract" className="smp-card" bordered={false}>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Text type="secondary">Source API version (OUTPUT)</Text>
                        <Select
                          value={validationSourceSchemaId ?? undefined}
                          onChange={setValidationSourceSchemaId}
                          options={sourceSchemaOptions}
                          loading={dbLoading}
                          placeholder="Choose a source output"
                          style={{ width: "100%", marginTop: 6 }}
                          showSearch
                          optionFilterProp="label"
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
                          showSearch
                          optionFilterProp="label"
                        />
                      </Col>
                    </Row>
                    <Text type="secondary" style={{ display: "block", marginTop: 16 }}>
                      Sample source payload (optional)
                    </Text>
                    <TextArea
                      rows={6}
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
                          {
                            title: "Severity",
                            dataIndex: "severity",
                            width: 110,
                            render: (severity: string) => (
                              <Tag color={severity === "ERROR" ? "error" : severity === "WARNING" ? "warning" : "blue"}>
                                {severity}
                              </Tag>
                            ),
                          },
                          { title: "Stage", dataIndex: "stage", width: 160 },
                          {
                            title: "Path",
                            width: 200,
                            render: (_, row: { source_path: string | null; target_path: string | null }) =>
                              row.source_path || row.target_path
                                ? `${row.source_path ?? "—"} → ${row.target_path ?? "—"}`
                                : "—",
                          },
                          { title: "Message", dataIndex: "message" },
                        ]}
                        locale={{ emptyText: "No validation issues reported." }}
                      />
                      <Collapse
                        style={{ marginTop: 16 }}
                        items={[{
                          key: "business-rules",
                          label: "Business rules diagnostics",
                          children: (
                            <pre className="smp-pre">
                              {JSON.stringify(validationResult.business_rules_diagnostics, null, 2)}
                            </pre>
                          ),
                        }]}
                      />
                    </Card>
                  )}
                </div>
              ),
            },
            {
              key: "database",
              label: "Mapping & Transform",
              children: (
                <div className="smp-panel">
                  <Card title="Select schemas" className="smp-card" bordered={false}>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Text type="secondary">Source schema</Text>
                        <Select
                          value={sourceSchemaId ?? undefined}
                          onChange={setSourceSchemaId}
                          options={schemaOptions}
                          loading={dbLoading}
                          style={{ width: "100%", marginTop: 6 }}
                          showSearch
                          optionFilterProp="label"
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
                          showSearch
                          optionFilterProp="label"
                        />
                      </Col>
                    </Row>
                    <Space wrap style={{ marginTop: 14 }}>
                      <Button loading={dbLoading} onClick={() => void loadDbSchemas()}>
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
                    <Card title="Comparison result" className="smp-card" bordered={false}>
                      <Space wrap style={{ marginBottom: 12 }}>
                        <Text>{dbComparison.source_schema.api_name}</Text>
                        <Text type="secondary">→</Text>
                        <Text>{dbComparison.target_schema.api_name}</Text>
                        <Tag color={compatColor(dbComparison.comparison.compatibility)}>
                          {dbComparison.comparison.compatibility}
                        </Tag>
                        <Tag>mapping #{dbComparison.mapping_id}</Tag>
                      </Space>
                      {summaryEntries.length > 0 && (
                        <>
                          <Title level={5}>Summary</Title>
                          <Table
                            size="small"
                            pagination={false}
                            dataSource={summaryEntries}
                            columns={[
                              { title: "Metric", dataIndex: "key", width: 200 },
                              { title: "Value", dataIndex: "value" },
                            ]}
                            style={{ marginBottom: 16 }}
                          />
                        </>
                      )}
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
                      <Collapse
                        style={{ marginTop: 16 }}
                        items={[{
                          key: "mapping-rules",
                          label: "Mapping rules (raw)",
                          children: (
                            <pre className="smp-pre">
                              {JSON.stringify(dbComparison.mapping, null, 2)}
                            </pre>
                          ),
                        }]}
                      />
                    </Card>
                  )}

                  <Card
                    title="Transform preview"
                    className="smp-card"
                    bordered={false}
                    extra={
                      <Select
                        size="small"
                        value={dbOutputFormat}
                        onChange={setDbOutputFormat}
                        options={[
                          { value: "json", label: "JSON" },
                          { value: "xml", label: "XML" },
                        ]}
                        style={{ width: 100 }}
                      />
                    }
                  >
                    <Text type="secondary">Sample payload</Text>
                    <TextArea
                      rows={6}
                      value={dbSampleText}
                      onChange={(e) => setDbSampleText(e.target.value)}
                      className="smp-code"
                      style={{ marginTop: 6 }}
                    />
                    <Button
                      style={{ marginTop: 12 }}
                      type="primary"
                      loading={dbTransforming}
                      onClick={() => void handleDbTransform()}
                      disabled={!dbComparison?.mapping_id}
                    >
                      Preview & save transform
                    </Button>
                  </Card>

                  {dbTransform && (
                    <Card title="Transform result" className="smp-card" bordered={false}>
                      <Space style={{ marginBottom: 12 }} wrap>
                        <Tag>run #{dbTransform.transform_run_id}</Tag>
                        <Tag>{dbTransform.mapping_status}</Tag>
                        <Tag color="blue">{dbTransform.format}</Tag>
                      </Space>
                      <Title level={5}>Result</Title>
                      <pre className="smp-pre">
                        {typeof dbTransform.result === "string"
                          ? dbTransform.result
                          : JSON.stringify(dbTransform.result, null, 2)}
                      </pre>
                      <Collapse
                        style={{ marginTop: 16 }}
                        items={[{
                          key: "transform-code",
                          label: "Generated transform code",
                          children: (
                            <pre className="smp-pre">{dbTransform.transform_code}</pre>
                          ),
                        }]}
                      />
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
