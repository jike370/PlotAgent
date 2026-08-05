import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const fixtureDir = path.resolve("tests/fixtures/import/files");
const previewDir = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.resolve("tests/fixtures/import/previews");
await fs.mkdir(fixtureDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

async function saveWorkbook(name, definitions) {
  const workbook = Workbook.create();
  for (const definition of definitions) {
    const sheet = workbook.worksheets.add(definition.name);
    if (definition.values) {
      const rows = definition.values.length;
      const columns = Math.max(...definition.values.map((row) => row.length));
      const padded = definition.values.map((row) => [
        ...row,
        ...Array(columns - row.length).fill(null),
      ]);
      sheet.getRangeByIndexes(0, 0, rows, columns).values = padded;
      if (rows > 1 && columns > 1) {
        sheet.getRangeByIndexes(0, 0, 1, columns).format = {
          fill: "#E8EEF7",
          font: { bold: true, color: "#1F2937" },
        };
      }
      sheet.getUsedRange().format.autofitColumns();
      // Keep intentionally short fixtures legible in rendered QA previews.
      sheet.getUsedRange().format.columnWidth = 20;
    }
    if (definition.formulas) {
      for (const [cell, formula] of Object.entries(definition.formulas)) {
        sheet.getRange(cell).formulas = [[formula]];
      }
    }
    sheet.showGridLines = true;
  }

  const inspection = await workbook.inspect({
    kind: "sheet,table,formula",
    maxChars: 2500,
    tableMaxRows: 6,
    tableMaxCols: 6,
  });
  console.log(JSON.stringify({ fixture: name, inspect: inspection.ndjson }));
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 20 },
    summary: `formula scan ${name}`,
  });
  console.log(JSON.stringify({ fixture: name, errors: errors.ndjson }));

  for (const definition of definitions) {
    const rendered = await workbook.render({
      sheetName: definition.name,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    const safeSheet = definition.name.replaceAll(/[^A-Za-z0-9_-]/g, "_");
    await fs.writeFile(
      path.join(previewDir, `${name}-${safeSheet}.png`),
      new Uint8Array(await rendered.arrayBuffer()),
    );
  }

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(fixtureDir, name));
}

await saveWorkbook("excel_two_sheets.xlsx", [
  {
    name: "Run A",
    values: [
      ["Time (s)", "Signal [mV]", "Valid"],
      [0, 0, false],
      [1, 2.5, true],
    ],
  },
  {
    name: "Run B",
    values: [
      ["Time (s)", "Signal [mV]", "Valid"],
      [0, 1.25, true],
      [1, 3.75, false],
    ],
  },
]);

await saveWorkbook("excel_title_header.xlsx", [
  {
    name: "Measurements",
    values: [
      ["Instrument export"],
      ["Time", "Response"],
      [0, 4.2],
      [1, 4.8],
    ],
  },
]);

await saveWorkbook("excel_nonfinite.xlsx", [
  {
    name: "Data",
    values: [
      ["x", "y"],
      [0, "NaN"],
      [1, "Inf"],
      [2, "-Inf"],
      [3, "NA"],
    ],
  },
]);

await saveWorkbook("excel_duplicate_headers.xlsx", [
  {
    name: "Data",
    values: [
      ["Signal", " Signal "],
      [1, 2],
      [3, 4],
    ],
  },
]);

await saveWorkbook("excel_formula.xlsx", [
  {
    name: "Data",
    values: [
      ["x", "derived"],
      [2, null],
      [3, null],
    ],
    formulas: { B2: "=A2*2", B3: "=A3*2" },
  },
]);

await saveWorkbook("excel_unicode_headers.xlsx", [
  {
    name: "Data",
    values: [
      ["Cafe\u0301", "Value"],
      ["A", 1],
      ["B", 2],
    ],
  },
]);

await saveWorkbook("excel_header_ambiguous.xlsx", [
  {
    name: "Data",
    values: [
      ["alpha", "beta"],
      ["group-a", "group-b"],
      [1, 2],
    ],
  },
]);

await saveWorkbook("excel_two_regions.xlsx", [
  {
    name: "Data",
    values: [
      ["x", "y"],
      [0, 1],
      [null, null],
      ["a", "b"],
      [2, 3],
    ],
  },
]);

await saveWorkbook("excel_empty.xlsx", [
  {
    name: "Notes",
    values: [["No tabular data"]],
  },
]);

await saveWorkbook("excel_numeric_no_header.xlsx", [
  {
    name: "Data",
    values: [
      [0, 1.5],
      [1, 2.5],
      [2, 3.5],
    ],
  },
]);

await fs.copyFile(
  path.join(fixtureDir, "excel_two_sheets.xlsx"),
  path.join(fixtureDir, "excel_readonly.xlsm"),
);
