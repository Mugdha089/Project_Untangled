import { useState, type FormEvent } from "react";
import { LockKeyhole, Network, ShieldCheck, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { login, register, UntangleApiError } from "@/lib/untangle-api";
import "./auth-modal.css";

export interface AuthUser {
  userId: string;
  fullName: string;
  email: string;
  role: string;
}

interface AuthModalProps {
  open: boolean;
  onAuthenticated: (user: AuthUser, token: string) => void;
}

const DEMO_EMAIL = "demo@untangle.local";
const DEMO_PASSWORD = "untangle-demo-2026";

export function AuthModal({ open, onAuthenticated }: AuthModalProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const session =
        mode === "register"
          ? await register(email.trim().toLowerCase(), password, fullName.trim())
          : await login(email.trim().toLowerCase(), password);
      onAuthenticated(
        {
          userId: session.user.user_id,
          fullName: session.user.full_name,
          email: session.user.email,
          role: session.user.role,
        },
        session.access_token,
      );
    } catch (cause) {
      setError(
        cause instanceof UntangleApiError
          ? cause.message
          : `Unable to ${mode === "register" ? "create an account" : "sign in"}. Check that the backend is running and try again.`,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent
        className="auth-dialog"
        onEscapeKeyDown={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => event.preventDefault()}
      >
        <div className="auth-brand-mark">
          <Network size={23} />
        </div>
        <div className="auth-eyebrow">UNTANGLE ENGINEERING WORKSPACE</div>
        <DialogTitle className="auth-title">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </DialogTitle>
        <DialogDescription className="auth-description">
          {mode === "login"
            ? "Sign in to access your saved P&amp;ID digitisation runs."
            : "Create an account to save and revisit your P&amp;ID runs."}
        </DialogDescription>
        <div className="auth-mode-switch" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "active" : ""}
            onClick={() => {
              setMode("login");
              setError("");
            }}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "active" : ""}
            onClick={() => {
              setMode("register");
              setError("");
            }}
          >
            Create account
          </button>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "register" && (
            <label>
              Full name
              <input
                autoComplete="name"
                required
                maxLength={100}
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Your name"
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              required
              maxLength={254}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 12 : undefined}
              maxLength={128}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={mode === "register" ? "At least 12 characters" : "Your password"}
            />
          </label>
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" className="auth-submit" disabled={loading}>
            <LockKeyhole size={15} />
            {loading
              ? mode === "login"
                ? "Signing in…"
                : "Creating account…"
              : mode === "login"
                ? "Sign in to workspace"
                : "Create account"}
          </Button>
        </form>
        {mode === "login" && (
          <>
            <div className="auth-divider">
              <span>LOCAL HACKATHON DEMO ACCOUNT</span>
            </div>
            <Button
              type="button"
              variant="outline"
              className="auth-demo"
              disabled={loading}
              onClick={() => {
                setEmail(DEMO_EMAIL);
                setPassword(DEMO_PASSWORD);
                setError("");
              }}
            >
              <UserRound size={16} />
              <span>
                <strong>Fill demo credentials</strong>
                <small>{DEMO_EMAIL}</small>
              </span>
            </Button>
            <div className="auth-local-note">
              <ShieldCheck size={13} />
              Credentials are checked by the local backend. Demo password: {DEMO_PASSWORD}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
