import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

import { App } from "../App";
import { reiniciarDatosDeEjemplo } from "../datos/panel";

/**
 * Monta el panel en `url` con datos de ejemplo recién reiniciados y una caché
 * vacía, como si la empresa acabara de entrar.
 */
export function montarPanel(url = "/") {
  window.history.replaceState(null, "", url);
  reiniciarDatosDeEjemplo();
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <App />
    </QueryClientProvider>,
  );
}
