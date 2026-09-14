import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { authFailure } from "../../auth/authErrors";

const signIn = vi.fn();
const signUp = vi.fn();
vi.mock("../../auth/SessionProvider", () => ({
  useSession: () => ({
    status: "unauthenticated",
    session: null,
    isAuthed: false,
    signIn,
    signUp,
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

afterEach(() => {
  signIn.mockReset();
  signUp.mockReset();
});

describe("LoginRoute (frontend_plan §11.0)", () => {
  it("opens on log in: email and password, and still no reset or remember-me", () => {
    // B6.4 added account creation, so "no sign-up" is no longer true -- it is a
    // second TAB on the same card. Password reset and remember-me are still out.
    renderLogin();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.queryByLabelText("Your name")).not.toBeInTheDocument();
    expect(screen.queryByText(/forgot|reset|remember me/i)).not.toBeInTheDocument();
  });

  it("the create tab asks for a name, an email and a password — and nothing else", async () => {
    renderLogin();
    await userEvent.click(screen.getByRole("tab", { name: "Create" }));

    // Step 1 shows the same NUMBER of fields log in does, so the card does not
    // change height when the teacher switches tab (the student app's reasoning).
    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    // No field the dashboard has no use for.
    expect(screen.queryByLabelText(/gender|school|role/i)).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Your name"), "Ms Perera");
    await userEvent.type(screen.getByLabelText("Email"), "teacher@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    // Step 2: password and its confirmation, and a way back.
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
    expect(screen.queryByLabelText("Your name")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
  });

  async function fillCreateForm(password: string, confirmation = password) {
    await userEvent.click(screen.getByRole("tab", { name: "Create" }));
    await userEvent.type(screen.getByLabelText("Your name"), "Ms Perera");
    await userEvent.type(screen.getByLabelText("Email"), "teacher@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.type(screen.getByLabelText("Password"), password);
    await userEvent.type(screen.getByLabelText("Confirm password"), confirmation);
  }

  it("creating an account passes the name through and lands on the dashboard", async () => {
    signUp.mockResolvedValue({ ok: true, needsConfirmation: false });
    renderLogin();
    await fillCreateForm("correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(signUp).toHaveBeenCalledWith("Ms Perera", "teacher@example.com", "correct-horse");
    expect(await screen.findByText("Home screen")).toBeInTheDocument();
  });

  it("going Back keeps what was already typed", async () => {
    renderLogin();
    await fillCreateForm("correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(screen.getByLabelText("Your name")).toHaveValue("Ms Perera");
    expect(screen.getByLabelText("Email")).toHaveValue("teacher@example.com");
  });

  it("will not submit an account with a too-short password", async () => {
    renderLogin();
    await fillCreateForm("short");

    // Disabled rather than accepting the click and answering with an error.
    expect(screen.getByRole("button", { name: "Create account" })).toBeDisabled();
    expect(signUp).not.toHaveBeenCalled();
  });

  it("mismatched passwords are TOLD, not silently blocked", async () => {
    renderLogin();
    await fillCreateForm("correct-horse", "correct-mouse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The passwords do not match.");
    expect(signUp).not.toHaveBeenCalled();
  });

  it("a failed sign-up shows its own plain-language reason, never a raw error", async () => {
    signUp.mockResolvedValue({ ok: false, failure: authFailure("email_taken") });
    renderLogin();
    await fillCreateForm("correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("An account already exists");
    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
  });

  it("when the project requires email confirmation it says so and returns to log in", async () => {
    signUp.mockResolvedValue({ ok: true, needsConfirmation: true });
    renderLogin();
    await fillCreateForm("correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Check your email");
    // Back on the log-in tab, with nothing signed in.
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
  });

  it("successful sign-in navigates home", async () => {
    signIn.mockResolvedValue(null);
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "teacher01@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Home screen")).toBeInTheDocument();
  });

  it("wrong password: plain-language error, no stack, no token echoed (gate 6)", async () => {
    signIn.mockResolvedValue(authFailure("bad_credentials"));
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "teacher01@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

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
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not set up as a teacher/i);
  });
});
