import { describe, expect, it } from "vitest";
import {
  ApiRequestError,
  NotAuthorizedError,
  apiError,
  isNotAuthorizedError,
} from "../apiError";

describe("apiError — a 403 must stay distinguishable from every other failure", () => {
  it("builds a NotAuthorizedError for 403 and a plain ApiRequestError otherwise", () => {
    expect(apiError("/home", 403)).toBeInstanceOf(NotAuthorizedError);
    for (const status of [400, 401, 404, 409, 500, 503]) {
      const error = apiError("/home", status);
      expect(error).toBeInstanceOf(ApiRequestError);
      expect(isNotAuthorizedError(error)).toBe(false);
    }
  });

  it("keeps the status and path on the error, so a caller never re-parses a message", () => {
    const error = apiError("/classes/abc/cohort", 503);
    expect(error.status).toBe(503);
    expect(error.path).toBe("/classes/abc/cohort");
  });

  it("preserves the exact message the untyped Error used to carry", () => {
    expect(apiError("/home", 500).message).toBe("Request to /home failed with HTTP 500");
  });

  it("every API failure is still an Error — ErrorState's contract is unchanged", () => {
    expect(apiError("/home", 403)).toBeInstanceOf(Error);
    expect(apiError("/home", 500)).toBeInstanceOf(Error);
  });

  it("recognises a 403 by its code, not instanceof — it survives a module boundary", () => {
    const crossedABoundary = JSON.parse(
      JSON.stringify({ code: "NOT_AUTHORIZED", message: "x" }),
    ) as unknown;
    expect(isNotAuthorizedError(crossedABoundary)).toBe(true);
  });

  it("does not mistake null, a string or an unrelated error for a 403", () => {
    expect(isNotAuthorizedError(null)).toBe(false);
    expect(isNotAuthorizedError("403")).toBe(false);
    expect(isNotAuthorizedError(new Error("403 Forbidden"))).toBe(false);
  });
});
