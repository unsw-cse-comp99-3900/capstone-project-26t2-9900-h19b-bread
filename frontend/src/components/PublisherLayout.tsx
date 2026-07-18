import React, { useState } from 'react';
import { Layout, Menu, Button, Avatar, Divider, Tooltip } from 'antd';
import {
  UserOutlined,
  LogoutOutlined,
  SearchOutlined,
  PartitionOutlined,
  CloudUploadOutlined,
  ApiOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { logout } from '../store/authSlice';
import type { RootState, AppDispatch } from '../store';
import '../pages/Homepage/Homepage.scss';

const { Header, Sider, Content } = Layout;

const navItems = [
  { key: 'discovery',   icon: <SearchOutlined />,      label: 'Discovery Service' },
  { key: 'composition', icon: <PartitionOutlined />,   label: 'Composition Service' },
  { key: 'publisher',   icon: <CloudUploadOutlined />, label: 'API Publisher' },
];

interface Props {
  children: React.ReactNode;
  activeNav?: string;
}

const PublisherLayout: React.FC<Props> = ({ children, activeNav = 'publisher' }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [selectedKey, setSelectedKey] = useState(activeNav);
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const user = useSelector((s: RootState) => s.auth.user);

  const handleLogout = () => {
    dispatch(logout());
    navigate('/login');
  };

  return (
    <Layout className="hp-root">
      <Sider
        className="hp-sider"
        width={200}
        collapsedWidth={64}
        collapsed={collapsed}
        collapsible={false}
      >
        <div className={`hp-sider__brand ${collapsed ? 'hp-sider__brand--collapsed' : ''}`}>
          <div className="hp-sider__brand-icon">
            <ApiOutlined />
          </div>
          {!collapsed && (
            <span className="hp-sider__brand-name">API Ecosystem</span>
          )}
        </div>

        <Divider className="hp-sider__divider" />

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

        <Menu
          className="hp-menu"
          mode="inline"
          selectedKeys={[selectedKey]}
          inlineCollapsed={collapsed}
          onClick={({ key }) => {
            setSelectedKey(key);
            if (key === 'publisher') navigate('/homepage');
          }}
          items={navItems}
        />

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
        <Header className="hp-header">
          <Button type="primary" icon={<LogoutOutlined />} onClick={handleLogout}>
            Log out
          </Button>
        </Header>
        <Content className="hp-content">{children}</Content>
      </Layout>
    </Layout>
  );
};

export default PublisherLayout;
