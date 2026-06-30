import React, { useState, useEffect, useCallback } from 'react';
import {
  Layout,
  Menu,
  Button,
  Avatar,
  Table,
  Tag,
  Space,
  Typography,
  Divider,
  Tooltip,
  Popconfirm,
  message,
} from 'antd';
import {
  UserOutlined,
  LogoutOutlined,
  PlusOutlined,
  SearchOutlined,
  PartitionOutlined,
  CloudUploadOutlined,
  ApiOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  EditOutlined,
  SwapOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  MinusCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import type { TableColumnsType } from 'antd';
import APIInfoForm from '../../components/APIInfoForm';
import { logout } from '../../store/authSlice';
import type { RootState, AppDispatch } from '../../store';
import { withdrawApi } from '../../services/lifecycle';
import { getSubmissions } from '../../services/submission';
import type { SubmissionListItem } from '../../services/submission';
import './Homepage.scss';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

type ApiStatus = 'Published' | 'Rejected' | 'Draft' | 'Validating' | 'Withdrawn';

interface ApiRecord {
  key:        string;
  name:       string;
  protocol:   string;
  endpoint:   string;
  authMethod: string;
  category:   string;
  status:     ApiStatus;
}

function mapStatus(s: string): ApiStatus {
  const m: Record<string, ApiStatus> = {
    DRAFT:      'Draft',
    VALIDATING: 'Validating',
    REJECTED:   'Rejected',
    PUBLISHED:  'Published',
    WITHDRAWN:  'Withdrawn',
  };
  return m[s.toUpperCase()] ?? 'Draft';
}

function toRecord(item: SubmissionListItem): ApiRecord {
  return {
    key:        String(item.api_id),
    name:       item.api_name,
    protocol:   item.protocol_type,
    endpoint:   item.endpoint_url,
    authMethod: '—',
    category:   item.capability_category,
    status:     mapStatus(item.status),
  };
}

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

const navItems = [
  { key: 'discovery',   icon: <SearchOutlined />,      label: 'Discovery Service' },
  { key: 'composition', icon: <PartitionOutlined />,   label: 'Composition Service' },
  { key: 'publisher',   icon: <CloudUploadOutlined />, label: 'API Publisher' },
];

const HomePage: React.FC = () => {
  const [selectedKey, setSelectedKey] = useState('publisher');
  const [collapsed, setCollapsed]     = useState(false);
  const [modalOpen, setModalOpen]     = useState(false);
  const [tableData, setTableData]     = useState<ApiRecord[]>([]);
  const [loading, setLoading]         = useState(false);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);

  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const user     = useSelector((s: RootState) => s.auth.user);

  const loadSubmissions = useCallback(async () => {
    setLoading(true);
    try {
      const items = await getSubmissions();
      setTableData(items.map(toRecord));
    } catch {
      // error shown by request interceptor
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadSubmissions(); }, [loadSubmissions]);

  const handleLogout = () => {
    dispatch(logout());
    navigate('/login');
  };

  const handleWithdraw = async (record: ApiRecord) => {
    if (!user) return;
    setWithdrawingId(record.key);
    try {
      await withdrawApi(record.key, {
        actor_id: Number(user.user_id),
        reason:   'Withdrawn by publisher',
      });
      message.success(`"${record.name}" has been withdrawn.`);
      loadSubmissions();
    } catch {
      // error already shown by request interceptor
    } finally {
      setWithdrawingId(null);
    }
  };

  const handleFormComplete = () => { loadSubmissions(); };

  const columns: TableColumnsType<ApiRecord> = [
    {
      title:     'API Name',
      dataIndex: 'name',
      key:       'name',
      width:     180,
      ellipsis:  { showTitle: false },
      render: (name: string) => (
        <Tooltip title={name} placement="topLeft">
          <span style={{ cursor: 'default' }}>{name}</span>
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
      width:     150,
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
          <Tag
            icon={icon}
            color={color}
            style={{ fontWeight: 500, fontSize: 12 }}
          >
            {status}
          </Tag>
        );
      },
    },
    {
      title:  'Operate',
      key:    'operate',
      align:  'center',
      width:  108,
      render: (_, record) => (
        <Space size={6}>
          <Tooltip title="Update (coming soon)">
            <Button
              size="small"
              icon={<EditOutlined />}
              className="hp-btn-update"
              disabled
            />
          </Tooltip>
          <Tooltip title="Schema Mapping (coming soon)">
            <Button
              size="small"
              icon={<SwapOutlined />}
              className="hp-btn-mapping"
              disabled
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
    },
  ];

  return (
    <>
    <Layout className="hp-root">
      {/* ── Sidebar ── */}
      <Sider
        className="hp-sider"
        width={200}
        collapsedWidth={64}
        collapsed={collapsed}
        collapsible={false}
      >
        {/* Brand */}
        <div className={`hp-sider__brand ${collapsed ? 'hp-sider__brand--collapsed' : ''}`}>
          <div className="hp-sider__brand-icon">
            <ApiOutlined />
          </div>
          {!collapsed && (
            <span className="hp-sider__brand-name">API Ecosystem</span>
          )}
        </div>

        <Divider className="hp-sider__divider" />

        {/* Avatar */}
        <div className={`hp-sider__avatar-wrap ${collapsed ? 'hp-sider__avatar-wrap--collapsed' : ''}`}>
          <Avatar
            size={collapsed ? 36 : 52}
            icon={<UserOutlined />}
            className="hp-sider__avatar"
          />
          {!collapsed && (
            <span className="hp-sider__avatar-label">
              {user?.email ?? 'Enterprise User'}
            </span>
          )}
        </div>

        <Divider className="hp-sider__divider" />

        {/* Nav */}
        <Menu
          className="hp-menu"
          mode="inline"
          selectedKeys={[selectedKey]}
          inlineCollapsed={collapsed}
          onClick={({ key }) => setSelectedKey(key)}
          items={navItems}
        />

        {/* Collapse trigger */}
        <div className="hp-sider__footer">
          <Tooltip title={collapsed ? 'Expand' : 'Collapse'} placement="right">
            <button
              className="hp-sider__toggle"
              onClick={() => setCollapsed(!collapsed)}
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </button>
          </Tooltip>
        </div>
      </Sider>

      <Layout>
        {/* ── Header ── */}
        <Header className="hp-header">
          <Button
            type="primary"
            icon={<LogoutOutlined />}
            onClick={handleLogout}
          >
            Log out
          </Button>
        </Header>

        {/* ── Content ── */}
        <Content className="hp-content">
          <div className="hp-card">
            <div className="hp-card__header">
              <div>
                <Title level={5} className="hp-card__title">
                  API Publisher — My Published APIs
                </Title>
                <span className="hp-card__desc">
                  Manage your enterprise e-invoicing APIs submitted to the ecosystem repository
                </span>
              </div>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
                Publish New API
              </Button>
            </div>

            <Table<ApiRecord>
              columns={columns}
              dataSource={tableData}
              loading={loading}
              pagination={false}
              bordered
              className="hp-table"
              tableLayout="fixed"
            />
          </div>
        </Content>
      </Layout>
    </Layout>

    <APIInfoForm
      open={modalOpen}
      onClose={() => setModalOpen(false)}
      onComplete={handleFormComplete}
    />
    </>
  );
};

export default HomePage;
