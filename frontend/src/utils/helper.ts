import { parse as parseYaml } from "yaml";

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

const AUTO_DESCRIPTION_LIMIT = 360;

/**
 * OpenAPI info.description is often a provider's full integration guide, not
 * the short catalogue description required by this application. The original
 * document is kept intact; this derives a concise, editable summary instead.
 */
export function summarizeApiDescription(
  value: unknown,
  limit = AUTO_DESCRIPTION_LIMIT,
): string | undefined {
  if (typeof value !== "string" || !value.trim()) return undefined;

  const cleanParagraph = (paragraph: string) =>
    paragraph
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/<[^>]*>/g, " ")
      .replace(/`([^`]*)`/g, "$1")
      .replace(/^\s{0,3}[#>]+\s?/gm, "")
      .replace(/[*_~]/g, "")
      .replace(/\s+/g, " ")
      .trim();

  const paragraphs = value
    .split(/\r?\n\s*\r?\n/)
    .map(cleanParagraph)
    .filter(Boolean);
  const summary =
    paragraphs.find(
      (paragraph) =>
        paragraph.replace(/[^\p{L}\p{N}]/gu, "").length >= 40,
    ) ??
    paragraphs[0] ??
    cleanParagraph(value);

  if (summary.length <= limit) return summary;
  const cutAt = summary.lastIndexOf(" ", limit);
  return `${summary.slice(0, cutAt > 80 ? cutAt : limit).trim()}…`;
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

export function parseOpenApiDocument(obj: Record<string, unknown>): ParsedInfo {
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
    description: summarizeApiDescription(info.description),
    protocol: "REST",
    inputFormat,
    outputFormat,
    authMethod,
    category,
  };
}

/** Parse a JSON or YAML OpenAPI document before extracting catalogue metadata. */
export function parseOpenApiText(text: string): ParsedInfo {
  const trimmed = text.trim();
  const parsed: unknown = trimmed.startsWith("{")
    ? JSON.parse(trimmed)
    : parseYaml(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("OpenAPI document must be an object.");
  }
  return parseOpenApiDocument(parsed as Record<string, unknown>);
}

/** @deprecated Use parseOpenApiDocument or parseOpenApiText. */
export const parseOpenApiJson = parseOpenApiDocument;

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
