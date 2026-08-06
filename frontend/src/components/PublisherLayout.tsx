import React, { useEffect, useState } from 'react';
import { Layout, Menu, Button, Avatar, Divider, Tooltip } from 'antd';
import {
  UserOutlined,
  LogoutOutlined,
  CloudUploadOutlined,
  SwapOutlined,
  ApiOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { logout } from '../store/authSlice';
import { fetchAuthors } from '../store/authorsSlice';
import type { RootState, AppDispatch } from '../store';
import '../pages/Homepage/Homepage.scss';

const { Header, Sider, Content } = Layout;

const navItems = [
  { key: 'publisher', icon: <CloudUploadOutlined />, label: 'Dashboard' },
  { key: 'mapping',   icon: <SwapOutlined />,        label: 'Schema Mapping' },
];

interface Props {
  children: React.ReactNode;
  activeNav?: string;
}

const PublisherLayout: React.FC<Props> = ({ children, activeNav }) => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch<AppDispatch>();
  const user = useSelector((s: RootState) => s.auth.user);
  const token = useSelector((s: RootState) => s.auth.token);
  const authorsStatus = useSelector((s: RootState) => s.authors.status);

  const selectedKey = activeNav
    ?? (location.pathname.includes('mapping') ? 'mapping' : 'publisher');

  useEffect(() => {
    if (token && authorsStatus === 'idle') {
      void dispatch(fetchAuthors());
    }
  }, [token, authorsStatus, dispatch]);

  const handleLogout = () => {
    dispatch(logout());
    navigate('/login');
  };

  return (
    <Layout className="hp-root">
      <Sider
        className="hp-sider"
        width={220}
        collapsedWidth={64}
        collapsed={collapsed}
        collapsible={false}
      >
        <div className={`hp-sider__brand ${collapsed ? 'hp-sider__brand--collapsed' : ''}`}>
          <div className="hp-sider__brand-icon">
            <ApiOutlined />
          </div>
          {!collapsed && (
            <span className="hp-sider__brand-name">API Publisher</span>
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
            if (key === 'publisher') navigate('/homepage');
            if (key === 'mapping') navigate('/schema-mapping');
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
          <span className="hp-header__title">E-Invoice API Publisher</span>
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
