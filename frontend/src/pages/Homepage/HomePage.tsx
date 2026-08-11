import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
  EyeOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { TableColumnsType } from 'antd';
import APIInfoForm from '../../components/APIInfoForm';
import PublisherLayout from '../../components/PublisherLayout';
import type { RootState } from '../../store';
import type { ApiRecord, ApiStatus } from '../../types/api';
import { mapStatus } from '../../types/api';
import {
  getSubmissions,
  type SubmissionListItem,
} from '../../services/submission';
import { withdrawApi } from '../../services/lifecycle';
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

function toRecord(item: SubmissionListItem): ApiRecord {
  return {
    key:          String(item.api_id),
    name:         item.api_name,
    protocol:     item.protocol_type || 'REST',
    endpoint:     item.endpoint_url || '—',
    authMethod:   '—',
    category:     item.capability_category || '—',
    status:       mapStatus(item.status),
    creator:      item.submitted_by_name?.trim() || `user #${item.submitted_by}`,
    creatorId:    String(item.submitted_by),
    description:  '',
    inputFormat:  item.input_format || '—',
    outputFormat: item.output_format || '—',
    createdAt:    item.created_at,
    updatedAt:    item.updated_at,
    history:      [],
    isMine:       item.is_current_user_api,
    canManage:    item.can_manage,
  };
}

const HomePage: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editApiId, setEditApiId] = useState<string | null>(null);
  const [listTab, setListTab] = useState<ListTab>('all');
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [authorFilter, setAuthorFilter] = useState<string>('all');
  const [tableData, setTableData] = useState<ApiRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const navigate = useNavigate();
  const user = useSelector((s: RootState) => s.auth.user);
  const authors = useSelector((s: RootState) => s.authors.items);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const items = await getSubmissions();
      setTableData(items.map(toRecord));
    } catch {
      // interceptor shows error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getSubmissions()
      .then(items => {
        if (active) setTableData(items.map(toRecord));
      })
      .catch(() => {
        // interceptor shows error
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const authorOptions = useMemo(
    () => [
      { value: 'all', label: 'All creators' },
      ...authors.map(a => ({
        value: String(a.user_id),
        label: a.name || `user #${a.user_id}`,
      })),
    ],
    [authors],
  );

  const filteredData = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    return tableData.filter(row => {
      if (listTab === 'mine' && !row.isMine) return false;
      if (statusFilter !== 'all' && row.status !== statusFilter) return false;
      if (authorFilter !== 'all' && row.creatorId !== authorFilter) return false;
      if (!q) return true;
      const haystack = [
        row.name,
        row.endpoint,
        row.creator,
        row.creatorId,
        row.status,
        row.category,
        row.protocol,
        row.inputFormat,
        row.outputFormat,
        row.authMethod,
        row.key,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [tableData, listTab, keyword, statusFilter, authorFilter]);

  const handleWithdraw = async (record: ApiRecord) => {
    if (!user) return;
    setWithdrawingId(record.key);
    try {
      await withdrawApi(record.key, {
        actor_id: Number(user.user_id),
        reason:   'Withdrawn by publisher',
      });
      message.success(`"${record.name}" has been withdrawn.`);
      await loadList();
    } catch {
      // interceptor shows error
    } finally {
      setWithdrawingId(null);
    }
  };

  const baseColumns: TableColumnsType<ApiRecord> = [
    {
      title:     'API Name',
      dataIndex: 'name',
      key:       'name',
      width:     280,
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
        <Tag color={protocolColorMap[protocol] ?? 'default'}>{protocol}</Tag>
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

  const browseColumn: TableColumnsType<ApiRecord>[number] = {
    title:  'Actions',
    key:    'browse',
    align:  'center',
    width:  96,
    render: (_, record) => (
      <Space size={6}>
        <Tooltip title="View details">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/apis/${record.key}`)}
          />
        </Tooltip>
        <Tooltip title="Schema mapping for this API">
          <Button
            size="small"
            icon={<SwapOutlined />}
            className="hp-btn-mapping"
            onClick={() => navigate(`/apis/${record.key}/mapping`)}
          />
        </Tooltip>
      </Space>
    ),
  };

  const operateColumn: TableColumnsType<ApiRecord>[number] = {
    title:  'Actions',
    key:    'operate',
    align:  'center',
    width:  132,
    render: (_, record) => {
      const canManage = !!record.canManage;
      const canUpdate =
        canManage &&
        record.status !== 'Withdrawn' &&
        record.status !== 'Validating';
      return (
        <Space size={6}>
          <Tooltip title="View details">
            <Button
              size="small"
              icon={<EyeOutlined />}
              onClick={() => navigate(`/apis/${record.key}`)}
            />
          </Tooltip>
          <Tooltip
            title={
              !canManage
                ? 'No permission to update'
                : record.status === 'Withdrawn'
                  ? 'Withdrawn APIs cannot be updated'
                  : record.status === 'Validating'
                    ? 'Finish validation before updating'
                    : 'Update'
            }
          >
            <Button
              size="small"
              icon={<EditOutlined />}
              className="hp-btn-update"
              disabled={!canUpdate}
              onClick={() => {
                setEditApiId(record.key);
                setModalOpen(true);
              }}
            />
          </Tooltip>
          <Tooltip title="Schema mapping for this API">
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
            disabled={!canManage || record.status === 'Withdrawn'}
            onConfirm={() => void handleWithdraw(record)}
          >
            <Tooltip
              title={
                !canManage
                  ? 'No permission to withdraw'
                  : record.status === 'Withdrawn'
                    ? 'Already withdrawn'
                    : 'Withdraw'
              }
            >
              <Button
                size="small"
                icon={<DeleteOutlined />}
                className="hp-btn-withdraw"
                loading={withdrawingId === record.key}
                disabled={!canManage || record.status === 'Withdrawn'}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      );
    },
  };

  const columns: TableColumnsType<ApiRecord> =
    listTab === 'all'
      ? [...baseColumns.slice(0, 3), creatorColumn, ...baseColumns.slice(3), browseColumn]
      : [...baseColumns, operateColumn];

  return (
    <PublisherLayout>
      <div className="hp-card">
        <div className="hp-card__header">
          <div>
            <Title level={5} className="hp-card__title">
              Dashboard
            </Title>
            <span className="hp-card__desc">
              Browse enterprise APIs or manage your own submissions
            </span>
          </div>
          <div className="hp-card__header-actions">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditApiId(null);
                setModalOpen(true);
              }}
            >
              Publish New API
            </Button>
          </div>
        </div>

        <Tabs
          activeKey={listTab}
          onChange={key => {
            setListTab(key as ListTab);
            setPage(1);
          }}
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
            placeholder="Search by name, URL, creator, status, protocol…"
            value={keyword}
            onChange={e => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            className="hp-toolbar__search"
          />
          <Select
            value={statusFilter}
            onChange={value => {
              setStatusFilter(value);
              setPage(1);
            }}
            options={STATUS_FILTER_OPTIONS}
            className="hp-toolbar__status"
          />
          {listTab === 'all' && (
            <Select
              value={authorFilter}
              onChange={value => {
                setAuthorFilter(value);
                setPage(1);
              }}
              options={authorOptions}
              className="hp-toolbar__status"
              showSearch
              optionFilterProp="label"
            />
          )}
        </div>

        <Table<ApiRecord>
          columns={columns}
          dataSource={filteredData}
          loading={loading}
          pagination={{
            current: page,
            pageSize: 8,
            showSizeChanger: false,
            onChange: next => setPage(next),
          }}
          bordered
          className="hp-table"
          tableLayout="fixed"
          locale={{ emptyText: 'No APIs match your filters.' }}
        />
      </div>

      <APIInfoForm
        open={modalOpen}
        editApiId={editApiId}
        onClose={() => {
          setModalOpen(false);
          setEditApiId(null);
        }}
        onComplete={() => {
          void loadList();
        }}
      />
    </PublisherLayout>
  );
};

export default HomePage;
