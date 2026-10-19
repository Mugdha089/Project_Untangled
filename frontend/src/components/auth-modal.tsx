import { useState, type FormEvent } from "react";
import { LockKeyhole, Network, ShieldCheck, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { login, UntangleApiError } from "@/lib/untangle-api";
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
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const session = await login(email.trim().toLowerCase(), password);
      onAuthenticated({
        userId: session.user.user_id,
        fullName: session.user.full_name,
        email: session.user.email,
        role: session.user.role,
      }, session.access_token);
    } catch (cause) {
      setError(cause instanceof UntangleApiError
        ? cause.message
        : "Unable to sign in. Check that the backend is running and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent className="auth-dialog" onEscapeKeyDown={(event) => event.preventDefault()} onPointerDownOutside={(event) => event.preventDefault()}>
        <div className="auth-brand-mark"><Network size={23} /></div>
        <div className="auth-eyebrow">UNTANGLE ENGINEERING WORKSPACE</div>
        <DialogTitle className="auth-title">Welcome back</DialogTitle>
        <DialogDescription className="auth-description">Sign in to access your saved P&amp;ID digitisation runs.</DialogDescription>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Your password" /></label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <Button type="submit" className="auth-submit" disabled={loading}><LockKeyhole size={15} />{loading ? "Signing in…" : "Sign in to workspace"}</Button>
        </form>
        <div className="auth-divider"><span>LOCAL HACKATHON DEMO ACCOUNT</span></div>
        <Button type="button" variant="outline" className="auth-demo" disabled={loading} onClick={() => { setEmail(DEMO_EMAIL); setPassword(DEMO_PASSWORD); setError(""); }}>
          <UserRound size={16} /><span><strong>Fill demo credentials</strong><small>{DEMO_EMAIL}</small></span>
        </Button>
        <div className="auth-local-note"><ShieldCheck size={13} />Credentials are checked by the local backend. Demo password: {DEMO_PASSWORD}</div>
      </DialogContent>
    </Dialog>
  );
}
