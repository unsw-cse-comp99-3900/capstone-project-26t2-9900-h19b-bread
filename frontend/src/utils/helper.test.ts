import { describe, expect, it } from 'vitest';

import {
  parseOpenApiDocument,
  parseOpenApiText,
  parseWsdl,
  summarizeApiDescription,
} from './helper';


describe('specification metadata helpers', () => {
  it('summarizes multi-line API descriptions', () => {
    expect(summarizeApiDescription('First sentence.\nSecond line.')).toBe('First sentence. Second line.');
    expect(summarizeApiDescription('  ')).toBeUndefined();
  });

  it('extracts REST metadata from OpenAPI', () => {
    const parsed = parseOpenApiDocument({
      openapi: '3.0.3',
      info: { title: 'Invoice API', description: 'Validates invoices.' },
      servers: [{ url: 'https://api.example.test' }],
      paths: {
        '/invoices': {
          post: {
            requestBody: { content: { 'application/json': { schema: { type: 'object' } } } },
            responses: { 200: { content: { 'application/xml': { schema: { type: 'object' } } } } },
          },
        },
      },
      components: { securitySchemes: { OAuth: { type: 'oauth2' } } },
    });

    expect(parsed.protocol).toBe('REST');
    expect(parsed.name).toBe('Invoice API');
    expect(parsed.endpoint).toBe('https://api.example.test');
    expect(parsed.inputFormat).toBe('JSON');
    expect(parsed.outputFormat).toBe('XML');
  });

  it('parses YAML OpenAPI text', () => {
    const parsed = parseOpenApiText(`
openapi: 3.0.3
info:
  title: YAML Invoice API
  version: 1.0.0
paths: {}
`);

    expect(parsed.name).toBe('YAML Invoice API');
    expect(parsed.protocol).toBe('REST');
  });

  it('extracts SOAP metadata from WSDL XML', () => {
    const xml = new DOMParser().parseFromString(`
      <definitions xmlns="http://schemas.xmlsoap.org/wsdl/" name="InvoiceSoap">
        <service name="InvoiceService">
          <port name="InvoicePort"><address xmlns="http://schemas.xmlsoap.org/wsdl/soap/" location="https://soap.example.test/invoice" /></port>
        </service>
      </definitions>
    `, 'application/xml');

    const parsed = parseWsdl(xml);

    expect(parsed.protocol).toBe('SOAP');
    expect(parsed.name).toBe('InvoiceService');
  });
});
