import React, { useMemo, useState } from 'react';
import {
  Button,
  Table,
  Tag,
  Space,
  Typography,
  Tooltip,
  Popconfirm,
  message,
  Tabs,
  Input,
  Select,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  SwapOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  MinusCircleOutlined,
  SyncOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { TableColumnsType } from 'antd';
import APIInfoForm from '../../components/APIInfoForm';
import PublisherLayout from '../../components/PublisherLayout';
import type { RootState } from '../../store';
import type { ApiRecord, ApiStatus } from '../../types/api';
import { getMockApiList } from '../../mock/dashboardApis';
import './Homepage.scss';

const { Title } = Typography;

type ListTab = 'all' | 'mine';

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

const STATUS_FILTER_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  { value: 'Published', label: 'Published' },
  { value: 'Rejected', label: 'Rejected' },
  { value: 'Draft', label: 'Draft' },
  { value: 'Validating', label: 'Validating' },
  { value: 'Withdrawn', label: 'Withdrawn' },
];

const HomePage: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [listTab, setListTab] = useState<ListTab>('all');
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [tableData, setTableData] = useState<ApiRecord[]>(() => getMockApiList());
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);

  const navigate = useNavigate();
  const user = useSelector((s: RootState) => s.auth.user);

  const filteredData = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    return tableData.filter(row => {
      const isMine =
        !!user &&
        (row.creatorId === user.user_id ||
          row.creator.toLowerCase() === user.email.toLowerCase());

      if (listTab === 'mine' && !isMine) return false;

      if (statusFilter !== 'all' && row.status !== statusFilter) return false;

      if (!q) return true;
      return (
        row.name.toLowerCase().includes(q) ||
        row.endpoint.toLowerCase().includes(q) ||
        row.creator.toLowerCase().includes(q) ||
        row.status.toLowerCase().includes(q) ||
        row.category.toLowerCase().includes(q)
      );
    });
  }, [tableData, listTab, keyword, statusFilter, user]);

  const handleWithdraw = (record: ApiRecord) => {
    setWithdrawingId(record.key);
    setTimeout(() => {
      setTableData(prev =>
        prev.map(r =>
          r.key === record.key
            ? {
                ...r,
                status: 'Withdrawn' as ApiStatus,
                updatedAt: new Date().toISOString(),
                history: [
                  {
                    version: r.history[0]?.version ?? 'v1.0',
                    action: 'Withdrawn',
                    actor: user?.email ?? 'unknown',
                    note: 'Withdrawn by publisher (mock).',
                    changedAt: new Date().toISOString(),
                  },
                  ...r.history,
                ],
              }
            : r,
        ),
      );
      message.success(`"${record.name}" has been withdrawn.`);
      setWithdrawingId(null);
    }, 400);
  };

  const baseColumns: TableColumnsType<ApiRecord> = [
    {
      title:     'API Name',
      dataIndex: 'name',
      key:       'name',
      width:     180,
      ellipsis:  { showTitle: false },
      render: (name: string, record) => (
        <Tooltip title={name} placement="topLeft">
          <Button
            type="link"
            className="hp-api-name-link"
            onClick={() => navigate(`/apis/${record.key}`)}
          >
            {name}
          </Button>
        </Tooltip>
      ),
    },
    {
      title:     'Protocol',
      dataIndex: 'protocol',
      key:       'protocol',
      align:     'center',
      width:     96,
      render: (protocol: string) => (
        <Tag color={protocolColorMap[protocol]}>{protocol}</Tag>
      ),
    },
    {
      title:     'Endpoint URL',
      dataIndex: 'endpoint',
      key:       'endpoint',
      ellipsis:  { showTitle: false },
      render: (endpoint: string) => (
        <Tooltip title={endpoint} placement="topLeft">
          <span style={{ cursor: 'default' }}>{endpoint}</span>
        </Tooltip>
      ),
    },
    {
      title:     'Auth Method',
      dataIndex: 'authMethod',
      key:       'authMethod',
      align:     'center',
      width:     110,
    },
    {
      title:     'Category',
      dataIndex: 'category',
      key:       'category',
      align:     'center',
      width:     140,
    },
    {
      title:     'Status',
      dataIndex: 'status',
      key:       'status',
      align:     'center',
      width:     120,
      render: (status: ApiStatus) => {
        const { color, icon } = statusConfig[status];
        return (
          <Tag icon={icon} color={color} style={{ fontWeight: 500, fontSize: 12 }}>
            {status}
          </Tag>
        );
      },
    },
  ];

  const creatorColumn: TableColumnsType<ApiRecord>[number] = {
    title:     'Creator',
    dataIndex: 'creator',
    key:       'creator',
    width:     170,
    ellipsis:  { showTitle: false },
    render: (creator: string) => (
      <Tooltip title={creator} placement="topLeft">
        <span>{creator}</span>
      </Tooltip>
    ),
  };

  const operateColumn: TableColumnsType<ApiRecord>[number] = {
    title:  'Operate',
    key:    'operate',
    align:  'center',
    width:  108,
    render: (_, record) => (
      <Space size={6}>
        <Tooltip title="Update (coming soon)">
          <Button size="small" icon={<EditOutlined />} className="hp-btn-update" disabled />
        </Tooltip>
        <Tooltip title="Schema Mapping">
          <Button
            size="small"
            icon={<SwapOutlined />}
            className="hp-btn-mapping"
            onClick={() => navigate(`/apis/${record.key}/mapping`)}
          />
        </Tooltip>
        <Popconfirm
          title="Withdraw this API?"
          description="It will be removed from the repository."
          okText="Withdraw"
          okButtonProps={{ danger: true }}
          cancelText="Cancel"
          disabled={record.status === 'Withdrawn'}
          onConfirm={() => handleWithdraw(record)}
        >
          <Tooltip title={record.status === 'Withdrawn' ? 'Already withdrawn' : 'Withdraw'}>
            <Button
              size="small"
              icon={<DeleteOutlined />}
              className="hp-btn-withdraw"
              loading={withdrawingId === record.key}
              disabled={record.status === 'Withdrawn'}
            />
          </Tooltip>
        </Popconfirm>
      </Space>
    ),
  };

  const columns: TableColumnsType<ApiRecord> =
    listTab === 'all'
      ? [...baseColumns.slice(0, 3), creatorColumn, ...baseColumns.slice(3)]
      : [...baseColumns, operateColumn];

  return (
    <PublisherLayout>
      <div className="hp-card">
        <div className="hp-card__header">
          <div>
            <Title level={5} className="hp-card__title">
              API Publisher — Dashboard
            </Title>
            <span className="hp-card__desc">
              Browse all published APIs or manage your own submissions
            </span>
          </div>
            <div className="hp-card__header-actions">
              <Button icon={<SwapOutlined />} onClick={() => navigate('/schema-mapping')}>
                Schema Mapping
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
                Publish New API
              </Button>
            </div>
        </div>

        <Tabs
          activeKey={listTab}
          onChange={key => setListTab(key as ListTab)}
          items={[
            { key: 'all',  label: 'All APIs' },
            { key: 'mine', label: 'My APIs' },
          ]}
          className="hp-tabs"
        />

        <div className="hp-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Search by name, URL, creator, or status"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            className="hp-toolbar__search"
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            options={STATUS_FILTER_OPTIONS}
            className="hp-toolbar__status"
          />
        </div>

        <Table<ApiRecord>
          columns={columns}
          dataSource={filteredData}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          bordered
          className="hp-table"
          tableLayout="fixed"
          locale={{ emptyText: 'No APIs match your filters.' }}
        />
      </div>

      <APIInfoForm
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onComplete={() => {
          message.info('Submission saved. List will refresh when the backend list API is ready.');
        }}
      />
    </PublisherLayout>
  );
};

export default HomePage;
