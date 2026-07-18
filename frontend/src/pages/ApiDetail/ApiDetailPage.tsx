import React, { useMemo, useState } from 'react';
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
import type { ApiStatus } from '../../types/api';
import { getMockApiById } from '../../mock/dashboardApis';
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

const ApiDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useSelector((s: RootState) => s.auth.user);
  const [withdrawn, setWithdrawn] = useState(false);

  const api = useMemo(() => (id ? getMockApiById(id) : undefined), [id]);

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

  const isOwner =
    !!user &&
    (api.creatorId === user.user_id ||
      api.creator.toLowerCase() === user.email.toLowerCase());

  const currentStatus: ApiStatus = withdrawn ? 'Withdrawn' : api.status;
  const { color, icon } = statusConfig[currentStatus];

  const handleWithdraw = () => {
    setWithdrawn(true);
    message.success(`"${api.name}" has been withdrawn.`);
  };

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
            <Tooltip title={isOwner ? 'Update (coming soon)' : 'Only the creator can edit this API'}>
              <Button icon={<EditOutlined />} disabled>
                Edit
              </Button>
            </Tooltip>
            <Tooltip title={isOwner ? 'Schema Mapping (coming soon)' : 'Only the creator can map this API'}>
              <Button icon={<SwapOutlined />} disabled>
                Mapping
              </Button>
            </Tooltip>
            <Popconfirm
              title="Withdraw this API?"
              description="It will be removed from the repository."
              okText="Withdraw"
              okButtonProps={{ danger: true }}
              cancelText="Cancel"
              disabled={!isOwner || currentStatus === 'Withdrawn'}
              onConfirm={handleWithdraw}
            >
              <Tooltip
                title={
                  !isOwner
                    ? 'Only the creator can withdraw this API'
                    : currentStatus === 'Withdrawn'
                      ? 'Already withdrawn'
                      : 'Withdraw'
                }
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  disabled={!isOwner || currentStatus === 'Withdrawn'}
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
              <Tag color={protocolColorMap[api.protocol]}>{api.protocol}</Tag>
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
                  <Tag color={protocolColorMap[api.protocol]}>{api.protocol}</Tag>
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
                  item.action === 'Rejected' || item.action === 'Withdrawn'
                    ? 'red'
                    : item.action === 'Published'
                      ? 'green'
                      : 'blue',
                children: (
                  <div className="apd-history-item">
                    <div className="apd-history-item__head">
                      <Text strong>{item.version}</Text>
                      <Tag>{item.action}</Tag>
                      <Text type="secondary">{formatDate(item.changedAt)}</Text>
                    </div>
                    <div className="apd-history-item__meta">
                      by {item.actor}
                    </div>
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
