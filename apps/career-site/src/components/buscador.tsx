import { Button } from "@vortex/ui";
import { MapPin, Search } from "lucide-react";
import Form from "next/form";

import type { FiltrosVacantes } from "../lib/filtros";

/**
 * Buscador por puesto y ubicación. Es un formulario GET a `/vacantes`: con
 * `next/form` navega sin recargar y, sin JavaScript, funciona como un form normal.
 */
export function Buscador({ filtros = {} }: { filtros?: FiltrosVacantes }) {
  return (
    <search aria-label="Buscar vacantes" className="block w-full max-w-3xl">
      <Form
        action="/vacantes"
        className="flex w-full flex-col gap-2 rounded-[20px] bg-white p-2 shadow-float sm:flex-row"
      >
        <label className="flex min-h-[52px] flex-1 items-center gap-2.5 rounded-[14px] px-3.5 text-mist-600 focus-within:ring-2 focus-within:ring-aqua-500">
          <Search aria-hidden="true" className="h-[18px] w-[18px] shrink-0" />
          <span className="sr-only">Puesto o palabra clave</span>
          <input
            name="q"
            defaultValue={filtros.q}
            placeholder="Puesto o palabra clave"
            className="w-full border-0 bg-transparent p-0 text-[15.5px] shadow-none focus:ring-0 text-ink-900 outline-none placeholder:text-mist-500"
          />
        </label>
        <label className="flex min-h-[52px] flex-1 items-center gap-2.5 border-mist-200 px-3.5 text-mist-600 focus-within:ring-2 focus-within:ring-aqua-500 max-sm:border-t sm:rounded-none sm:border-l">
          <MapPin aria-hidden="true" className="h-[18px] w-[18px] shrink-0" />
          <span className="sr-only">Ciudad o «remoto»</span>
          <input
            name="ubicacion"
            defaultValue={filtros.ubicacion}
            placeholder="Ciudad o «remoto»"
            className="w-full border-0 bg-transparent p-0 text-[15.5px] shadow-none focus:ring-0 text-ink-900 outline-none placeholder:text-mist-500"
          />
        </label>
        {filtros.modalidad && <input type="hidden" name="modalidad" value={filtros.modalidad} />}
        {filtros.conSalario && <input type="hidden" name="salario" value="1" />}
        <Button type="submit" size="lg">
          Buscar
        </Button>
      </Form>
    </search>
  );
}
