import { Button, Form, Input, Typography } from "antd";
import {
  UserOutlined,
  LockOutlined,
  MailOutlined,
  BarChartOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import "./Login.scss";

const Register = () => {
  const navigate = useNavigate();

  return (
    <div className="login-root">
      {/* ── Left brand panel ── */}
      <div className="login-root__brand">
        {/* <div className="login-root__logo-icon">
          <BarChartOutlined />
        </div> */}
        <span className="login-root__sys-name">API Platform</span>
        <span className="login-root__sys-sub">Dashboard System</span>
      </div>

      {/* ── Right form panel ── */}
      <div className="login-root__form-panel">
        <div className="login-root__card" style={{ width: 400 }}>
          <div className="login-root__form-header">
            <p className="login-root__form-title">Create Account</p>
            <span className="login-root__form-subtitle">
              Fill in the details below to get started
            </span>
          </div>

          <Form
            name="register"
            autoComplete="off"
            layout="vertical"
            size="large"
          >
            <Form.Item
              label="Name"
              name="name"
              rules={[
                { required: true, message: "Please input your name!" },
                { min: 2, message: "Name must be at least 2 characters!" },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder="Your full name" />
            </Form.Item>

            <Form.Item
              label="Email"
              name="email"
              rules={[
                { required: true, message: "Please input your email!" },
                {
                  type: "email",
                  message: "Please enter a valid email address!",
                },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="your@email.com" />
            </Form.Item>

            <Form.Item
              label="Password"
              name="password"
              rules={[
                { required: true, message: "Please input your password!" },
                { min: 6, message: "Password must be at least 6 characters!" },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="Create a password"
              />
            </Form.Item>

            <Form.Item
              label="Confirm Password"
              name="confirmPassword"
              dependencies={["password"]}
              rules={[
                { required: true, message: "Please confirm your password!" },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue("password") === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(
                      new Error("The two passwords do not match!"),
                    );
                  },
                }),
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="Confirm your password"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button type="primary" htmlType="submit" block>
                Sign Up
              </Button>
            </Form.Item>

            <div className="login-root__form-footer">
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                Already have an account?
              </Typography.Text>
              <Button
                type="link"
                size="small"
                onClick={() => navigate("/login")}
              >
                Sign In
              </Button>
            </div>
          </Form>
        </div>
      </div>
    </div>
  );
};

export default Register;
