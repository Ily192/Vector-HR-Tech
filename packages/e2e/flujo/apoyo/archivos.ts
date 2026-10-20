/**
 * Un PDF mínimo y válido con una línea de texto por línea, en Helvetica (el mismo
 * que `_pdf` en los tests del hr-engine). Sin líneas sale una página sin texto:
 * para el worker es un CV escaneado, ilegible. El texto va en ASCII: Helvetica sin
 * `/Encoding` no mapea bien los acentos.
 */
export function pdf(...lineas: string[]): Buffer {
  const texto = lineas.map((linea) => `(${linea}) Tj 0 -14 Td`).join(" ");
  const contenido = `BT /F1 12 Tf 72 720 Td ${texto} ET`;
  const objetos = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R" +
      " /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${Buffer.byteLength(contenido, "latin1")} >>\nstream\n${contenido}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let salida = "%PDF-1.4\n";
  const posiciones: number[] = [];
  objetos.forEach((objeto, i) => {
    posiciones.push(Buffer.byteLength(salida, "latin1"));
    salida += `${i + 1} 0 obj\n${objeto}\nendobj\n`;
  });
  const xref = Buffer.byteLength(salida, "latin1");
  salida += `xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n`;
  for (const posicion of posiciones) salida += `${String(posicion).padStart(10, "0")} 00000 n \n`;
  salida += `trailer\n<< /Size ${objetos.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(salida, "latin1");
}

const FIN_DEL_DIRECTORIO = 0x06054b50;
const ENTRADA_DEL_DIRECTORIO = 0x02014b50;

/** Los nombres de los archivos de un .zip, en su orden, leídos del directorio central. */
export function nombresEnElZip(zip: Buffer): string[] {
  // El registro final mide 22 bytes más un comentario de hasta 64 KB.
  let fin = -1;
  for (let i = zip.length - 22; i >= Math.max(0, zip.length - 22 - 0xffff); i--) {
    if (zip.readUInt32LE(i) === FIN_DEL_DIRECTORIO) {
      fin = i;
      break;
    }
  }
  if (fin < 0) throw new Error("No es un .zip: no tiene directorio central.");
  const total = zip.readUInt16LE(fin + 10);
  let posicion = zip.readUInt32LE(fin + 16);
  const nombres: string[] = [];
  for (let n = 0; n < total; n++) {
    if (zip.readUInt32LE(posicion) !== ENTRADA_DEL_DIRECTORIO) {
      throw new Error(`Entrada ${n + 1} del .zip dañada.`);
    }
    const largoDelNombre = zip.readUInt16LE(posicion + 28);
    const largoExtra = zip.readUInt16LE(posicion + 30);
    const largoDelComentario = zip.readUInt16LE(posicion + 32);
    nombres.push(zip.toString("utf8", posicion + 46, posicion + 46 + largoDelNombre));
    posicion += 46 + largoDelNombre + largoExtra + largoDelComentario;
  }
  return nombres;
}
