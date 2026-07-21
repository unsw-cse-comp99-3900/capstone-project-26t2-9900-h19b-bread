import React, { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Row,
  Tag,
  Typography,
  Space,
  Descriptions,
  Timeline,
  Result,
  Popconfirm,
  message,
  Tooltip,
  Spin,
} from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  SwapOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  MinusCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { useSelector } from 'react-redux';
import PublisherLayout from '../../components/PublisherLayout';
import type { RootState } from '../../store';
import type { ApiHistoryItem, ApiRecord, ApiStatus } from '../../types/api';
import { mapStatus } from '../../types/api';
import { withdrawApi } from '../../services/lifecycle';
import { getSubmissions, type SubmissionListItem } from '../../services/submission';
import {
  getApiHistory,
  getVersionDetail,
  getVersions,
  type VersionDetail,
  type VersionEvent,
} from '../../services/versionHistory';
import './ApiDetail.scss';

const { Title, Paragraph, Text } = Typography;

const statusConfig: Record<ApiStatus, { color: string; icon: React.ReactNode }> = {
  Published:  { color: 'success',    icon: <CheckCircleOutlined /> },
  Rejected:   { color: 'error',      icon: <CloseCircleOutlined /> },
  Draft:      { color: 'warning',    icon: <ClockCircleOutlined /> },
  Validating: { color: 'processing', icon: <SyncOutlined spin /> },
  Withdrawn:  { color: 'default',    icon: <MinusCircleOutlined /> },
};

const protocolColorMap: Record<string, string> = {
  REST: 'blue',
  SOAP: 'purple',
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function eventToHistory(event: VersionEvent, versionLabel: string): ApiHistoryItem {
  return {
    version:   versionLabel,
    action:    event.event_type.replace(/_/g, ' '),
    actor:     event.actor_user_id != null ? `user #${event.actor_user_id}` : 'system',
    note:      event.message ?? `${event.from_status ?? '—'} → ${event.to_status ?? '—'}`,
    changedAt: event.created_at,
  };
}

function detailToRecord(
  apiId: string,
  detail: VersionDetail,
  history: ApiHistoryItem[],
  listItem?: SubmissionListItem,
): ApiRecord {
  return {
    key:          apiId,
    name:         listItem?.api_name ?? detail.api_name,
    protocol:     detail.protocol_type,
    endpoint:     detail.endpoint_url,
    authMethod:   detail.auth?.auth_method ?? '—',
    category:     detail.capability_category ?? detail.category ?? '—',
    status:       mapStatus(listItem?.status ?? detail.status),
    creator:      listItem?.submitted_by_name?.trim()
      || (listItem ? `user #${listItem.submitted_by}` : `user #${detail.created_by}`),
    creatorId:    String(listItem?.submitted_by ?? detail.created_by),
    description:  detail.description ?? 'No description provided.',
    inputFormat:  detail.input_format ?? '—',
    outputFormat: detail.output_format ?? '—',
    createdAt:    listItem?.created_at ?? detail.created_at,
    updatedAt:    listItem?.updated_at ?? detail.published_at ?? detail.created_at,
    history,
    isMine:       listItem?.is_current_user_api,
    canManage:    listItem?.can_manage,
  };
}

const ApiDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useSelector((s: RootState) => s.auth.user);

  const [loading, setLoading] = useState(true);
  const [api, setApi] = useState<ApiRecord | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);

  const loadDetail = useCallback(async () => {
    if (!id) {
      setApi(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const [versions, listItems] = await Promise.all([
        getVersions(id),
        getSubmissions().catch(() => [] as SubmissionListItem[]),
      ]);
      const current =
        versions.items.find(v => v.is_current) ?? versions.items[0];

      if (!current) throw new Error('No versions');

      const listItem = listItems.find(item => String(item.api_id) === id);

      const [detail, historyPage] = await Promise.all([
        getVersionDetail(id, current.version_id),
        getApiHistory(id),
      ]);

      const versionMap = new Map(
        versions.items.map(v => [v.version_id, v.version_number]),
      );
      const history = historyPage.items.map(ev =>
        eventToHistory(ev, versionMap.get(ev.version_id) ?? `v#${ev.version_id}`),
      );

      setApi(detailToRecord(id, detail, history, listItem));
    } catch {
      setApi(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const handleWithdraw = async () => {
    if (!api || !user) return;
    setWithdrawing(true);
    try {
      await withdrawApi(api.key, {
        actor_id: Number(user.user_id),
        reason:   'Withdrawn by publisher',
      });
      message.success(`"${api.name}" has been withdrawn.`);
      await loadDetail();
    } catch {
      // interceptor shows error
    } finally {
      setWithdrawing(false);
    }
  };

  if (loading) {
    return (
      <PublisherLayout>
        <div className="apd-empty" style={{ textAlign: 'center', padding: 64 }}>
          <Spin size="large" />
        </div>
      </PublisherLayout>
    );
  }

  if (!api) {
    return (
      <PublisherLayout>
        <div className="apd-empty">
          <Result
            status="404"
            title="API not found"
            subTitle="This API does not exist or is no longer available."
            extra={
              <Button type="primary" onClick={() => navigate('/homepage')}>
                Back to Dashboard
              </Button>
            }
          />
        </div>
      </PublisherLayout>
    );
  }

  const role = user?.role?.toUpperCase() ?? '';
  const canManage =
    api.canManage === true ||
    (!!user && api.creatorId === user.user_id) ||
    role === 'ADMIN' ||
    role === 'MANAGER';

  const currentStatus = api.status;
  const { color, icon } = statusConfig[currentStatus];

  return (
    <PublisherLayout>
      <div className="apd-page">
        <div className="apd-toolbar">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/homepage')}
          >
            Back to Dashboard
          </Button>

          <Space wrap>
            <Tooltip title={canManage ? 'Update (coming soon)' : 'No permission to update'}>
              <Button icon={<EditOutlined />} disabled>
                Edit
              </Button>
            </Tooltip>
            <Tooltip title="Open schema mapping">
              <Button
                icon={<SwapOutlined />}
                onClick={() => navigate(`/apis/${api.key}/mapping`)}
              >
                Mapping
              </Button>
            </Tooltip>
            <Popconfirm
              title="Withdraw this API?"
              description="It will be removed from the repository."
              okText="Withdraw"
              okButtonProps={{ danger: true }}
              cancelText="Cancel"
              disabled={!canManage || currentStatus === 'Withdrawn'}
              onConfirm={() => void handleWithdraw()}
            >
              <Tooltip
                title={
                  !canManage
                    ? 'No permission to withdraw this API'
                    : currentStatus === 'Withdrawn'
                      ? 'Already withdrawn'
                      : 'Withdraw'
                }
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={withdrawing}
                  disabled={!canManage || currentStatus === 'Withdrawn'}
                >
                  Withdraw
                </Button>
              </Tooltip>
            </Popconfirm>
          </Space>
        </div>

        <Card className="apd-glass apd-hero-card" bordered={false}>
          <div className="apd-hero">
            <div>
              <Title level={3} className="apd-hero__title">{api.name}</Title>
              <Paragraph type="secondary" className="apd-hero__desc">
                {api.description}
              </Paragraph>
            </div>
            <Space size={8} wrap className="apd-hero__tags">
              <Tag color={protocolColorMap[api.protocol] ?? 'default'}>{api.protocol}</Tag>
              <Tag icon={icon} color={color}>
                {currentStatus}
              </Tag>
            </Space>
          </div>
        </Card>

        <Row gutter={[16, 16]} className="apd-cards">
          <Col xs={24} lg={14}>
            <Card title="API Information" className="apd-glass apd-info-card" bordered={false}>
              <Descriptions column={1} size="middle" bordered>
                <Descriptions.Item label="API Name">{api.name}</Descriptions.Item>
                <Descriptions.Item label="Endpoint URL">
                  <Text copyable>{api.endpoint}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Protocol">
                  <Tag color={protocolColorMap[api.protocol] ?? 'default'}>{api.protocol}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Auth Method">{api.authMethod}</Descriptions.Item>
                <Descriptions.Item label="Category">{api.category}</Descriptions.Item>
                <Descriptions.Item label="Input Format">{api.inputFormat}</Descriptions.Item>
                <Descriptions.Item label="Output Format">{api.outputFormat}</Descriptions.Item>
                <Descriptions.Item label="Status">
                  <Tag icon={icon} color={color}>{currentStatus}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>

          <Col xs={24} lg={10}>
            <Card title="Ownership & Timeline" className="apd-glass apd-info-card" bordered={false}>
              <Descriptions column={1} size="middle" bordered>
                <Descriptions.Item label="Creator">{api.creator}</Descriptions.Item>
                <Descriptions.Item label="Created At">
                  {formatDate(api.createdAt)}
                </Descriptions.Item>
                <Descriptions.Item label="Updated At">
                  {formatDate(api.updatedAt)}
                </Descriptions.Item>
                <Descriptions.Item label="API ID">{api.key}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
        </Row>

        <Card title="Version History" className="apd-glass apd-history-card" bordered={false}>
          {api.history.length === 0 ? (
            <Text type="secondary">No history records yet.</Text>
          ) : (
            <Timeline
              items={api.history.map(item => ({
                color:
                  /reject|withdraw|fail/i.test(item.action)
                    ? 'red'
                    : /publish/i.test(item.action)
                      ? 'green'
                      : 'blue',
                children: (
                  <div className="apd-history-item">
                    <div className="apd-history-item__head">
                      <Text strong>{item.version}</Text>
                      <Tag>{item.action}</Tag>
                      <Text type="secondary">{formatDate(item.changedAt)}</Text>
                    </div>
                    <div className="apd-history-item__meta">by {item.actor}</div>
                    <div className="apd-history-item__note">{item.note}</div>
                  </div>
                ),
              }))}
            />
          )}
        </Card>
      </div>
    </PublisherLayout>
  );
};

export default ApiDetailPage;
