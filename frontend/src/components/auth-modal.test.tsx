import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AuthModal } from "./auth-modal";

describe("AuthModal", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("signs in with the demo engineer and persists the profile", () => {
    const onAuthenticated = vi.fn();
    render(<AuthModal open onAuthenticated={onAuthenticated} />);

    fireEvent.click(screen.getByRole("button", { name: /Demo Engineer Login/i }));

    const expectedUser = {
      fullName: "Alex Morgan",
      email: "alex.morgan@untangle.demo",
      role: "Process Engineer",
    };
    expect(onAuthenticated).toHaveBeenCalledWith(expectedUser);
    expect(JSON.parse(localStorage.getItem("untangle.auth.session") ?? "null")).toEqual(
      expectedUser,
    );
  });

  it("registers a named local profile without persisting the password", () => {
    const onAuthenticated = vi.fn();
    render(<AuthModal open onAuthenticated={onAuthenticated} />);

    fireEvent.click(screen.getByRole("tab", { name: "Register" }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Sam Rivera" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "P&ID Specialist" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "sam@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "safe-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(onAuthenticated).toHaveBeenCalledWith({
      fullName: "Sam Rivera",
      email: "sam@example.com",
      role: "P&ID Specialist",
    });
    expect(localStorage.getItem("untangle.auth.session")).not.toContain("safe-password");
  });
});
