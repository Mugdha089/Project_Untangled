export async function exportDiagram(format: 'SVG' | 'PNG' | 'PDF') {
  const svg = document.getElementById('process-diagram');
  if (!(svg instanceof SVGSVGElement)) throw new Error('Open the PFD or topology view before exporting.');
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const originals = [svg, ...Array.from(svg.querySelectorAll('*'))];
  const copies = [clone, ...Array.from(clone.querySelectorAll('*'))];
  originals.forEach((original, i) => {
    const computed = getComputedStyle(original);
    const copy = copies[i];
    if (!copy) return;
    for (const prop of ['fill', 'stroke', 'stroke-width', 'font-family', 'font-size', 'font-weight', 'opacity', 'stroke-dasharray', 'color']) copy.setAttribute(prop, computed.getPropertyValue(prop));
  });
  // XMLSerializer emits the SVG namespace for SVG namespace nodes. Adding a
  // plain xmlns attribute here can serialize it twice and invalidate the XML.
  clone.setAttribute('width', '1200'); clone.setAttribute('height', '700');
  const text = new XMLSerializer().serializeToString(clone);
  let blob = new Blob([text], { type: 'image/svg+xml' });
  if (format !== 'SVG') {
    const url = URL.createObjectURL(blob);
    try {
      const image = new Image(); image.src = url;
      await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = () => reject(new Error('Diagram could not be rendered.')); });
      const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = 700;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Image export is unavailable.');
      context.drawImage(image, 0, 0);
      if (format === 'PNG') blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Image export failed.')), 'image/png'));
      else {
        const { jsPDF } = await import('jspdf');
        const pdf = new jsPDF({ orientation: 'landscape', unit: 'px', format: [1200, 700] });
        pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, 1200, 700);
        blob = pdf.output('blob');
      }
    } finally { URL.revokeObjectURL(url); }
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `UNTANGLE_PFD-001.${format.toLowerCase()}`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
