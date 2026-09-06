import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { authFailure } from "../../auth/authErrors";

const signIn = vi.fn();
vi.mock("../../auth/SessionProvider", () => ({
  useSession: () => ({
    status: "unauthenticated",
    session: null,
    isAuthed: false,
    signIn,
    signOut: vi.fn(),
  }),
}));

const { default: LoginRoute } = await import("../login/LoginRoute");

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/" element={<div>Home screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => signIn.mockReset());

describe("LoginRoute (frontend_plan §11.0)", () => {
  it("is one email/password form — no sign-up, reset or remember-me", () => {
    renderLogin();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.queryByText(/sign up|forgot|reset|remember me/i)).not.toBeInTheDocument();
  });

  it("successful sign-in navigates home", async () => {
    signIn.mockResolvedValue(null);
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "teacher01@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Home screen")).toBeInTheDocument();
  });

  it("wrong password: plain-language error, no stack, no token echoed (gate 6)", async () => {
    signIn.mockResolvedValue(authFailure("bad_credentials"));
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "teacher01@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/don't match/i);
    expect(alert).not.toHaveTextContent(/eyJ|stack|Error:|401|403/);
    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
  });

  it("a 403 (not a teacher here) reads differently from a wrong password", async () => {
    signIn.mockResolvedValue(authFailure("not_a_teacher"));
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "someone@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "whatever");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not set up as a teacher/i);
  });
});
