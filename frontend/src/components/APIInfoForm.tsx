import React, { useState } from 'react';
import {
  Modal,
  Steps,
  Form,
  Input,
  Select,
  Upload,
  Button,
  Alert,
  Spin,
  Typography,
  Result,
  Radio,
  Tag,
} from 'antd';
import type { UploadFile } from 'antd';
import {
  InboxOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
  ThunderboltOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import {
  type Protocol,
  type ParsedInfo,
  type StageResult,
  type ValidationResult,
  FORMAT_OPTIONS,
  AUTH_OPTIONS,
  CATEGORY_OPTIONS,
  MOCK_URL_RESULT,
  parseOpenApiJson,
  parseWsdl,
} from '../utils/helper';

const { TextArea } = Input;
const { Text }     = Typography;
const { Option }   = Select;
const { Dragger }  = Upload;

// ── Types ──────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
}

type ImportMethod = 'upload' | 'url';

// ── Constants ──────────────────────────────────────────────────────────────

const STEP_ITEMS = [
  { title: 'Import Spec' },
  { title: 'Review & Edit' },
  { title: 'Validation' },
];

// ── Sub-components ─────────────────────────────────────────────────────────

interface FieldLabelProps { name: string; auto: boolean; }

const FieldLabel: React.FC<FieldLabelProps> = ({ name, auto }) => (
  <span>
    {name}{' '}
    {auto && (
      <Tag color="green" style={{ fontSize: 11, padding: '0 5px', lineHeight: '18px', marginLeft: 2 }}>
        Auto
      </Tag>
    )}
  </span>
);

interface StageRowProps { title: string; desc: string; stage: StageResult; }

const StageRow: React.FC<StageRowProps> = ({ title, desc, stage }) => (
  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 0', borderBottom: '1px solid #f0f0f0' }}>
    {stage.passed
      ? <CheckCircleFilled style={{ color: '#52c41a', fontSize: 18, marginTop: 2 }} />
      : <CloseCircleFilled style={{ color: '#ff4d4f', fontSize: 18, marginTop: 2 }} />}
    <div>
      <Text strong>{title}</Text>
      <br />
      <Text type="secondary" style={{ fontSize: 12 }}>{desc}</Text>
      <br />
      <Text style={{ fontSize: 12, color: stage.passed ? '#52c41a' : '#ff4d4f' }}>
        {stage.passed ? '✓ ' : '✗ '}{stage.message}
      </Text>
    </div>
  </div>
);

// ── Main component ─────────────────────────────────────────────────────────

const APIInfoForm: React.FC<Props> = ({ open, onClose }) => {
  const [form] = Form.useForm();

  const [current, setCurrent]             = useState(0);
  const [importMethod, setImportMethod]   = useState<ImportMethod>('upload');
  const [protocol, setProtocol]           = useState<Protocol>('REST');
  const [fileList, setFileList]           = useState<UploadFile[]>([]);
  const [rawFile, setRawFile]             = useState<File | null>(null);
  const [urlValue, setUrlValue]           = useState('');
  const [parsing, setParsing]             = useState(false);
  const [parseError, setParseError]       = useState<string | null>(null);
  const [parsedFields, setParsedFields]   = useState<Set<string>>(new Set());
  const [validating, setValidating]       = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [published, setPublished]         = useState(false);

  const reset = () => {
    form.resetFields();
    setCurrent(0);
    setImportMethod('upload');
    setProtocol('REST');
    setFileList([]);
    setRawFile(null);
    setUrlValue('');
    setParsing(false);
    setParseError(null);
    setParsedFields(new Set());
    setValidating(false);
    setValidationResult(null);
    setPublished(false);
  };

  const handleClose = () => { reset(); onClose(); };

  const applyParsed = (info: ParsedInfo) => {
    const values: Record<string, string | undefined> = {
      name:         info.name,
      endpoint:     info.endpoint,
      protocol:     info.protocol,
      inputFormat:  info.inputFormat,
      outputFormat: info.outputFormat,
      authMethod:   info.authMethod,
      category:     info.category,
      description:  info.description,
    };
    form.setFieldsValue(values);
    if (info.protocol) setProtocol(info.protocol);
    setParsedFields(new Set(Object.entries(values).filter(([, v]) => !!v).map(([k]) => k)));
  };

  const processFile = (file: File) => {
    setParsing(true);
    setParseError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      try {
        if (file.name.endsWith('.json')) {
          applyParsed(parseOpenApiJson(JSON.parse(text) as Record<string, unknown>));
        } else if (file.name.endsWith('.wsdl') || (file.name.endsWith('.xml') && text.includes('wsdl'))) {
          applyParsed(parseWsdl(new DOMParser().parseFromString(text, 'text/xml')));
        } else {
          setParseError('Auto-parse is not available for YAML files. Fields have been left empty — please fill in manually.');
        }
      } catch {
        setParseError('Failed to parse the specification. Please fill in the details manually.');
      } finally {
        setParsing(false);
        setCurrent(1);
      }
    };
    reader.readAsText(file);
  };

  const handleNext = async () => {
    if (current === 0) {
      if (importMethod === 'upload') {
        if (!rawFile) { setParseError('Please upload a specification file to continue.'); return; }
        processFile(rawFile);
      } else {
        if (!urlValue.trim()) { setParseError('Please enter a valid URL.'); return; }
        setParsing(true);
        setParseError(null);
        setTimeout(() => {
          applyParsed(MOCK_URL_RESULT);
          setParsing(false);
          setCurrent(1);
        }, 1400);
      }
      return;
    }

    if (current === 1) {
      await form.validateFields();
      const authMethod = form.getFieldValue('authMethod') as string;
      const proto      = form.getFieldValue('protocol')   as Protocol;
      setCurrent(2);
      runMockValidation(authMethod, proto);
    }
  };

  const runMockValidation = (authMethod: string, proto: Protocol) => {
    setValidating(true);
    setValidationResult(null);
    setTimeout(() => {
      setValidating(false);
      setValidationResult({
        specValidation: {
          passed:  true,
          message: `${proto === 'REST' ? 'OpenAPI 3.0' : 'WSDL 1.1'} document is syntactically and structurally correct.`,
        },
        domainCompliance: {
          passed:  true,
          message: 'API operations are consistent with e-invoicing standards (UBL 2.1 / PEPPOL BIS 3.0).',
        },
        securityMetadata: {
          passed:  true,
          message: `${authMethod} security scheme is present and fully described.`,
        },
      });
    }, 1800);
  };

  const allPassed =
    validationResult?.specValidation.passed &&
    validationResult?.domainCompliance.passed &&
    validationResult?.securityMetadata.passed;

  const specAccept = protocol === 'REST' ? '.json,.yaml,.yml' : '.wsdl,.xml';

  return (
    <Modal
      title="Publish New API"
      open={open}
      onCancel={handleClose}
      width={700}
      footer={null}
      destroyOnClose
    >
      <Steps current={current} items={STEP_ITEMS} size="small" style={{ marginBottom: 28 }} />

      {/* ── Step 0: Import Spec ────────────────────────────────────────── */}
      {current === 0 && (
        <div>
          <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 20 }}>
            Upload your API specification or provide a hosted URL — fields will be auto-populated from the spec.
          </Text>

          <div style={{ marginBottom: 18 }}>
            <div style={{ marginBottom: 6, fontWeight: 500, fontSize: 13 }}>Protocol</div>
            <Radio.Group
              value={protocol}
              onChange={e => { setProtocol(e.target.value as Protocol); setParseError(null); }}
              optionType="button"
              buttonStyle="solid"
            >
              <Radio.Button value="REST">REST</Radio.Button>
              <Radio.Button value="SOAP">SOAP</Radio.Button>
            </Radio.Group>
          </div>

          <div style={{ marginBottom: 18 }}>
            <div style={{ marginBottom: 6, fontWeight: 500, fontSize: 13 }}>Import Method</div>
            <Radio.Group
              value={importMethod}
              onChange={e => { setImportMethod(e.target.value as ImportMethod); setParseError(null); }}
            >
              <Radio value="upload"><ThunderboltOutlined /> Upload File</Radio>
              <Radio value="url"><LinkOutlined /> Enter URL</Radio>
            </Radio.Group>
          </div>

          {importMethod === 'upload' ? (
            <Dragger
              accept={specAccept}
              maxCount={1}
              fileList={fileList}
              beforeUpload={(file) => {
                setRawFile(file as unknown as File);
                setFileList([file as unknown as UploadFile]);
                setParseError(null);
                return false;
              }}
              onRemove={() => { setRawFile(null); setFileList([]); }}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">Click or drag the specification file here</p>
              <p className="ant-upload-hint">
                {protocol === 'REST'
                  ? 'OpenAPI / Swagger (.json, .yaml) — metadata will be auto-extracted'
                  : 'WSDL document (.wsdl, .xml) — metadata will be auto-extracted'}
              </p>
            </Dragger>
          ) : (
            <Input
              prefix={<LinkOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="https://api.example.com/openapi.json"
              value={urlValue}
              onChange={e => { setUrlValue(e.target.value); setParseError(null); }}
              size="large"
            />
          )}

          {parsing && (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <Spin indicator={<LoadingOutlined spin />} />
              <Text type="secondary" style={{ marginLeft: 10, fontSize: 13 }}>
                {importMethod === 'url' ? 'Fetching and parsing specification…' : 'Parsing specification…'}
              </Text>
            </div>
          )}

          {parseError && !parsing && (
            <Alert type="warning" showIcon message={parseError} style={{ marginTop: 14 }} />
          )}
        </div>
      )}

      {/* ── Step 1: Review & Edit ──────────────────────────────────────── */}
      {current === 1 && (
        <div>
          {parsedFields.size > 0 && (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
              message={
                <span>
                  <strong>{parsedFields.size}</strong> field{parsedFields.size > 1 ? 's' : ''} auto-populated
                  from the specification.{parsedFields.size < 8 && ' Please complete the remaining fields.'}
                </span>
              }
            />
          )}
          {parseError && (
            <Alert type="warning" showIcon message={parseError} style={{ marginBottom: 16 }} />
          )}

          <Form form={form} layout="vertical" requiredMark="optional">
            <Form.Item
              label={<FieldLabel name="API Name" auto={parsedFields.has('name')} />}
              name="name"
              rules={[{ required: true, message: 'Please enter the API name' }]}
            >
              <Input placeholder="e.g. Invoice Creation API" />
            </Form.Item>

            <Form.Item
              label={<FieldLabel name="Endpoint URL" auto={parsedFields.has('endpoint')} />}
              name="endpoint"
              rules={[
                { required: true, message: 'Please enter the endpoint URL' },
                { type: 'url',    message: 'Please enter a valid URL' },
              ]}
            >
              <Input placeholder="https://api.example.com/invoices" />
            </Form.Item>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <Form.Item
                label={<FieldLabel name="Protocol" auto={parsedFields.has('protocol')} />}
                name="protocol"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="REST">REST</Option>
                  <Option value="SOAP">SOAP</Option>
                </Select>
              </Form.Item>

              <Form.Item
                label={<FieldLabel name="E-invoicing Category" auto={parsedFields.has('category')} />}
                name="category"
                rules={[{ required: true, message: 'Please select a category' }]}
              >
                <Select placeholder="Select category">
                  {CATEGORY_OPTIONS.map(c => <Option key={c} value={c}>{c}</Option>)}
                </Select>
              </Form.Item>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <Form.Item
                label={<FieldLabel name="Input Format" auto={parsedFields.has('inputFormat')} />}
                name="inputFormat"
                rules={[{ required: true, message: 'Required' }]}
              >
                <Select placeholder="Select format">
                  {FORMAT_OPTIONS.map(f => <Option key={f} value={f}>{f}</Option>)}
                </Select>
              </Form.Item>

              <Form.Item
                label={<FieldLabel name="Output Format" auto={parsedFields.has('outputFormat')} />}
                name="outputFormat"
                rules={[{ required: true, message: 'Required' }]}
              >
                <Select placeholder="Select format">
                  {FORMAT_OPTIONS.map(f => <Option key={f} value={f}>{f}</Option>)}
                </Select>
              </Form.Item>
            </div>

            <Form.Item
              label={<FieldLabel name="Authentication Method" auto={parsedFields.has('authMethod')} />}
              name="authMethod"
              rules={[{ required: true, message: 'Please select an auth method' }]}
            >
              <Select placeholder="Select authentication method">
                {AUTH_OPTIONS.map(a => <Option key={a} value={a}>{a}</Option>)}
              </Select>
            </Form.Item>

            <Form.Item
              label={<FieldLabel name="Description" auto={parsedFields.has('description')} />}
              name="description"
              rules={[{ required: true, message: 'Please provide a description' }]}
            >
              <TextArea
                rows={3}
                placeholder="Briefly describe the API's functional purpose within the e-invoicing ecosystem"
              />
            </Form.Item>
          </Form>
        </div>
      )}

      {/* ── Step 2: Validation ────────────────────────────────────────── */}
      {current === 2 && (
        <div>
          {validating && (
            <div style={{ textAlign: 'center', padding: '48px 0' }}>
              <Spin indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />} />
              <p style={{ marginTop: 16, color: '#595959' }}>Running validation pipeline…</p>
            </div>
          )}
          {!validating && validationResult && (
            <>
              <StageRow
                title="Specification Validation"
                desc="Syntactic and structural correctness of the API specification"
                stage={validationResult.specValidation}
              />
              <StageRow
                title="E-invoicing Domain Compliance"
                desc="Alignment with e-invoicing standards (PEPPOL BIS 3.0, UBL 2.1, EN 16931)"
                stage={validationResult.domainCompliance}
              />
              <StageRow
                title="Security & Authentication Metadata"
                desc="Presence and completeness of the declared authentication scheme"
                stage={validationResult.securityMetadata}
              />
              {allPassed && !published && (
                <Alert
                  type="success"
                  showIcon
                  message="All validation stages passed. Ready to publish to the repository."
                  style={{ marginTop: 20 }}
                />
              )}
              {published && (
                <Result
                  status="success"
                  title="API Published Successfully"
                  subTitle="Your API is now available in the repository for discovery and composition."
                  style={{ paddingBlock: 24 }}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
        {current > 0 && !published && (
          <Button onClick={() => setCurrent(c => c - 1)} disabled={validating || parsing}>
            Back
          </Button>
        )}
        {current < 2 && (
          <Button type="primary" onClick={handleNext} loading={parsing}>
            {current === 0
              ? (importMethod === 'upload' ? 'Parse & Continue' : 'Fetch & Continue')
              : 'Validate & Publish'}
          </Button>
        )}
        {current === 2 && !validating && allPassed && !published && (
          <Button type="primary" onClick={() => setPublished(true)}>
            Publish to Repository
          </Button>
        )}
        {current === 2 && !validating && validationResult && !allPassed && (
          <Button onClick={reset}>Fix & Resubmit</Button>
        )}
        {published && (
          <Button type="primary" onClick={handleClose}>Done</Button>
        )}
        {!published && (
          <Button onClick={handleClose} disabled={validating || parsing}>Cancel</Button>
        )}
      </div>
    </Modal>
  );
};

export default APIInfoForm;
