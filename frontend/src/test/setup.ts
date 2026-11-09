import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, expect } from "vitest";
import * as axeMatchers from "vitest-axe/matchers";
import { resetSessionForTests } from "@/api/session";
import { server } from "./server";

expect.extend(axeMatchers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  resetSessionForTests();
  localStorage.clear();
});
afterAll(() => server.close());
