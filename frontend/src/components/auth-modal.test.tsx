import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthModal } from "./auth-modal";

describe("AuthModal", () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("submits credentials to backend login and forwards the returned token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          access_token: "signed-token",
          token_type: "bearer",
          expires_at: 123,
          user: {
            user_id: "u1",
            email: "demo@untangle.local",
            full_name: "Demo Engineer",
            role: "Process Engineer",
          },
        }),
        { status: 200 },
      ),
    );
    const onAuthenticated = vi.fn();
    render(<AuthModal open onAuthenticated={onAuthenticated} />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "demo@untangle.local" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pass" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in to workspace" }));
    await waitFor(() =>
      expect(onAuthenticated).toHaveBeenCalledWith(
        {
          userId: "u1",
          fullName: "Demo Engineer",
          email: "demo@untangle.local",
          role: "Process Engineer",
        },
        "signed-token",
      ),
    );
    expect(localStorage.length).toBe(0);
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/auth/login",
      expect.objectContaining({
        body: JSON.stringify({ email: "demo@untangle.local", password: "secret-pass" }),
      }),
    );
  });

  it("shows backend credential errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Invalid email or password." }), { status: 401 }),
    );
    render(<AuthModal open onAuthenticated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "demo@untangle.local" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in to workspace" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });

  it("registers an account through the backend and forwards its session", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          access_token: "registered-token",
          token_type: "bearer",
          expires_at: 456,
          user: {
            user_id: "u2",
            email: "new@example.test",
            full_name: "New User",
            role: "Process Engineer",
          },
        }),
        { status: 201 },
      ),
    );
    const onAuthenticated = vi.fn();
    render(<AuthModal open onAuthenticated={onAuthenticated} />);
    fireEvent.click(screen.getByRole("tab", { name: "Create account" }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New User" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-enough-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(onAuthenticated).toHaveBeenCalledWith(
        {
          userId: "u2",
          fullName: "New User",
          email: "new@example.test",
          role: "Process Engineer",
        },
        "registered-token",
      ),
    );
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/auth/register",
      expect.objectContaining({
        body: JSON.stringify({
          email: "new@example.test",
          password: "a-long-enough-password",
          full_name: "New User",
        }),
      }),
    );
  });
});
