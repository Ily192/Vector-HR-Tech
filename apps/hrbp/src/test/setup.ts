import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// `globals: false` ⇒ RTL no auto-limpia; lo hacemos explícito.
afterEach(() => {
  cleanup();
});
