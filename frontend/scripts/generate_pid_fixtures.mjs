import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { jsPDF } from 'jspdf';
import { strToU8, unzipSync, zipSync } from 'fflate';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const fixtureRoot = resolve(projectRoot, 'test_cases');
const pageWidth = 800;
const pageHeight = 600;

const xmlEscape = value =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');

const columnName = number => {
  let column = '';
  for (let n = number; n > 0; n = Math.floor((n - 1) / 26)) {
    column = String.fromCharCode(((n - 1) % 26) + 65) + column;
  }
  return column;
};

function worksheetXml(rows) {
  const sheetRows = rows
    .map((row, rowIndex) => {
      const cells = row
        .map((value, colIndex) => {
          if (value === null || value === undefined || value === '') return '';
          const ref = `${columnName(colIndex + 1)}${rowIndex + 1}`;
          return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value)}</t></is></c>`;
        })
        .join('');
      return `<row r="${rowIndex + 1}">${cells}</row>`;
    })
    .join('');
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetRows}</sheetData></worksheet>`;
}

function makeWorkbook({ tags, equipment, expectedConnections, groundTruth }) {
  const sheets = [
    { name: 'Instrument Tag List', rows: [['Tag Number', 'Instrument Type', 'Expected in PDF'], ...tags] },
    { name: 'Major Equipment', rows: [['Equipment Tag', 'Type', 'Expected in PDF'], ...equipment] },
    { name: 'Expected Connections', rows: [['From', 'To', 'Relationship'], ...expectedConnections] },
    { name: 'Ground Truth', rows: [['Item', 'Expected Behavior'], ...groundTruth] },
  ];
  const sheetOverrides = sheets
    .map((_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`)
    .join('');
  const workbookSheets = sheets
    .map((sheet, index) => `<sheet name="${xmlEscape(sheet.name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`)
    .join('');
  const relationships = sheets
    .map((_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`)
    .join('');
  const zip = zipSync({
    '[Content_Types].xml': strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>${sheetOverrides}</Types>`),
    '_rels/.rels': strToU8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
    'xl/workbook.xml': strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${workbookSheets}</sheets></workbook>`),
    'xl/_rels/workbook.xml.rels': strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${relationships}</Relationships>`),
    ...Object.fromEntries(sheets.map((sheet, index) => [`xl/worksheets/sheet${index + 1}.xml`, strToU8(worksheetXml(sheet.rows))])),
  });
  return zip;
}

function createDrawing() {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: [pageWidth, pageHeight], compress: false });
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(17);
  doc.text('UNTANGLE SYNTHETIC P&ID TEST FIXTURE', 28, 24);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text('For software regression testing only - not for plant operation or construction', 28, 45);
  doc.setDrawColor(25, 83, 104);
  doc.setLineWidth(1.5);
  doc.line(28, 67, 53, 67);
  doc.text('PROCESS PIPE', 59, 70);
  doc.setDrawColor(170, 175, 180);
  doc.setLineWidth(0.8);
  doc.setFontSize(10);
  doc.setTextColor(30, 45, 55);
  return doc;
}

function processLine(doc, x1, y1, x2, y2) {
  doc.setDrawColor(25, 83, 104);
  doc.setLineWidth(1.5);
  doc.line(x1, y1, x2, y2);
}

function equipment(doc, tag, type, x, y) {
  doc.setDrawColor(54, 69, 79);
  doc.setFillColor(248, 250, 251);
  doc.setLineWidth(1.1);
  if (type === 'pump') {
    doc.circle(x, y, 14, 'FD');
    doc.line(x - 7, y, x + 7, y - 7);
    doc.line(x + 7, y - 7, x + 7, y + 7);
    doc.line(x + 7, y + 7, x - 7, y);
  } else if (type === 'vessel' || type === 'tank') {
    doc.roundedRect(x - 18, y - 23, 36, 46, 7, 7, 'FD');
  } else if (type === 'filter') {
    doc.rect(x - 16, y - 19, 32, 38, 'FD');
    doc.line(x - 12, y + 12, x + 12, y - 12);
  } else {
    doc.rect(x - 20, y - 14, 40, 28, 'FD');
    doc.line(x - 14, y - 10, x + 14, y + 10);
    doc.line(x - 14, y + 10, x + 14, y - 10);
  }
  doc.setTextColor(20, 36, 45);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.text(tag, x, y + 36, { align: 'center' });
  if (type === 'filter') {
    doc.setFontSize(7);
    doc.text('Filter', x, y + 47, { align: 'center' });
  }
  doc.setFont('helvetica', 'normal');
}

function instrument(doc, tag, x, y) {
  doc.setTextColor(35, 45, 50);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.text(tag, x, y);
}

async function writeFixture(name, doc, workbook) {
  const pdf = new Uint8Array(doc.output('arraybuffer'));
  const pdfText = Buffer.from(pdf).toString('latin1');
  if (!pdfText.startsWith('%PDF-') || !pdfText.includes('UNTANGLE SYNTHETIC P&ID TEST FIXTURE')) {
    throw new Error(`${name}: generated PDF failed its header/text checks`);
  }
  const workbookEntries = unzipSync(workbook);
  const workbookXml = Buffer.from(workbookEntries['xl/workbook.xml']).toString('utf8');
  if (!workbookXml.includes('Instrument Tag List') || !workbookXml.includes('Expected Connections')) {
    throw new Error(`${name}: generated workbook is missing required sheets`);
  }
  await writeFile(resolve(fixtureRoot, `${name}.pdf`), pdf);
  await writeFile(resolve(fixtureRoot, `${name}_io.xlsx`), workbook);
}

const yes = (tag, type) => [tag, type, 'yes'];
const no = (tag, type) => [tag, type, 'no'];
const eq = (tag, type) => [tag, type, 'yes'];

async function ambiguousCrossing() {
  const name = '08_ambiguous_crossing';
  const doc = createDrawing();
  equipment(doc, 'P-801', 'pump', 86, 300);
  equipment(doc, 'V-801', 'vessel', 714, 300);
  equipment(doc, 'E-801', 'exchanger', 400, 112);
  equipment(doc, 'TK-801', 'tank', 400, 488);
  processLine(doc, 100, 300, 700, 300);
  processLine(doc, 400, 136, 400, 464);
  instrument(doc, 'PT-801', 190, 280);
  instrument(doc, 'FT-801', 570, 280);
  instrument(doc, 'TT-801', 418, 185);
  instrument(doc, 'LT-801', 418, 450);
  doc.setFontSize(8);
  doc.text('X crossing requires review: junction or crossover', 293, 560);
  const workbook = makeWorkbook({
    tags: [yes('PT-801', 'Pressure Transmitter'), yes('FT-801', 'Flow Transmitter'), yes('TT-801', 'Temperature Transmitter'), yes('LT-801', 'Level Transmitter'), no('PT-899', 'Pressure Transmitter')],
    equipment: [eq('P-801', 'pump'), eq('V-801', 'vessel'), eq('E-801', 'exchanger'), eq('TK-801', 'tank')],
    expectedConnections: [['P-801', 'V-801', 'process-flow'], ['E-801', 'TK-801', 'process-flow']],
    groundTruth: [
      ['Equipment', 'P-801, V-801, E-801, TK-801 are visible and required'],
      ['Tags', 'PT-801, FT-801, TT-801, LT-801 are visible; PT-899 is absent'],
      ['Crossing alternatives', 'Connected Junction adds cross-path connectivity between horizontal and vertical routes'],
      ['Crossing alternatives', 'Crossover keeps horizontal and vertical routes separate'],
      ['Unsupported direction', 'No flow arrows are drawn; direction remains unresolved'],
    ],
  });
  await writeFixture(name, doc, workbook);
}

async function bypassRecycle() {
  const name = '09_bypass_recycle';
  const doc = createDrawing();
  equipment(doc, 'TK-901', 'tank', 66, 300);
  equipment(doc, 'P-901', 'pump', 202, 300);
  equipment(doc, 'E-901', 'exchanger', 420, 300);
  equipment(doc, 'V-901', 'vessel', 670, 300);
  processLine(doc, 84, 300, 184, 300);
  processLine(doc, 220, 300, 400, 300);
  processLine(doc, 440, 300, 652, 300);
  processLine(doc, 260, 300, 260, 190);
  processLine(doc, 260, 190, 420, 190);
  processLine(doc, 420, 190, 420, 280);
  processLine(doc, 688, 300, 745, 300);
  processLine(doc, 745, 300, 745, 475);
  processLine(doc, 745, 475, 202, 475);
  processLine(doc, 202, 475, 202, 318);
  instrument(doc, 'PT-901', 155, 280);
  instrument(doc, 'FT-901', 505, 280);
  instrument(doc, 'TT-901', 438, 212);
  instrument(doc, 'LT-901', 670, 265);
  instrument(doc, 'FV-901', 325, 180);
  instrument(doc, 'PI-901', 122, 325);
  doc.setFontSize(8);
  doc.text('Top branch: exchanger bypass | lower return: recycle to pump suction', 225, 535);
  const workbook = makeWorkbook({
    tags: [yes('PT-901', 'Pressure Transmitter'), yes('FT-901', 'Flow Transmitter'), yes('TT-901', 'Temperature Transmitter'), yes('LT-901', 'Level Transmitter'), yes('FV-901', 'Flow Valve'), yes('PI-901', 'Pressure Indicator'), no('LT-999', 'Level Transmitter')],
    equipment: [eq('TK-901', 'tank'), eq('P-901', 'pump'), eq('E-901', 'exchanger'), eq('V-901', 'vessel')],
    expectedConnections: [['TK-901', 'P-901', 'process-flow'], ['P-901', 'E-901', 'process-flow'], ['E-901', 'V-901', 'process-flow'], ['P-901', 'V-901', 'bypass'], ['V-901', 'P-901', 'recycle']],
    groundTruth: [
      ['Equipment', 'TK-901, P-901, E-901, and V-901 are visible and required'],
      ['Tags', 'Six listed tags are visible; LT-999 is intentionally absent'],
      ['Topology', 'Top branch bypasses E-901 and returns to the common outlet path'],
      ['Topology', 'Lower return forms a recycle loop from V-901 to P-901 suction'],
      ['Unsupported direction', 'No flow arrows are drawn; direction remains unresolved'],
    ],
  });
  await writeFixture(name, doc, workbook);
}

async function denseBranches() {
  const name = '10_dense_shared_headers';
  const doc = createDrawing();
  equipment(doc, 'TK-1001', 'tank', 55, 300);
  equipment(doc, 'P-1001A', 'pump', 190, 205);
  equipment(doc, 'P-1001B', 'pump', 190, 395);
  equipment(doc, 'E-1001', 'exchanger', 420, 160);
  equipment(doc, 'F-1001', 'filter', 420, 440);
  equipment(doc, 'V-1001', 'vessel', 715, 300);
  processLine(doc, 73, 300, 112, 300);
  processLine(doc, 112, 205, 112, 395);
  processLine(doc, 112, 205, 172, 205);
  processLine(doc, 112, 395, 172, 395);
  processLine(doc, 208, 205, 330, 205);
  processLine(doc, 208, 395, 330, 395);
  processLine(doc, 330, 205, 330, 395);
  processLine(doc, 330, 205, 400, 160);
  processLine(doc, 330, 395, 400, 440);
  processLine(doc, 440, 160, 565, 205);
  processLine(doc, 440, 440, 565, 395);
  processLine(doc, 565, 205, 565, 395);
  processLine(doc, 565, 300, 697, 300);
  instrument(doc, 'PT-1001', 130, 170);
  instrument(doc, 'FT-1001', 245, 185);
  instrument(doc, 'PI-1001', 130, 220);
  instrument(doc, 'PT-1002', 130, 365);
  instrument(doc, 'FT-1002', 245, 415);
  instrument(doc, 'TT-1001', 445, 130);
  instrument(doc, 'TT-1002', 445, 466);
  instrument(doc, 'LT-1001', 700, 270);
  instrument(doc, 'FC-1001', 495, 185);
  instrument(doc, 'FV-1001', 520, 215);
  instrument(doc, 'PT-1099', 610, 267);
  doc.setFontSize(8);
  doc.text('Parallel pump and treatment branches use shared suction and discharge headers', 210, 535);
  const workbook = makeWorkbook({
    tags: [yes('PT-1001', 'Pressure Transmitter'), yes('FT-1001', 'Flow Transmitter'), yes('PI-1001', 'Pressure Indicator'), yes('PT-1002', 'Pressure Transmitter'), yes('FT-1002', 'Flow Transmitter'), yes('TT-1001', 'Temperature Transmitter'), yes('TT-1002', 'Temperature Transmitter'), yes('LT-1001', 'Level Transmitter'), yes('FC-1001', 'Flow Controller'), yes('FV-1001', 'Flow Valve'), yes('PT-1099', 'Pressure Transmitter'), no('LT-1099', 'Level Transmitter')],
    equipment: [eq('TK-1001', 'tank'), eq('P-1001A', 'pump'), eq('P-1001B', 'pump'), eq('E-1001', 'exchanger'), eq('F-1001', 'filter'), eq('V-1001', 'vessel')],
    expectedConnections: [['TK-1001', 'P-1001A', 'branch'], ['TK-1001', 'P-1001B', 'branch'], ['P-1001A', 'E-1001', 'process-flow'], ['P-1001B', 'F-1001', 'process-flow'], ['E-1001', 'V-1001', 'merge'], ['F-1001', 'V-1001', 'merge']],
    groundTruth: [
      ['Equipment', 'All six equipment tags are visible and required'],
      ['Tags', 'Eleven listed instrument tags are visible; LT-1099 is intentionally absent'],
      ['Topology', 'Both pump paths share the tank suction and discharge header system'],
      ['Topology', 'Exchanger and filter paths remain distinct until the shared outlet header'],
      ['Simplification', 'Do not remove equipment, any parallel branch, or the shared headers'],
      ['Unsupported direction', 'No flow arrows are drawn; direction remains unresolved'],
    ],
  });
  await writeFixture(name, doc, workbook);
}

await mkdir(fixtureRoot, { recursive: true });
await ambiguousCrossing();
await bypassRecycle();
await denseBranches();
console.log('Generated 3 synthetic PDF/XLSX fixture pairs in test_cases/.');
