"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";

const DEMO = [
  { label: "Operator — Maria Chen", email: "maria@sunnyside.example" },
  { label: "Parent — Ava's family", email: "ava.parent@example.com" },
];

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    setLoading(false);
    if (!res || res.error) {
      setError("That email and password don't match. Please try again.");
      return;
    }
    // Middleware routes operators to /operator and parents to /.
    window.location.href = "/";
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#F7F9FB",
        display: "grid",
        placeItems: "center",
        padding: 20,
      }}
    >
      <div style={{ width: 380, maxWidth: "100%" }}>
        {/* Brand */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            justifyContent: "center",
            marginBottom: 22,
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 14,
              background: "#5463D6",
              display: "grid",
              placeItems: "center",
              boxShadow: "0 6px 16px -4px rgba(84,99,214,.6)",
            }}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#FFFFFF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
          </div>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#18181D" }}>
            Sunnyside Front Desk
          </div>
        </div>

        <form
          onSubmit={submit}
          style={{
            background: "#FFFFFF",
            border: "1px solid #EBEFF4",
            borderRadius: 20,
            padding: 24,
            boxShadow: "0 20px 50px -24px rgba(30,37,73,.3)",
          }}
        >
          <div style={{ fontSize: 20, fontWeight: 800, color: "#18181D" }}>
            Sign in
          </div>
          <div style={{ fontSize: 13.5, color: "#5C5E6A", marginTop: 4 }}>
            Welcome back — sign in to continue.
          </div>

          <label style={labelStyle}>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
            style={inputStyle}
          />

          <label style={labelStyle}>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            style={inputStyle}
          />

          {error && (
            <div
              style={{
                marginTop: 12,
                fontSize: 13,
                color: "#CF193A",
                background: "#FDEFF2",
                border: "1px solid #F8CBD6",
                borderRadius: 10,
                padding: "9px 12px",
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="fd-primary"
            style={{
              width: "100%",
              marginTop: 18,
              background: "#5463D6",
              color: "#FFFFFF",
              border: "none",
              borderRadius: 12,
              padding: "12px 0",
              fontSize: 15,
              fontWeight: 700,
              cursor: loading ? "default" : "pointer",
              opacity: loading ? 0.7 : 1,
              transition: "background .15s",
            }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>

          {/* Demo helper (prototype only) */}
          <div
            style={{
              marginTop: 18,
              paddingTop: 16,
              borderTop: "1px solid #F0F3F8",
            }}
          >
            <div
              style={{
                fontSize: 11.5,
                fontWeight: 700,
                letterSpacing: ".04em",
                textTransform: "uppercase",
                color: "#737685",
                marginBottom: 9,
              }}
            >
              Demo accounts (password: demo1234)
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  className="fd-chip"
                  onClick={() => {
                    setEmail(d.email);
                    setPassword("demo1234");
                  }}
                  style={{
                    textAlign: "left",
                    padding: "9px 12px",
                    borderRadius: 10,
                    border: "1px solid #E3E8FF",
                    background: "#F5F7FF",
                    color: "#5463D6",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "all .15s",
                  }}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12.5,
  fontWeight: 700,
  color: "#5C5E6A",
  margin: "16px 0 6px",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "#F7F9FB",
  border: "1px solid #EBEFF4",
  borderRadius: 12,
  padding: "12px 14px",
  fontSize: 14.5,
  color: "#18181D",
  outline: "none",
};
