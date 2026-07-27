export type ApiStatus = 'Published' | 'Rejected' | 'Draft' | 'Validating' | 'Withdrawn';

export interface ApiHistoryItem {
  version:    string;
  action:     string;
  actor:      string;
  note:       string;
  changedAt:  string;
}

export interface ApiRecord {
  key:          string;
  name:         string;
  protocol:     string;
  endpoint:     string;
  authMethod:   string;
  category:     string;
  status:       ApiStatus;
  creator:      string;
  creatorId:    string;
  description:  string;
  inputFormat:  string;
  outputFormat: string;
  createdAt:    string;
  updatedAt:    string;
  history:      ApiHistoryItem[];
  isMine?:      boolean;
  canManage?:   boolean;
}

export function mapStatus(s: string): ApiStatus {
  const m: Record<string, ApiStatus> = {
    DRAFT:      'Draft',
    VALIDATING: 'Validating',
    REJECTED:   'Rejected',
    PUBLISHED:  'Published',
    WITHDRAWN:  'Withdrawn',
  };
  return m[s.toUpperCase()] ?? 'Draft';
}
