import { useState } from "react";
import { Button, Form, Input, Typography, message } from "antd";
import { UserOutlined, LockOutlined, ApiOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { login } from "../../services/login";
import type { LoginRequest } from "../../services/login";
import "./Login.scss";

const Login = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: LoginRequest) => {
    setLoading(true);
    try {
      const res = await login(values);
      if (res.status === 'success' && res.token) {
        localStorage.setItem('token', res.token);
        if (res.user) localStorage.setItem('user', JSON.stringify(res.user));
        message.success(res.message || 'Login successful');
        navigate('/homepage');
      } else {
        message.error(res.message || 'Invalid email or password.');
      }
    } catch {
      // HTTP-level errors are already handled by the request interceptor
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-root">
      {/* ── Left brand panel ── */}
      <div className="login-root__brand">
        <div className="login-root__logo-icon">
          <ApiOutlined />
        </div>
        <span className="login-root__sys-name">E-Invoice API Ecosystem</span>
        <span className="login-root__sys-sub">Discovery · Composition · Publisher</span>
      </div>

      {/* ── Right form panel ── */}
      <div className="login-root__form-panel">
        <div className="login-root__card">
          <div className="login-root__form-header">
            <p className="login-root__form-title">Sign In</p>
            <span className="login-root__form-subtitle">
              Access the enterprise API publishing portal
            </span>
          </div>

          <Form
            name="login"
            autoComplete="off"
            layout="vertical"
            size="large"
            onFinish={onFinish}
          >
            <Form.Item
              label="Email"
              name="email"
              rules={[
                { required: true, message: "Please input your email!" },
                { type: "email", message: "Please enter a valid email address!" },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder="your@enterprise.com" />
            </Form.Item>

            <Form.Item
              label="Password"
              name="password"
              rules={[{ required: true, message: "Please input your password!" }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="Enter your password"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button type="primary" htmlType="submit" block loading={loading}>
                Sign In
              </Button>
            </Form.Item>

            <div className="login-root__form-footer">
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                Don&apos;t have an account?
              </Typography.Text>
              <Button type="link" size="small" onClick={() => navigate("/register")}>
                Sign Up
              </Button>
            </div>
          </Form>
        </div>
      </div>
    </div>
  );
};

export default Login;
