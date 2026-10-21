import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom no implementa el scroll; `navegar()` lo usa al cambiar de pantalla.
window.scrollTo = () => {};

// `globals: false` ⇒ RTL no auto-limpia; lo hacemos explícito.
afterEach(() => {
  cleanup();
});
