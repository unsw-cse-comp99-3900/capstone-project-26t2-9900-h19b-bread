import { useState } from "react";
import { Button, Form, Input, Typography, message } from "antd";
import {
  UserOutlined,
  LockOutlined,
  MailOutlined,
  ApiOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { registerUser } from "../../services/register";
import { login } from "../../services/login";
import { setCredentials } from "../../store/authSlice";
import type { AppDispatch } from "../../store";
import "./Login.scss";

interface RegisterFormValues {
  name:            string;
  email:           string;
  password:        string;
  confirmPassword: string;
}

const Register = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: RegisterFormValues) => {
    setLoading(true);
    try {
      const res = await registerUser({
        name:     values.name,
        email:    values.email,
        password: values.password,
      });

      if (res.status === 'success') {
        const loginRes = await login({ email: values.email, password: values.password });
        if (loginRes.status === 'success' && loginRes.token && loginRes.user) {
          dispatch(setCredentials({ token: loginRes.token, user: loginRes.user }));
        }
        message.success('Account created successfully.');
        navigate('/homepage');
      } else {
        message.error(res.message || 'Registration failed.');
      }
    } catch {
      // HTTP-level errors (409, 400) are handled by the request interceptor
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
        <div className="login-root__card" style={{ width: 400 }}>
          <div className="login-root__form-header">
            <p className="login-root__form-title">Create Account</p>
            <span className="login-root__form-subtitle">
              Register your enterprise developer account
            </span>
          </div>

          <Form
            name="register"
            autoComplete="off"
            layout="vertical"
            size="large"
            onFinish={onFinish}
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
                { type: "email", message: "Please enter a valid email address!" },
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
              <Button type="primary" htmlType="submit" block loading={loading}>
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
