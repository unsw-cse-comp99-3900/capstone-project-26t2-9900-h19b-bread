import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
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

  const loadDbSchemas = async () => {
    setDbLoading(true);
    try {
      const schemas = await listApiSchemas();
      setApiSchemas(schemas);
      if (schemas.length > 0 && sourceSchemaId == null) {
        setSourceSchemaId(schemas[0].schema_id);
      }
      if (schemas.length > 1 && targetSchemaId == null) {
        setTargetSchemaId(schemas[1].schema_id);
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

  const schemaOptions = useMemo(
    () =>
      apiSchemas.map((schema) => {
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
    [apiSchemas],
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
