import { useState, type FormEvent } from "react";
import { LockKeyhole, Network, ShieldCheck, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import "./auth-modal.css";

export interface AuthUser {
  fullName: string;
  email: string;
  role: string;
}

interface AuthModalProps {
  open: boolean;
  onAuthenticated: (user: AuthUser) => void;
}

type AuthMode = "signin" | "register";

const DEMO_USER: AuthUser = {
  fullName: "Alex Morgan",
  email: "alex.morgan@untangle.demo",
  role: "Process Engineer",
};

function displayNameFromEmail(email: string): string {
  const localPart = email.split("@")[0] ?? "";
  const words = localPart
    .replace(/[._-]+/g, " ")
    .trim()
    .split(/\s+/);
  return (
    words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ") ||
    "Process Engineer"
  );
}

export function AuthModal({ open, onAuthenticated }: AuthModalProps) {
  const [mode, setMode] = useState<AuthMode>("signin");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("Process Engineer");
  const [error, setError] = useState("");

  const completeSignIn = (user: AuthUser) => {
    try {
      localStorage.setItem("untangle.auth.session", JSON.stringify(user));
      setError("");
      onAuthenticated(user);
    } catch {
      setError(
        "Unable to save your session in this browser. Check your browser storage settings and try again.",
      );
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const user: AuthUser =
      mode === "register"
        ? {
            fullName: fullName.trim(),
            email: email.trim().toLowerCase(),
            role: role.trim() || "Process Engineer",
          }
        : {
            fullName: displayNameFromEmail(email.trim()),
            email: email.trim().toLowerCase(),
            role: "Process Engineer",
          };
    completeSignIn(user);
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
          {mode === "signin" ? "Welcome back" : "Create your account"}
        </DialogTitle>
        <DialogDescription className="auth-description">
          {mode === "signin"
            ? "Sign in to access your P&ID digitisation workspace."
            : "Set up a local workspace profile to continue."}
        </DialogDescription>

        <div className="auth-mode-switch" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signin"}
            className={mode === "signin" ? "active" : ""}
            onClick={() => {
              setMode("signin");
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
            Register
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "register" && (
            <>
              <label>
                Full name
                <input
                  autoComplete="name"
                  required
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Alex Morgan"
                />
              </label>
              <label>
                Role
                <input
                  autoComplete="organization-title"
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                  placeholder="Process Engineer"
                />
              </label>
            </>
          )}
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="At least 8 characters"
            />
          </label>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" className="auth-submit">
            <LockKeyhole size={15} />
            {mode === "signin" ? "Sign in to workspace" : "Create account"}
          </Button>
        </form>

        <div className="auth-divider">
          <span>OR TRY A PRESENTATION ACCOUNT</span>
        </div>
        <Button
          type="button"
          variant="outline"
          className="auth-demo"
          onClick={() => completeSignIn(DEMO_USER)}
        >
          <UserRound size={16} />
          <span>
            <strong>Demo Engineer Login</strong>
            <small>Alex Morgan · Process Engineer</small>
          </span>
        </Button>

        <div className="auth-local-note">
          <ShieldCheck size={13} />
          Local demo sign-in; no server validates credentials and passwords are never stored.
        </div>
      </DialogContent>
    </Dialog>
  );
}
