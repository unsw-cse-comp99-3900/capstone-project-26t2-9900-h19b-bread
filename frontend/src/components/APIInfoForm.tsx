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
  Result,
  Radio,
  Tag,
  message,
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
import { createSubmission } from '../services/submission';
import type { SubmissionApiResponse, SubmissionRequest } from '../services/submission';
import type { ValidationApiResponse } from '../services/validation';
import './APIInfoForm.scss';

const { TextArea } = Input;
const { Option }   = Select;
const { Dragger }  = Upload;

// ── Types ──────────────────────────────────────────────────────────────────

export interface PublishedInfo {
  submissionId: string;
  name:         string;
  protocol:     Protocol;
  endpoint:     string;
  authMethod:   string;
  category:     string;
}

interface Props {
  open:          boolean;
  onClose:       () => void;
  onPublished?:  (info: PublishedInfo) => void;
}

type ImportMethod = 'upload' | 'url';

// ── Constants ──────────────────────────────────────────────────────────────

const STEP_ITEMS = [
  { title: 'Import Spec' },
  { title: 'Review & Edit' },
  { title: 'Validation' },
];

// ── Helpers ────────────────────────────────────────────────────────────────

function mapBackendValidation(v: ValidationApiResponse): ValidationResult {
  const passed    = v.overall_status === 'pass';
  const specStage = v.stages.find(s => s.stage === 'specification_validation');
  const specPassed = specStage ? specStage.status === 'pass' : passed;
  const mainError  = v.errors[0]?.message ?? 'Validation failed.';

  return {
    specValidation: {
      passed:  specPassed,
      message: specPassed
        ? 'OpenAPI / WSDL document is syntactically and structurally correct.'
        : mainError,
    },
    domainCompliance: {
      passed:  passed,
      message: passed
        ? 'API operations are consistent with e-invoicing standards (UBL 2.1 / PEPPOL BIS 3.0).'
        : specPassed
          ? 'Domain compliance check failed.'
          : 'Not evaluated — preceding stage failed.',
    },
    securityMetadata: {
      passed:  passed,
      message: passed
        ? 'Authentication scheme is present and fully described.'
        : specPassed
          ? 'Security metadata validation failed.'
          : 'Not evaluated — preceding stage failed.',
    },
  };
}

// ── Sub-components ─────────────────────────────────────────────────────────

interface FieldLabelProps { name: string; auto: boolean; }

const FieldLabel: React.FC<FieldLabelProps> = ({ name, auto }) => (
  <span>
    {name}
    {auto && <Tag className="apif-auto-tag" color="green">Auto</Tag>}
  </span>
);

interface StageRowProps { title: string; desc: string; stage: StageResult; }

const StageRow: React.FC<StageRowProps> = ({ title, desc, stage }) => (
  <div className={`apif-stage-row ${stage.passed ? 'apif-stage-row--pass' : 'apif-stage-row--fail'}`}>
    <span className="apif-stage-row__icon">
      {stage.passed
        ? <CheckCircleFilled style={{ color: '#52c41a' }} />
        : <CloseCircleFilled style={{ color: '#ff4d4f' }} />}
    </span>
    <div className="apif-stage-row__body">
      <div className="apif-stage-row__title">{title}</div>
      <div className="apif-stage-row__desc">{desc}</div>
      <div className={`apif-stage-row__message apif-stage-row__message--${stage.passed ? 'pass' : 'fail'}`}>
        {stage.passed ? '✓ ' : '✗ '}{stage.message}
      </div>
    </div>
  </div>
);

// ── Main component ─────────────────────────────────────────────────────────

const APIInfoForm: React.FC<Props> = ({ open, onClose, onPublished }) => {
  const [form] = Form.useForm();

  const [current, setCurrent]             = useState(0);
  const [importMethod, setImportMethod]   = useState<ImportMethod>('upload');
  const [protocol, setProtocol]           = useState<Protocol>('REST');
  const [fileList, setFileList]           = useState<UploadFile[]>([]);
  const [rawFile, setRawFile]             = useState<File | null>(null);
  const [urlValue, setUrlValue]           = useState('');
  const [specContent, setSpecContent]     = useState<string | null>(null);
  const [parsing, setParsing]             = useState(false);
  const [parseError, setParseError]       = useState<string | null>(null);
  const [parsedFields, setParsedFields]   = useState<Set<string>>(new Set());
  const [validating, setValidating]       = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [published, setPublished]         = useState(false);
  const [submissionId, setSubmissionId]   = useState<string | null>(null);

  const reset = () => {
    form.resetFields();
    setCurrent(0);
    setImportMethod('upload');
    setProtocol('REST');
    setFileList([]);
    setRawFile(null);
    setUrlValue('');
    setSpecContent(null);
    setParsing(false);
    setParseError(null);
    setParsedFields(new Set());
    setValidating(false);
    setValidationResult(null);
    setPublished(false);
    setSubmissionId(null);
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
      setSpecContent(text);
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

  const runRealSubmission = async () => {
    setValidating(true);
    setValidationResult(null);
    const values = form.getFieldsValue() as {
      name: string; endpoint: string; protocol: Protocol;
      inputFormat: string; outputFormat: string; authMethod: string;
      category: string; description?: string;
    };
    const req: SubmissionRequest = {
      api_name:            values.name,
      endpoint_url:        values.endpoint,
      protocol:            values.protocol,
      input_format:        values.inputFormat,
      output_format:       values.outputFormat,
      auth_method:         values.authMethod,
      description:         values.description,
      capability_category: values.category,
      spec_content:        specContent!,
    };
    try {
      const res: SubmissionApiResponse = await createSubmission(req);
      setSubmissionId(res.submission_id);
      const mapped = mapBackendValidation(res.validation);
      setValidationResult(mapped);
      if (res.validation.overall_status === 'pass') {
        setPublished(true);
        onPublished?.({
          submissionId: res.submission_id,
          name:         values.name,
          protocol:     values.protocol,
          endpoint:     values.endpoint,
          authMethod:   values.authMethod,
          category:     values.category,
        });
      }
    } catch {
      setValidationResult({
        specValidation:   { passed: false, message: 'Submission failed. Please check your API specification.' },
        domainCompliance: { passed: false, message: 'Validation could not be completed.' },
        securityMetadata: { passed: false, message: 'Validation could not be completed.' },
      });
    } finally {
      setValidating(false);
    }
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
        try {
          const response = await fetch(urlValue);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const text = await response.text();
          setSpecContent(text);
          try {
            if (urlValue.toLowerCase().endsWith('.json') || text.trim().startsWith('{')) {
              applyParsed(parseOpenApiJson(JSON.parse(text) as Record<string, unknown>));
            } else {
              applyParsed(parseWsdl(new DOMParser().parseFromString(text, 'text/xml')));
            }
          } catch {
            setParseError('Fetched spec but could not auto-parse fields. Please fill in the details manually.');
          }
        } catch {
          setParseError('Could not fetch spec from URL (CORS or network error). Form pre-filled with example data — please upload the file for actual submission.');
          applyParsed(MOCK_URL_RESULT);
          setSpecContent(null);
        } finally {
          setParsing(false);
          setCurrent(1);
        }
      }
      return;
    }

    if (current === 1) {
      await form.validateFields();
      if (!specContent) {
        message.warning('No spec content available. Please upload a specification file.');
        return;
      }
      setCurrent(2);
      runRealSubmission();
    }
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
      className="apif-modal"
    >
      <Steps current={current} items={STEP_ITEMS} size="small" className="apif-steps" />

      {/* ── Step 0: Import Spec ────────────────────────────────────────── */}
      {current === 0 && (
        <div className="apif-step">
          <span className="apif-intro">
            Upload your API specification or provide a hosted URL — fields will be auto-populated from the spec.
          </span>

          <div className="apif-section">
            <div className="apif-section__label">Protocol</div>
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

          <div className="apif-section">
            <div className="apif-section__label">Import Method</div>
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
              className="apif-dragger"
              accept={specAccept}
              maxCount={1}
              fileList={fileList}
              beforeUpload={(file) => {
                setRawFile(file as unknown as File);
                setFileList([file as unknown as UploadFile]);
                setParseError(null);
                return false;
              }}
              onRemove={() => { setRawFile(null); setFileList([]); setSpecContent(null); }}
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
            <div className="apif-parsing">
              <Spin indicator={<LoadingOutlined spin />} />
              <span>
                {importMethod === 'url' ? 'Fetching and parsing specification…' : 'Parsing specification…'}
              </span>
            </div>
          )}

          {parseError && !parsing && (
            <Alert type="warning" showIcon message={parseError} style={{ marginTop: 14 }} />
          )}
        </div>
      )}

      {/* ── Step 1: Review & Edit ──────────────────────────────────────── */}
      {current === 1 && (
        <div className="apif-step">
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
                rows={2}
                placeholder="Briefly describe the API's functional purpose within the e-invoicing ecosystem"
              />
            </Form.Item>
          </Form>
        </div>
      )}

      {/* ── Step 2: Validation ────────────────────────────────────────── */}
      {current === 2 && (
        <div className="apif-step">
          {validating && (
            <div className="apif-validating">
              <Spin indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />} />
              <span>Submitting and running validation pipeline…</span>
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
              {published && (
                <Result
                  status="success"
                  title="API Published Successfully"
                  subTitle={`Submission ID: ${submissionId} — Your API is now available in the repository.`}
                  style={{ paddingBlock: 24 }}
                />
              )}
              {!published && allPassed && (
                <Alert
                  type="info"
                  showIcon
                  message="Validation passed but publication did not complete. Please try again."
                  style={{ marginTop: 20 }}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <div className="apif-footer">
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
