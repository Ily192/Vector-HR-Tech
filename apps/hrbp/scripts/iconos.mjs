/**
 * Los PNG de la app instalable (`public/iconos`), desde `public/favicon.svg`.
 *
 *   node apps/hrbp/scripts/iconos.mjs
 *
 * Los PNG van en el repo: el build no los genera. Se vuelven a correr solo si cambia el
 * favicon. Usa el Chromium de Playwright del paquete e2e
 * (`pnpm --filter @fluveai/e2e e2e:install`), para no sumarle una dependencia al panel.
 *
 * - `panel-*`: el favicon tal cual (tinta con la V en aqua), para `manifest.webmanifest`.
 * - `admin-*`: los colores al revés (aqua con la V en tinta), para `admin.webmanifest`:
 *   con las dos instaladas en el teléfono se distinguen de un vistazo.
 * - `*-maskable-512` y `*-apple-touch-icon` (180) llenan el cuadro, sin esquinas
 *   transparentes: Android recorta el maskable con su forma y iOS redondea el suyo (las
 *   esquinas transparentes las pinta de negro). La V queda dentro del círculo seguro del
 *   80% que pide el maskable.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";

const PANEL = new URL("../", import.meta.url);
const SALIDA = new URL("public/iconos/", PANEL);
const requerir = createRequire(new URL("../../../packages/e2e/package.json", import.meta.url));
const { chromium } = requerir("@playwright/test");

const favicon = await readFile(new URL("public/favicon.svg", PANEL), "utf8");
const color = (patron) => {
  const valor = patron.exec(favicon)?.[1];
  if (!valor) throw new Error(`favicon.svg cambió: no encuentro ${patron}`);
  return valor;
};
const TINTA = color(/<rect[^>]*fill="(#[0-9A-Fa-f]{6})"/);
const AQUA = color(/stroke="(#[0-9A-Fa-f]{6})"/);
const V = color(/<path d="([^"]+)"/);

const svg = ({ fondo, trazo, redondo }, lado) =>
  [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${lado}" height="${lado}" viewBox="0 0 64 64">`,
    `<rect width="64" height="64"${redondo ? ' rx="15"' : ""} fill="${fondo}"/>`,
    `<path d="${V}" fill="none" stroke="${trazo}" stroke-width="7.5"`,
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
  ].join("");

const PANEL_COLORES = { fondo: TINTA, trazo: AQUA };
const ADMIN_COLORES = { fondo: AQUA, trazo: TINTA };

const ICONOS = [
  ["panel-192.png", 192, { ...PANEL_COLORES, redondo: true }],
  ["panel-512.png", 512, { ...PANEL_COLORES, redondo: true }],
  ["panel-maskable-512.png", 512, { ...PANEL_COLORES, redondo: false }],
  ["panel-apple-touch-icon.png", 180, { ...PANEL_COLORES, redondo: false }],
  ["admin-192.png", 192, { ...ADMIN_COLORES, redondo: true }],
  ["admin-512.png", 512, { ...ADMIN_COLORES, redondo: true }],
  ["admin-maskable-512.png", 512, { ...ADMIN_COLORES, redondo: false }],
  ["admin-apple-touch-icon.png", 180, { ...ADMIN_COLORES, redondo: false }],
];

await mkdir(SALIDA, { recursive: true });
const navegador = await chromium.launch();
try {
  const pagina = await navegador.newPage({ deviceScaleFactor: 1 });
  for (const [nombre, lado, opciones] of ICONOS) {
    await pagina.setViewportSize({ width: lado, height: lado });
    await pagina.setContent(
      `<!doctype html><html><body style="margin:0;background:transparent">${svg(opciones, lado)}</body></html>`,
    );
    const png = await pagina.screenshot({
      omitBackground: true,
      clip: { x: 0, y: 0, width: lado, height: lado },
    });
    await writeFile(new URL(nombre, SALIDA), png);
    console.info(`public/iconos/${nombre} (${lado}×${lado}, ${png.length} bytes)`);
  }
} finally {
  await navegador.close();
}
