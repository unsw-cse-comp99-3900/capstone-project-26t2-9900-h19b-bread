import React, { useState } from 'react';
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
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { TableColumnsType } from 'antd';
import './Homepage.scss';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

interface ApiRecord {
  key: string;
  name: string;
  protocol: 'REST' | 'SOAP';
  endpoint: string;
  authMethod: string;
  category: string;
  status: 'Published' | 'Rejected' | 'Draft';
}

const mockData: ApiRecord[] = [
  {
    key: '1',
    name: 'Invoice Creation API',
    protocol: 'REST',
    endpoint: 'https://api.acme.com/invoices',
    authMethod: 'OAuth 2.0',
    category: 'Invoice Creation',
    status: 'Published',
  },
  {
    key: '2',
    name: 'PEPPOL Validation Service',
    protocol: 'SOAP',
    endpoint: 'https://svc.acme.com/validate',
    authMethod: 'mTLS',
    category: 'Validation',
    status: 'Rejected',
  },
  {
    key: '3',
    name: 'Invoice Archive API',
    protocol: 'REST',
    endpoint: 'https://api.acme.com/archive',
    authMethod: 'API Key',
    category: 'Archiving',
    status: 'Draft',
  },
];

const statusColorMap: Record<string, string> = {
  Published: 'success',
  Rejected: 'error',
  Draft: 'warning',
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
  const navigate = useNavigate();

  const columns: TableColumnsType<ApiRecord> = [
    {
      title: 'API Name',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: 'Protocol',
      dataIndex: 'protocol',
      key: 'protocol',
      align: 'center',
      width: 90,
      render: (protocol: string) => (
        <Tag color={protocolColorMap[protocol]}>{protocol}</Tag>
      ),
    },
    {
      title: 'Endpoint URL',
      dataIndex: 'endpoint',
      key: 'endpoint',
      ellipsis: true,
    },
    {
      title: 'Auth Method',
      dataIndex: 'authMethod',
      key: 'authMethod',
      align: 'center',
      width: 110,
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      align: 'center',
      width: 140,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      align: 'center',
      width: 110,
      render: (status: string) => (
        <Tag color={statusColorMap[status]}>{status}</Tag>
      ),
    },
    {
      title: 'Operate',
      key: 'operate',
      align: 'center',
      width: 180,
      render: () => (
        <Space size={4}>
          <Button size="small" className="hp-btn-update">Update</Button>
          <Button size="small" className="hp-btn-mapping">Mapping</Button>
          <Button size="small" className="hp-btn-withdraw">Withdraw</Button>
        </Space>
      ),
    },
  ];

  return (
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
            <span className="hp-sider__avatar-label">Enterprise User</span>
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
            onClick={() => navigate('/login')}
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
              <Button type="primary" icon={<PlusOutlined />}>
                Publish New API
              </Button>
            </div>

            <Table<ApiRecord>
              columns={columns}
              dataSource={mockData}
              pagination={false}
              bordered
              className="hp-table"
              scroll={{ x: 900 }}
            />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

export default HomePage;
