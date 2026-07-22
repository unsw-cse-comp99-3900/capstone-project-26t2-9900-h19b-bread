// ── Shared types ───────────────────────────────────────────────────────────

export type Protocol = "REST" | "SOAP";

export interface ParsedInfo {
  name?: string;
  endpoint?: string;
  protocol?: Protocol;
  inputFormat?: string;
  outputFormat?: string;
  authMethod?: string;
  category?: string;
  description?: string;
}

export interface StageResult {
  passed: boolean;
  skipped?: boolean;
  message: string;
}

export interface ValidationResult {
  specValidation: StageResult;
  domainCompliance: StageResult;
  securityMetadata: StageResult;
}

// ── Domain constants ────────────────────────────────────────────────────────

export const FORMAT_OPTIONS = [
  "JSON",
  "XML",
  "UBL 2.1",
  "CSV",
  "EDIFACT",
  "PDF",
] as const;
export const AUTH_OPTIONS = [
  "OAuth 2.0",
  "Bearer / JWT",
  "API Key",
  "Basic Authentication",
  "mTLS",
] as const;
export const CATEGORY_OPTIONS = [
  "Invoice Creation",
  "Validation",
  "Transmission",
  "Archiving",
] as const;

// ── Spec parsers ───────────────────────────────────────────────────────────

export function parseOpenApiJson(obj: Record<string, unknown>): ParsedInfo {
  const info = (obj.info as Record<string, unknown>) ?? {};
  const servers = ((obj.servers as unknown[]) ?? []) as Array<
    Record<string, unknown>
  >;
  const components = (obj.components as Record<string, unknown>) ?? {};
  const schemes =
    (components.securitySchemes as Record<string, Record<string, unknown>>) ??
    {};

  let authMethod: string | undefined;
  for (const s of Object.values(schemes)) {
    const scheme = String(s.scheme ?? "").toLowerCase();
    if (s.type === "oauth2") {
      authMethod = "OAuth 2.0";
      break;
    }
    if (s.type === "apiKey") {
      authMethod = "API Key";
      break;
    }
    if (s.type === "http") {
      authMethod = scheme === "basic" ? "Basic Authentication" : "Bearer / JWT";
      break;
    }
    if (s.type === "mutualTLS") {
      authMethod = "mTLS";
      break;
    }
  }

  const paths = (obj.paths as Record<string, Record<string, unknown>>) ?? {};
  let inputFormat: string | undefined;
  let outputFormat: string | undefined;

  outer: for (const pathItem of Object.values(paths)) {
    for (const op of Object.values(pathItem)) {
      if (typeof op !== "object" || !op) continue;
      const operation = op as Record<string, unknown>;

      const rb = operation.requestBody as Record<string, unknown> | undefined;
      if (rb?.content) {
        const types = Object.keys(rb.content as object);
        if (types.includes("application/json")) inputFormat = "JSON";
        else if (types.some((t) => t.includes("xml"))) inputFormat = "XML";
      }

      const responses = operation.responses as
        | Record<string, Record<string, unknown>>
        | undefined;
      if (responses) {
        for (const resp of Object.values(responses)) {
          if (resp?.content) {
            const types = Object.keys(resp.content as object);
            if (types.includes("application/json")) outputFormat = "JSON";
            else if (types.some((t) => t.includes("xml"))) outputFormat = "XML";
          }
        }
      }
      if (inputFormat && outputFormat) break outer;
    }
  }

  const tags = ((obj.tags as unknown[]) ?? []) as Array<
    Record<string, unknown>
  >;
  const tagNames = tags.map((t) => String(t.name ?? "").toLowerCase());
  let category: string | undefined;
  if (tagNames.some((t) => t.includes("creat") || t.includes("submit")))
    category = "Invoice Creation";
  else if (tagNames.some((t) => t.includes("valid"))) category = "Validation";
  else if (tagNames.some((t) => t.includes("transmit") || t.includes("send")))
    category = "Transmission";
  else if (tagNames.some((t) => t.includes("archiv") || t.includes("store")))
    category = "Archiving";

  return {
    name: info.title ? String(info.title) : undefined,
    endpoint: servers[0]?.url ? String(servers[0].url) : undefined,
    description: info.description ? String(info.description) : undefined,
    protocol: "REST",
    inputFormat,
    outputFormat,
    authMethod,
    category,
  };
}

export function parseWsdl(xmlDoc: Document): ParsedInfo {
  const svc =
    xmlDoc.getElementsByTagNameNS(
      "http://schemas.xmlsoap.org/wsdl/",
      "service",
    )[0] ?? xmlDoc.querySelector("service");
  const addr =
    xmlDoc.getElementsByTagNameNS(
      "http://schemas.xmlsoap.org/wsdl/soap/",
      "address",
    )[0] ??
    xmlDoc.getElementsByTagNameNS(
      "http://schemas.xmlsoap.org/wsdl/soap12/",
      "address",
    )[0] ??
    xmlDoc.querySelector("address");
  return {
    name: svc?.getAttribute("name") ?? undefined,
    endpoint: addr?.getAttribute("location") ?? undefined,
    protocol: "SOAP",
    inputFormat: "XML",
    outputFormat: "XML",
  };
}
