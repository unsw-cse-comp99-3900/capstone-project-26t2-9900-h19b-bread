import React, { useEffect, useState } from "react";
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
} from "antd";
import type { UploadFile } from "antd";
import {
  InboxOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  MinusCircleOutlined,
  LoadingOutlined,
  ThunderboltOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import {
  type Protocol,
  type ParsedInfo,
  type StageResult,
  type ValidationResult,
  FORMAT_OPTIONS,
  AUTH_OPTIONS,
  CATEGORY_OPTIONS,
  parseOpenApiText,
  parseWsdl,
} from "../utils/helper";
import {
  createSubmission,
  saveDraft,
  importFromUrl,
} from "../services/submission";
import type {
  SubmissionApiResponse,
  SubmissionRequest,
} from "../services/submission";
import type { ValidationApiResponse } from "../services/validation";
import { submitApi } from "../services/lifecycle";
import {
  bumpVersionNumber,
  createVersion,
  detectSpecType,
  fromBackendAuth,
  fromBackendCategory,
  getVersionDetail,
  getVersions,
  getVersionSpecification,
  nextVersionNumber,
  toBackendAuth,
  toBackendCategory,
  updateVersion,
  type VersionWriteRequest,
} from "../services/versionHistory";
import "./APIInfoForm.scss";

const { TextArea } = Input;
const { Option } = Select;
const { Dragger } = Upload;

interface Props {
  open: boolean;
  onClose: () => void;
  onComplete?: () => void;
  /** When set, form updates an existing API instead of creating one. */
  editApiId?: string | null;
}

type ImportMethod = "upload" | "url";

interface EditContext {
  apiId: string;
  versionId: number;
  versionNumber: string;
  versionStatus: string;
}

const STEP_ITEMS = [
  { title: "Import Spec" },
  { title: "Review & Edit" },
  { title: "Validation" },
];

function mapBackendValidation(v: ValidationApiResponse): ValidationResult {
  const passed = v.overall_status === "pass";
  const specStage = v.stages.find(
    (s) => s.stage === "specification_validation",
  );
  const domainStage = v.stages.find(
    (s) => s.stage === "domain_compliance_validation",
  );
  const securityStage = v.stages.find((s) => s.stage === "security_validation");
  const specPassed = specStage ? specStage.status === "pass" : passed;
  const domainPassed = domainStage ? domainStage.status === "pass" : passed;
  const securityPassed = securityStage
    ? securityStage.status === "pass"
    : passed;
  const specError =
    v.errors.find((e) => e.stage === "specification_validation")?.message ??
    v.errors[0]?.message ??
    "Validation failed.";
  const domainError =
    v.errors.find((e) => e.stage === "domain_compliance_validation")?.message ??
    "Domain compliance check failed.";
  const securityError =
    v.errors.find((e) => e.stage === "security_validation")?.message ??
    "Security metadata validation failed.";

  return {
    specValidation: {
      passed: specPassed,
      message: specPassed
        ? "OpenAPI / WSDL document is syntactically and structurally correct."
        : specError,
    },
    domainCompliance: {
      passed: domainPassed,
      skipped: !specPassed,
      message: domainPassed
        ? "API operations are consistent with e-invoicing standards (UBL 2.1 / PEPPOL BIS 3.0)."
        : specPassed
          ? domainError
          : "Not evaluated — preceding stage failed.",
    },
    securityMetadata: {
      passed: securityPassed,
      skipped: !specPassed,
      message: securityPassed
        ? "Authentication scheme is present and fully described."
        : specPassed
          ? securityError
          : "Not evaluated — preceding stage failed.",
    },
  };
}

function mapLifecycleStatus(status: string): ValidationResult {
  const normalized = status.toUpperCase();
  const passed = normalized === "PUBLISHED";
  const rejected = normalized === "REJECTED";
  return {
    specValidation: {
      passed: passed || !rejected,
      message: passed
        ? "Specification accepted."
        : rejected
          ? "Specification rejected during validation."
          : `Lifecycle status: ${status}`,
    },
    domainCompliance: {
      passed,
      skipped: !passed && !rejected,
      message: passed
        ? "Domain compliance checks passed."
        : rejected
          ? "Domain compliance checks failed."
          : "Validation still in progress.",
    },
    securityMetadata: {
      passed,
      skipped: !passed && !rejected,
      message: passed
        ? "Security metadata accepted."
        : rejected
          ? "Security metadata rejected."
          : "Validation still in progress.",
    },
  };
}

interface FieldLabelProps {
  name: string;
  auto: boolean;
}

const FieldLabel: React.FC<FieldLabelProps> = ({ name, auto }) => (
  <span>
    {name}
    {auto && (
      <Tag className="apif-auto-tag" color="green">
        Auto
      </Tag>
    )}
  </span>
);

interface StageRowProps {
  title: string;
  desc: string;
  stage: StageResult;
}

const StageRow: React.FC<StageRowProps> = ({ title, desc, stage }) => {
  const modifier = stage.skipped ? "skip" : stage.passed ? "pass" : "fail";
  return (
    <div className={`apif-stage-row apif-stage-row--${modifier}`}>
      <span className="apif-stage-row__icon">
        {stage.skipped ? (
          <MinusCircleOutlined style={{ color: "#bfbfbf" }} />
        ) : stage.passed ? (
          <CheckCircleFilled style={{ color: "#52c41a" }} />
        ) : (
          <CloseCircleFilled style={{ color: "#ff4d4f" }} />
        )}
      </span>
      <div className="apif-stage-row__body">
        <div className="apif-stage-row__title">{title}</div>
        <div className="apif-stage-row__desc">{desc}</div>
        <div
          className={`apif-stage-row__message apif-stage-row__message--${modifier}`}
        >
          {stage.skipped ? "— " : stage.passed ? "✓ " : "✗ "}
          {stage.message}
        </div>
      </div>
    </div>
  );
};

const APIInfoForm: React.FC<Props> = ({
  open,
  onClose,
  onComplete,
  editApiId = null,
}) => {
  const [form] = Form.useForm();
  const isEdit = !!editApiId;

  const [current, setCurrent] = useState(0);
  const [importMethod, setImportMethod] = useState<ImportMethod>("upload");
  const [protocol, setProtocol] = useState<Protocol>("REST");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [rawFile, setRawFile] = useState<File | null>(null);
  const [urlValue, setUrlValue] = useState("");
  const [specContent, setSpecContent] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsedFields, setParsedFields] = useState<Set<string>>(new Set());
  const [validating, setValidating] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(false);
  const [editCtx, setEditCtx] = useState<EditContext | null>(null);
  const [validationResult, setValidationResult] =
    useState<ValidationResult | null>(null);
  const [published, setPublished] = useState(false);
  const [submissionId, setSubmissionId] = useState<string | null>(null);

  const reset = () => {
    form.resetFields();
    setCurrent(0);
    setImportMethod("upload");
    setProtocol("REST");
    setFileList([]);
    setRawFile(null);
    setUrlValue("");
    setSpecContent(null);
    setParsing(false);
    setParseError(null);
    setParsedFields(new Set());
    setValidating(false);
    setSavingDraft(false);
    setLoadingEdit(false);
    setEditCtx(null);
    setValidationResult(null);
    setPublished(false);
    setSubmissionId(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const applyParsed = (info: ParsedInfo) => {
    const values: Record<string, string | undefined> = {
      name: info.name,
      endpoint: info.endpoint,
      protocol: info.protocol,
      inputFormat: info.inputFormat,
      outputFormat: info.outputFormat,
      authMethod: info.authMethod,
      category: info.category,
      description: info.description,
    };
    form.setFieldsValue(values);
    if (info.protocol) setProtocol(info.protocol);
    setParsedFields(
      new Set(
        Object.entries(values)
          .filter(([, v]) => !!v)
          .map(([k]) => k),
      ),
    );
  };

  useEffect(() => {
    if (!open || !editApiId) return;

    let cancelled = false;
    const load = async () => {
      setLoadingEdit(true);
      try {
        const versions = await getVersions(editApiId);
        const currentVersion =
          versions.items.find((v) => v.is_current) ?? versions.items[0];
        if (!currentVersion) {
          message.error("No version found for this API.");
          handleClose();
          return;
        }

        const status = String(currentVersion.status).toUpperCase();
        if (status === "WITHDRAWN") {
          message.warning("Withdrawn APIs cannot be updated.");
          handleClose();
          return;
        }
        if (status === "VALIDATING") {
          message.warning("Finish the current validation before updating.");
          handleClose();
          return;
        }

        const [detail, specification] = await Promise.all([
          getVersionDetail(editApiId, currentVersion.version_id),
          getVersionSpecification(editApiId, currentVersion.version_id),
        ]);

        if (cancelled) return;

        const proto = (
          detail.protocol_type === "SOAP" ? "SOAP" : "REST"
        ) as Protocol;
        setProtocol(proto);
        setSpecContent(specification || null);
        setEditCtx({
          apiId: editApiId,
          versionId: currentVersion.version_id,
          versionNumber:
            status === "DRAFT"
              ? currentVersion.version_number
              : nextVersionNumber(versions.items),
          versionStatus: status,
        });

        form.setFieldsValue({
          name: detail.api_name,
          endpoint: detail.endpoint_url,
          protocol: proto,
          inputFormat: detail.input_format || undefined,
          outputFormat: detail.output_format || undefined,
          authMethod: fromBackendAuth(detail.auth?.auth_method),
          category: fromBackendCategory(
            detail.capability_category,
            detail.category,
          ),
          description: detail.description || undefined,
          versionNumber:
            status === "DRAFT"
              ? detail.version_number
              : nextVersionNumber(versions.items),
          changeNote: "",
        });
        setCurrent(1);
      } catch {
        if (!cancelled) {
          message.error("Failed to load API for editing.");
          handleClose();
        }
      } finally {
        if (!cancelled) setLoadingEdit(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once per open/editApiId
  }, [open, editApiId]);

  const processFile = (file: File) => {
    setParsing(true);
    setParseError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      setSpecContent(text);
      try {
        if (
          file.name.endsWith(".wsdl") ||
          (file.name.endsWith(".xml") && text.includes("wsdl"))
        ) {
          applyParsed(
            parseWsdl(new DOMParser().parseFromString(text, "text/xml")),
          );
        } else {
          applyParsed(parseOpenApiText(text));
        }
      } catch {
        setParseError(
          "Failed to parse the specification. Please fill in the details manually.",
        );
      } finally {
        setParsing(false);
        setCurrent(1);
      }
    };
    reader.readAsText(file);
  };

  const getFormValues = () =>
    form.getFieldsValue() as {
      name: string;
      endpoint: string;
      protocol: Protocol;
      inputFormat: string;
      outputFormat: string;
      authMethod: string;
      category: string;
      description?: string;
      versionNumber?: string;
      changeNote?: string;
    };

  const buildVersionWrite = (
    values: ReturnType<typeof getFormValues>,
  ): VersionWriteRequest => {
    const spec = specContent ?? "";
    const versionNumber =
      values.versionNumber?.trim() ||
      (editCtx ? bumpVersionNumber(editCtx.versionNumber) : "v1.0");
    return {
      version_number: versionNumber,
      change_note:
        values.changeNote?.trim() ||
        (isEdit ? "Updated via publisher UI" : null),
      api_name: values.name,
      endpoint_url: values.endpoint,
      protocol_type: values.protocol,
      category: toBackendCategory(values.category),
      capability_category: values.category,
      description: values.description ?? null,
      input_format: values.inputFormat,
      output_format: values.outputFormat,
      auth_method: toBackendAuth(values.authMethod),
      auth_is_complete: true,
      spec_type: detectSpecType(values.protocol, spec),
      specification: spec,
    };
  };

  const persistEditVersion = async (
    values: ReturnType<typeof getFormValues>,
  ) => {
    if (!editCtx) throw new Error("Missing edit context");
    const body = buildVersionWrite(values);
    if (editCtx.versionStatus === "DRAFT") {
      const detail = await updateVersion(
        editCtx.apiId,
        editCtx.versionId,
        body,
      );
      setEditCtx({
        ...editCtx,
        versionId: detail.version_id,
        versionNumber: detail.version_number,
        versionStatus: String(detail.status).toUpperCase(),
      });
      return detail;
    }
    const detail = await createVersion(editCtx.apiId, body);
    setEditCtx({
      apiId: editCtx.apiId,
      versionId: detail.version_id,
      versionNumber: detail.version_number,
      versionStatus: String(detail.status).toUpperCase(),
    });
    return detail;
  };

  const runRealSubmission = async () => {
    setValidating(true);
    setValidationResult(null);
    const values = getFormValues();
    try {
      if (isEdit && editCtx) {
        await persistEditVersion(values);
        const lifecycle = await submitApi(editCtx.apiId, {
          protocol: values.protocol,
          spec_content: specContent ?? undefined,
        });
        setSubmissionId(String(lifecycle.api_id));
        const mapped = mapLifecycleStatus(lifecycle.status);
        setValidationResult(mapped);
        onComplete?.();
        if (String(lifecycle.status).toUpperCase() === "PUBLISHED") {
          setPublished(true);
        }
        return;
      }

      const authMethod = toBackendAuth(values.authMethod);
      let res: SubmissionApiResponse;
      if (importMethod === "url") {
        res = await importFromUrl({
          api_name: values.name,
          endpoint_url: values.endpoint,
          protocol: values.protocol,
          input_format: values.inputFormat,
          output_format: values.outputFormat,
          auth_method: authMethod,
          description: values.description,
          capability_category: values.category,
          spec_url: urlValue,
        });
      } else {
        const req: SubmissionRequest = {
          api_name: values.name,
          endpoint_url: values.endpoint,
          protocol: values.protocol,
          input_format: values.inputFormat,
          output_format: values.outputFormat,
          auth_method: authMethod,
          description: values.description,
          capability_category: values.category,
          spec_content: specContent!,
        };
        res = await createSubmission(req);
      }
      setSubmissionId(res.submission_id);
      const mapped = mapBackendValidation(res.validation);
      setValidationResult(mapped);
      onComplete?.();
      if (res.validation.overall_status === "pass") {
        setPublished(true);
      }
    } catch {
      setValidationResult({
        specValidation: {
          passed: false,
          message: "Submission failed. Please check your API specification.",
        },
        domainCompliance: {
          passed: false,
          message: "Validation could not be completed.",
        },
        securityMetadata: {
          passed: false,
          message: "Validation could not be completed.",
        },
      });
    } finally {
      setValidating(false);
    }
  };

  const handleSaveDraft = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    if (!specContent) {
      message.warning("Please upload a specification file to save as draft.");
      return;
    }
    const values = getFormValues();
    setSavingDraft(true);
    try {
      if (isEdit && editCtx) {
        await persistEditVersion(values);
        message.success("Draft updated.");
      } else {
        await saveDraft({
          api_name: values.name,
          endpoint_url: values.endpoint,
          protocol: values.protocol,
          input_format: values.inputFormat,
          output_format: values.outputFormat,
          auth_method: toBackendAuth(values.authMethod),
          description: values.description,
          capability_category: values.category,
          spec_content: specContent,
        });
        message.success("Draft saved. You can submit for validation later.");
      }
      onComplete?.();
      handleClose();
    } catch {
      // error shown by request interceptor
    } finally {
      setSavingDraft(false);
    }
  };

  const handleNext = async () => {
    if (current === 0) {
      if (isEdit && !rawFile && !urlValue.trim() && specContent) {
        setCurrent(1);
        return;
      }
      if (importMethod === "upload") {
        if (!rawFile) {
          setParseError("Please upload a specification file to continue.");
          return;
        }
        processFile(rawFile);
      } else {
        if (!urlValue.trim()) {
          setParseError("Please enter a valid URL.");
          return;
        }
        setParsing(true);
        setParseError(null);
        try {
          const response = await fetch(urlValue);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const text = await response.text();
          setSpecContent(text);
          try {
            if (protocol === "SOAP" || text.trim().startsWith("<")) {
              applyParsed(
                parseWsdl(new DOMParser().parseFromString(text, "text/xml")),
              );
            } else {
              applyParsed(parseOpenApiText(text));
            }
          } catch {
            setParseError(
              "Fetched spec but could not auto-parse fields. Please fill in the details manually.",
            );
          }
        } catch {
          setParseError(
            "Could not fetch the URL in the browser (often CORS). " +
              "Leave fields empty or fill them manually — the backend will fetch the spec during submission.",
          );
        } finally {
          setParsing(false);
          setCurrent(1);
        }
      }
      return;
    }

    if (current === 1) {
      await form.validateFields();
      if (importMethod === "upload" && !specContent) {
        message.warning(
          "No spec content available. Please upload a specification file.",
        );
        return;
      }
      setCurrent(2);
      void runRealSubmission();
    }
  };

  const allPassed =
    validationResult?.specValidation.passed &&
    validationResult?.domainCompliance.passed &&
    validationResult?.securityMetadata.passed;

  const specAccept = protocol === "REST" ? ".json,.yaml,.yml" : ".wsdl,.xml";

  return (
    <Modal
      title={isEdit ? "Update API" : "Publish New API"}
      open={open}
      onCancel={handleClose}
      width={700}
      footer={null}
      destroyOnHidden
      className="apif-modal"
    >
      {loadingEdit ? (
        <div className="apif-parsing" style={{ padding: 48 }}>
          <Spin indicator={<LoadingOutlined spin />} />
          <span>Loading API for edit…</span>
        </div>
      ) : (
        <>
          <Steps
            current={current}
            items={STEP_ITEMS}
            size="small"
            className="apif-steps"
          />

          {current === 0 && (
            <div className="apif-step">
              <span className="apif-intro">
                {isEdit
                  ? "Replace the specification if needed, or keep the existing one and continue."
                  : "Upload your API specification or provide a hosted URL — fields will be auto-populated from the spec."}
              </span>

              {isEdit && specContent && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 14 }}
                  message="Existing specification loaded. Upload a new file only if you want to replace it."
                />
              )}

              <div className="apif-section">
                <div className="apif-section__label">Protocol</div>
                <Radio.Group
                  value={protocol}
                  onChange={(e) => {
                    setProtocol(e.target.value as Protocol);
                    setParseError(null);
                  }}
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
                  onChange={(e) => {
                    setImportMethod(e.target.value as ImportMethod);
                    setParseError(null);
                  }}
                >
                  <Radio value="upload">
                    <ThunderboltOutlined /> Upload File
                  </Radio>
                  <Radio value="url">
                    <LinkOutlined /> Enter URL
                  </Radio>
                </Radio.Group>
              </div>

              {importMethod === "upload" ? (
                <Dragger
                  className="apif-dragger"
                  accept={specAccept}
                  maxCount={1}
                  fileList={fileList}
                  beforeUpload={(file) => {
                    const name = (file as unknown as File).name.toLowerCase();
                    const ext = name.includes(".")
                      ? "." + name.split(".").pop()
                      : "";
                    const allowed =
                      protocol === "REST"
                        ? [".json", ".yaml", ".yml"]
                        : [".wsdl", ".xml"];
                    if (!allowed.includes(ext)) {
                      setParseError(
                        `Unsupported file format "${ext || "(none)"}". ` +
                          (protocol === "REST"
                            ? "Please upload an OpenAPI specification (.json, .yaml, or .yml)."
                            : "Please upload a WSDL document (.wsdl or .xml)."),
                      );
                      return Upload.LIST_IGNORE;
                    }
                    setRawFile(file as unknown as File);
                    setFileList([file as unknown as UploadFile]);
                    setParseError(null);
                    return false;
                  }}
                  onRemove={() => {
                    setRawFile(null);
                    setFileList([]);
                  }}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">
                    Click or drag the specification file here
                  </p>
                  <p className="ant-upload-hint">
                    {protocol === "REST"
                      ? "OpenAPI / Swagger (.json, .yaml) — metadata will be auto-extracted"
                      : "WSDL document (.wsdl, .xml) — metadata will be auto-extracted"}
                  </p>
                </Dragger>
              ) : (
                <Input
                  prefix={<LinkOutlined style={{ color: "#bfbfbf" }} />}
                  placeholder="https://api.example.com/openapi.json"
                  value={urlValue}
                  onChange={(e) => {
                    setUrlValue(e.target.value);
                    setParseError(null);
                  }}
                  size="large"
                />
              )}

              {parsing && (
                <div className="apif-parsing">
                  <Spin indicator={<LoadingOutlined spin />} />
                  <span>
                    {importMethod === "url"
                      ? "Fetching and parsing specification…"
                      : "Parsing specification…"}
                  </span>
                </div>
              )}

              {parseError && !parsing && (
                <Alert
                  type={
                    parseError.startsWith("Unsupported") ? "error" : "warning"
                  }
                  showIcon
                  message={parseError}
                  style={{ marginTop: 14 }}
                />
              )}
            </div>
          )}

          {current === 1 && (
            <div className="apif-step">
              {parsedFields.size > 0 && (
                <Alert
                  type="success"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message={
                    <span>
                      <strong>{parsedFields.size}</strong> field
                      {parsedFields.size > 1 ? "s" : ""} auto-populated from the
                      specification.
                      {parsedFields.size < 8 &&
                        " Please complete the remaining fields."}
                    </span>
                  }
                />
              )}
              {parseError && (
                <Alert
                  type="warning"
                  showIcon
                  message={parseError}
                  style={{ marginBottom: 16 }}
                />
              )}

              <Form form={form} layout="vertical" requiredMark="optional">
                {isEdit && (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 16,
                    }}
                  >
                    <Form.Item
                      label="Version Number"
                      name="versionNumber"
                      rules={[
                        {
                          required: true,
                          message: "Version number is required",
                        },
                      ]}
                    >
                      <Input placeholder="e.g. v1.1" />
                    </Form.Item>
                    <Form.Item label="Change Note" name="changeNote">
                      <Input placeholder="What changed in this update?" />
                    </Form.Item>
                  </div>
                )}

                <Form.Item
                  label={
                    <FieldLabel
                      name="API Name"
                      auto={parsedFields.has("name")}
                    />
                  }
                  name="name"
                  rules={[
                    { required: true, message: "Please enter the API name" },
                  ]}
                >
                  <Input placeholder="e.g. Invoice Creation API" />
                </Form.Item>

                <Form.Item
                  label={
                    <FieldLabel
                      name="Endpoint URL"
                      auto={parsedFields.has("endpoint")}
                    />
                  }
                  name="endpoint"
                  rules={[
                    {
                      required: true,
                      message: "Please enter the endpoint URL",
                    },
                    { type: "url", message: "Please enter a valid URL" },
                  ]}
                >
                  <Input placeholder="https://api.example.com/invoices" />
                </Form.Item>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 16,
                  }}
                >
                  <Form.Item
                    label={
                      <FieldLabel
                        name="Protocol"
                        auto={parsedFields.has("protocol")}
                      />
                    }
                    name="protocol"
                    rules={[{ required: true }]}
                  >
                    <Select>
                      <Option value="REST">REST</Option>
                      <Option value="SOAP">SOAP</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item
                    label={
                      <FieldLabel
                        name="E-invoicing Category"
                        auto={parsedFields.has("category")}
                      />
                    }
                    name="category"
                    rules={[
                      { required: true, message: "Please select a category" },
                    ]}
                  >
                    <Select placeholder="Select category">
                      {CATEGORY_OPTIONS.map((c) => (
                        <Option key={c} value={c}>
                          {c}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 16,
                  }}
                >
                  <Form.Item
                    label={
                      <FieldLabel
                        name="Input Format"
                        auto={parsedFields.has("inputFormat")}
                      />
                    }
                    name="inputFormat"
                    rules={[{ required: true, message: "Required" }]}
                  >
                    <Select placeholder="Select format">
                      {FORMAT_OPTIONS.map((f) => (
                        <Option key={f} value={f}>
                          {f}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>

                  <Form.Item
                    label={
                      <FieldLabel
                        name="Output Format"
                        auto={parsedFields.has("outputFormat")}
                      />
                    }
                    name="outputFormat"
                    rules={[{ required: true, message: "Required" }]}
                  >
                    <Select placeholder="Select format">
                      {FORMAT_OPTIONS.map((f) => (
                        <Option key={f} value={f}>
                          {f}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </div>

                <Form.Item
                  label={
                    <FieldLabel
                      name="Authentication Method"
                      auto={parsedFields.has("authMethod")}
                    />
                  }
                  name="authMethod"
                  rules={[
                    { required: true, message: "Please select an auth method" },
                  ]}
                >
                  <Select placeholder="Select authentication method">
                    {AUTH_OPTIONS.map((a) => (
                      <Option key={a} value={a}>
                        {a}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item
                  label={
                    <FieldLabel
                      name="Description"
                      auto={parsedFields.has("description")}
                    />
                  }
                  name="description"
                  rules={[
                    { required: true, message: "Please provide a description" },
                  ]}
                >
                  <TextArea
                    rows={2}
                    placeholder="Briefly describe the API's functional purpose within the e-invoicing ecosystem"
                  />
                </Form.Item>
              </Form>
            </div>
          )}

          {current === 2 && (
            <div className="apif-step">
              {validating && (
                <div className="apif-validating">
                  <Spin
                    indicator={
                      <LoadingOutlined style={{ fontSize: 36 }} spin />
                    }
                  />
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
                      title={
                        isEdit
                          ? "API Updated Successfully"
                          : "API Published Successfully"
                      }
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

          <div className="apif-footer">
            {current > 0 && !published && (
              <Button
                onClick={() => setCurrent((c) => c - 1)}
                disabled={validating || savingDraft || parsing}
              >
                Back
              </Button>
            )}
            {current === 1 && (
              <Button
                onClick={handleSaveDraft}
                loading={savingDraft}
                disabled={validating}
              >
                Save as Draft
              </Button>
            )}
            {current < 2 && (
              <Button
                type="primary"
                onClick={() => void handleNext()}
                loading={parsing}
                disabled={savingDraft}
              >
                {current === 0
                  ? isEdit && !rawFile && !urlValue.trim() && specContent
                    ? "Keep Spec & Continue"
                    : importMethod === "upload"
                      ? "Parse & Continue"
                      : "Continue"
                  : isEdit
                    ? "Validate & Update"
                    : "Validate & Publish"}
              </Button>
            )}
            {current === 2 && !validating && validationResult && !allPassed && (
              <Button
                onClick={() => {
                  setValidationResult(null);
                  setPublished(false);
                  setCurrent(1);
                }}
              >
                Fix & Resubmit
              </Button>
            )}
            {published && (
              <Button type="primary" onClick={handleClose}>
                Done
              </Button>
            )}
            {!published && (
              <Button
                onClick={handleClose}
                disabled={validating || savingDraft || parsing}
              >
                Cancel
              </Button>
            )}
          </div>
        </>
      )}
    </Modal>
  );
};

export default APIInfoForm;
