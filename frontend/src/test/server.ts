import { setupServer } from "msw/node";

/** The network for tests. Each test adds the handlers it needs; unhandled requests fail loudly. */
export const server = setupServer();
