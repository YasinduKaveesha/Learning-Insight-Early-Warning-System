import { describe, expect, it } from "vitest";
import {
  classifySignInError,
  classifyVerificationResponse,
} from "../authErrors";

// frontend_plan §11.0: the three auth failures must read DIFFERENTLY and
// never collapse into one "login failed".
describe("auth failures are three distinct paths", () => {
  it("401 -> token bad or expired, retry is reasonable", () => {
    const f = classifyVerificationResponse(401, {});
    expect(f.kind).toBe("token_invalid");
    expect(f.retryable).toBe(true);
    expect(f.message).toMatch(/session has expired/i);
  });

  it("403 -> valid token, not a teacher here: a message, not a retry loop", () => {
    const f = classifyVerificationResponse(403, {});
    expect(f.kind).toBe("not_a_teacher");
    expect(f.retryable).toBe(false);
    expect(f.message).toMatch(/not set up as a teacher/i);
  });

  it('409 stage "demo_pool" -> T3_DEMO_MODE is on when it should be off; do not retry', () => {
    const f = classifyVerificationResponse(409, { stage: "demo_pool" });
    expect(f.kind).toBe("demo_mode_on");
    expect(f.retryable).toBe(false);
    expect(f.message).toMatch(/demo mode/i);
  });

  it("409 without the demo_pool stage is not special-cased", () => {
    expect(classifyVerificationResponse(409, { stage: "something_else" }).kind).toBe("unknown");
    expect(classifyVerificationResponse(409, null).kind).toBe("unknown");
  });

  it("the three messages are mutually distinct", () => {
    const msgs = [
      classifyVerificationResponse(401, {}).message,
      classifyVerificationResponse(403, {}).message,
      classifyVerificationResponse(409, { stage: "demo_pool" }).message,
    ];
    expect(new Set(msgs).size).toBe(3);
  });

  it("never echoes a status code, token or raw body", () => {
    const body = { stage: "demo_pool", access_token: "eyJhbGciOi...", sub: "abc-123" };
    const f = classifyVerificationResponse(409, body);
    expect(f.message).not.toMatch(/eyJ|abc-123|409|token|sub/);
  });
});

describe("Supabase sign-in error mapping (gate 6: wrong password)", () => {
  it("HTTP 400 / 'Invalid login credentials' -> plain bad-credentials message", () => {
    const f = classifySignInError({ status: 400, message: "Invalid login credentials" });
    expect(f.kind).toBe("bad_credentials");
    expect(f.message).toMatch(/don't match/i);
    expect(f.message).not.toMatch(/400|stack|Error/);
  });

  it("missing error object -> unknown, still safe to render", () => {
    expect(classifySignInError(null).kind).toBe("unknown");
  });
});
