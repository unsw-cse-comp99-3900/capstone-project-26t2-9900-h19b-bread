import React, { useMemo, useState } from 'react';
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
} from 'antd';
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import PublisherLayout from '../../components/PublisherLayout';
import {
  buildMatrix,
  compareSchemas,
  inferJsonSchema,
  transformPreview,
  type SchemaCompareResponse,
  type TransformPreviewResponse,
} from '../../services/schemaMapping';
import './SchemaMapping.scss';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

function parseJsonObject(raw: string, label: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) throw new Error(`${label} is empty.`);
  const parsed: unknown = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const compatColor = (level: string): string => {
  const v = level.toLowerCase();
  if (v.includes('full') || v.includes('compatible')) return 'success';
  if (v.includes('partial')) return 'warning';
  if (v.includes('incompat')) return 'error';
  return 'default';
};

const SchemaMappingPage: React.FC = () => {
  const navigate = useNavigate();
  const { id: apiId } = useParams<{ id?: string }>();

  const [sourceName, setSourceName] = useState('Source');
  const [targetName, setTargetName] = useState('Target');
  const [sourceText, setSourceText] = useState('{\n  "type": "object",\n  "properties": {\n    "invoiceId": { "type": "string" },\n    "total": { "type": "number" }\n  },\n  "required": ["invoiceId"]\n}');
  const [targetText, setTargetText] = useState('{\n  "type": "object",\n  "properties": {\n    "id": { "type": "string" },\n    "amount": { "type": "number" }\n  },\n  "required": ["id", "amount"]\n}');
  const [sampleText, setSampleText] = useState('{\n  "invoiceId": "INV-001",\n  "total": 120.5\n}');
  const [matrixText, setMatrixText] = useState(
    '[\n  { "name": "A", "schema": { "type": "object", "properties": { "a": { "type": "string" } } } },\n  { "name": "B", "schema": { "type": "object", "properties": { "a": { "type": "string" }, "b": { "type": "number" } } } }\n]',
  );

  const [comparing, setComparing] = useState(false);
  const [transforming, setTransforming] = useState(false);
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [comparison, setComparison] = useState<SchemaCompareResponse | null>(null);
  const [transform, setTransform] = useState<TransformPreviewResponse | null>(null);
  const [matrix, setMatrix] = useState<Array<Array<Record<string, unknown>>> | null>(null);
  const [outputFormat, setOutputFormat] = useState<'json' | 'xml'>('json');

  const issueRows = useMemo(() => {
    if (!comparison?.issues) return [];
    return comparison.issues.map((issue, index) => ({
      key: String(index),
      type: String(issue.type ?? issue.issue_type ?? 'issue'),
      path: String(issue.path ?? issue.field ?? '—'),
      message: String(issue.message ?? issue.detail ?? JSON.stringify(issue)),
    }));
  }, [comparison]);

  const handleInferSourceFromSample = async () => {
    try {
      const data = JSON.parse(sampleText);
      const res = await inferJsonSchema(data);
      const schema = (res as { schema?: Record<string, unknown> }).schema
        ?? (res as unknown as Record<string, unknown>);
      setSourceText(JSON.stringify(schema, null, 2));
      message.success('Source schema inferred from sample JSON.');
    } catch {
      // interceptor / parse error
    }
  };

  const handleCompare = async () => {
    setComparing(true);
    setComparison(null);
    try {
      const source_schema = parseJsonObject(sourceText, 'Source schema');
      const target_schema = parseJsonObject(targetText, 'Target schema');
      const res = await compareSchemas({
        source_schema,
        target_schema,
        source_name: sourceName,
        target_name: targetName,
      });
      setComparison(res);
      message.success('Comparison completed.');
    } catch (err) {
      if (err instanceof Error && err.message.includes('schema')) {
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
      const source_schema = parseJsonObject(sourceText, 'Source schema');
      const target_schema = parseJsonObject(targetText, 'Target schema');
      const data = parseJsonObject(sampleText, 'Sample data');
      const res = await transformPreview({
        source_schema,
        target_schema,
        data,
        format: outputFormat,
        source_name: sourceName,
        target_name: targetName,
      });
      setTransform(res);
      message.success('Transform preview ready.');
    } catch (err) {
      if (err instanceof Error && err.message.includes('empty')) {
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
      const parsed = JSON.parse(matrixText) as Array<{ name: string; schema: Record<string, unknown> }>;
      if (!Array.isArray(parsed) || parsed.length < 1) {
        throw new Error('Matrix input must be a non-empty array.');
      }
      const res = await buildMatrix(parsed);
      setMatrix(res.matrix);
      message.success('Compatibility matrix built.');
    } catch (err) {
      message.error(err instanceof Error ? err.message : 'Invalid matrix input.');
    } finally {
      setMatrixLoading(false);
    }
  };

  return (
    <PublisherLayout>
      <div className="smp-page">
        <div className="smp-toolbar">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(apiId ? `/apis/${apiId}` : '/homepage')}
          >
            {apiId ? 'Back to API Detail' : 'Back to Dashboard'}
          </Button>
          {apiId && <Tag color="blue">API #{apiId}</Tag>}
        </div>

        <Card className="smp-hero" bordered={false}>
          <Space align="start" size={12}>
            <SwapOutlined style={{ fontSize: 22, color: '#1a6fd4', marginTop: 4 }} />
            <div>
              <Title level={3} style={{ margin: 0 }}>Schema Mapping</Title>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                Compare schemas, preview transforms, and check multi-schema compatibility.
                Paste JSON Schema objects below (or infer source schema from sample data).
              </Paragraph>
            </div>
          </Space>
        </Card>

        <Tabs
          items={[
            {
              key: 'compare',
              label: 'Compare & Transform',
              children: (
                <div className="smp-panel">
                  <Row gutter={[16, 16]}>
                    <Col xs={24} lg={12}>
                      <Card title="Source schema" className="smp-card" bordered={false} size="small"
                        extra={
                          <Input
                            size="small"
                            value={sourceName}
                            onChange={e => setSourceName(e.target.value)}
                            style={{ width: 140 }}
                          />
                        }
                      >
                        <TextArea
                          rows={14}
                          value={sourceText}
                          onChange={e => setSourceText(e.target.value)}
                          className="smp-code"
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card title="Target schema" className="smp-card" bordered={false} size="small"
                        extra={
                          <Input
                            size="small"
                            value={targetName}
                            onChange={e => setTargetName(e.target.value)}
                            style={{ width: 140 }}
                          />
                        }
                      >
                        <TextArea
                          rows={14}
                          value={targetText}
                          onChange={e => setTargetText(e.target.value)}
                          className="smp-code"
                        />
                      </Card>
                    </Col>
                  </Row>

                  <Card title="Sample source data" className="smp-card" bordered={false} size="small"
                    extra={
                      <Space>
                        <Select
                          size="small"
                          value={outputFormat}
                          onChange={setOutputFormat}
                          options={[
                            { value: 'json', label: 'JSON out' },
                            { value: 'xml', label: 'XML out' },
                          ]}
                          style={{ width: 110 }}
                        />
                        <Button size="small" onClick={() => void handleInferSourceFromSample()}>
                          Infer source schema
                        </Button>
                      </Space>
                    }
                  >
                    <TextArea
                      rows={8}
                      value={sampleText}
                      onChange={e => setSampleText(e.target.value)}
                      className="smp-code"
                    />
                  </Card>

                  <Space wrap>
                    <Button type="primary" loading={comparing} onClick={() => void handleCompare()}>
                      Run comparison
                    </Button>
                    <Button loading={transforming} onClick={() => void handleTransform()}>
                      Transform preview
                    </Button>
                    {transform?.transform_code && (
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={() => downloadText('transform.py', transform.transform_code)}
                      >
                        Download transform code
                      </Button>
                    )}
                  </Space>

                  {comparison && (
                    <Card title="Comparison result" className="smp-card" bordered={false}>
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
                            <pre className="smp-pre">{JSON.stringify(comparison.summary, null, 2)}</pre>
                          }
                        />
                      )}
                      <Table
                        size="small"
                        pagination={false}
                        dataSource={issueRows}
                        columns={[
                          { title: 'Type', dataIndex: 'type', width: 140 },
                          { title: 'Path', dataIndex: 'path', width: 180 },
                          { title: 'Message', dataIndex: 'message' },
                        ]}
                        locale={{ emptyText: 'No issues reported.' }}
                      />
                    </Card>
                  )}

                  {transform && (
                    <Card title="Transform preview" className="smp-card" bordered={false}>
                      <Space style={{ marginBottom: 12 }}>
                        <Tag>{transform.mapping_status}</Tag>
                        <Tag color="blue">{transform.format}</Tag>
                      </Space>
                      <Title level={5}>Result</Title>
                      <pre className="smp-pre">
                        {typeof transform.result === 'string'
                          ? transform.result
                          : JSON.stringify(transform.result, null, 2)}
                      </pre>
                      <Title level={5}>Mapping</Title>
                      <pre className="smp-pre">{JSON.stringify(transform.mapping, null, 2)}</pre>
                    </Card>
                  )}
                </div>
              ),
            },
            {
              key: 'matrix',
              label: 'Compatibility Matrix',
              children: (
                <div className="smp-panel">
                  <Card title="Schemas array" className="smp-card" bordered={false} size="small">
                    <Paragraph type="secondary">
                      Provide an array of objects with <Text code>name</Text> and <Text code>schema</Text>.
                    </Paragraph>
                    <TextArea
                      rows={14}
                      value={matrixText}
                      onChange={e => setMatrixText(e.target.value)}
                      className="smp-code"
                    />
                  </Card>
                  <Button type="primary" loading={matrixLoading} onClick={() => void handleMatrix()}>
                    Build matrix
                  </Button>
                  {matrix && (
                    <Card title="Matrix" className="smp-card" bordered={false}>
                      <pre className="smp-pre">{JSON.stringify(matrix, null, 2)}</pre>
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
