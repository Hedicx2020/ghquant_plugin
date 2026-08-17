/**
 * r004 五工作簿唯一构建器。
 *
 * 只使用 @oai/artifact-tool >=2.8.6。调用方必须先把本文件复制到可写临时
 * 目录，并把该目录 node_modules 符号链接到指定只读 packages 目录。
 */

import { createRequire } from "node:module";
import { execFile } from "node:child_process";
import {
  readFile,
  mkdir,
  mkdtemp,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { promisify } from "node:util";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const MINIMUM_ARTIFACT_TOOL_VERSION = [2, 8, 6];
const EXCEL_MAX_DATA_ROWS = 1_048_575;
const MAX_COLUMN_WIDTH = 32;
const PREVIEW_MAX_ROWS = 40;
const PREVIEW_MAX_COLUMNS = 18;
const FORMULA_INSPECT_ROWS_PER_CHUNK = 500;
const ERROR_TOKENS = ["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"];
const HEADER_FILL = "#1f4e78";
const HEADER_FONT = "#ffffff";
const BORDER_COLOR = "#d1d5db";
const OOXML_COMMAND_MAX_BUFFER_BYTES = 16 * 1024 * 1024;
const OOXML_FREEZE_CELL = "A2";
const WARNING_MESSAGES = [];
const execFileAsync = promisify(execFile);

const originalConsoleWarn = console.warn.bind(console);
console.warn = (...values) => {
  const message = values.map((value) => (
    typeof value === "string" ? value : JSON.stringify(value)
  )).join(" ");
  WARNING_MESSAGES.push(message);
  originalConsoleWarn(...values);
};


function assertNoWarnings(context) {
  if (WARNING_MESSAGES.length > 0) {
    throw new Error(`${context} 捕获到QA warning: ${WARNING_MESSAGES.join(" | ")}`);
  }
}


function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`参数必须采用 --key value: ${argv.join(" ")}`);
    }
    args[key.slice(2)] = value;
  }
  for (const required of ["input", "output", "qa-dir", "manifest"]) {
    if (!args[required]) {
      throw new Error(`缺少必需参数 --${required}`);
    }
  }
  return args;
}


async function artifactToolVersion() {
  const require = createRequire(import.meta.url);
  const entry = require.resolve("@oai/artifact-tool");
  const packagePath = path.resolve(path.dirname(entry), "../package.json");
  const metadata = JSON.parse(await readFile(packagePath, "utf8"));
  const parts = String(metadata.version).split(".").map((value) => Number(value));
  const valid = MINIMUM_ARTIFACT_TOOL_VERSION.every((minimum, index) => {
    const current = parts[index] ?? 0;
    const earlierEqual = MINIMUM_ARTIFACT_TOOL_VERSION.slice(0, index).every(
      (value, earlierIndex) => (parts[earlierIndex] ?? 0) === value,
    );
    return !earlierEqual || current >= minimum;
  });
  if (!valid) {
    throw new Error(
      `@oai/artifact-tool版本过低: ${metadata.version}; `
      + `最低要求${MINIMUM_ARTIFACT_TOOL_VERSION.join(".")}`,
    );
  }
  return metadata.version;
}


function columnLetter(indexOneBased) {
  let value = indexOneBased;
  let output = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    output = String.fromCharCode(65 + remainder) + output;
    value = Math.floor((value - 1) / 26);
  }
  return output;
}


function safeSheetName(value, suffix = "") {
  const replaced = String(value).replace(/[\\/?*\[\]:]/g, "_");
  const suffixText = suffix ? `_${suffix}` : "";
  return `${replaced.slice(0, 31 - suffixText.length)}${suffixText}`;
}


function classifyColumn(column) {
  const name = String(column).toLowerCase();
  const date = name === "date" || name.endsWith("_date") || name.endsWith("date");
  const percentage = [
    "return", "volatility", "drawdown", "win_rate", "frequency", "weight",
    "turnover", "coverage", "cost_rate", "excess_return", "tracking_error",
    "positive_rate", "increase_ratio",
  ].some((token) => name.includes(token));
  return { date, percentage: percentage && !name.includes("count") };
}


function convertRows(columns, rows) {
  const classifications = columns.map(classifyColumn);
  return rows.map((row) => row.map((value, columnIndex) => {
    if (value === null || value === undefined) {
      return null;
    }
    if (classifications[columnIndex].date && typeof value === "string") {
      const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
      if (!Number.isNaN(parsed.valueOf())) {
        return parsed;
      }
    }
    return value;
  }));
}


function styleSheet(sheet, columns, rowCount) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const lastColumn = columnLetter(Math.max(1, columns.length));
  const lastRow = Math.max(1, rowCount + 1);
  const used = sheet.getRange(`A1:${lastColumn}${lastRow}`);
  used.format.font = { name: "PingFang SC", size: 10, color: "#111827" };
  used.format.verticalAlignment = "center";
  used.format.borders = { preset: "insideHorizontal", style: "thin", color: BORDER_COLOR };
  const header = sheet.getRange(`A1:${lastColumn}1`);
  header.format.fill = HEADER_FILL;
  header.format.font = { name: "PingFang SC", size: 10, bold: true, color: HEADER_FONT };
  header.format.wrapText = true;
  used.format.autofitColumns();
  used.format.autofitRows();
  columns.forEach((column, index) => {
    const letter = columnLetter(index + 1);
    const columnRange = sheet.getRange(`${letter}1:${letter}${lastRow}`);
    const width = Number(columnRange.format.columnWidth);
    if (Number.isFinite(width) && width > MAX_COLUMN_WIDTH) {
      columnRange.format.columnWidth = MAX_COLUMN_WIDTH;
      columnRange.format.wrapText = true;
    }
    const kind = classifyColumn(column);
    if (rowCount > 0 && kind.date) {
      if (!Number.isFinite(width) || width < 12) {
        columnRange.format.columnWidth = 12;
      }
      sheet.getRange(`${letter}2:${letter}${lastRow}`).format.numberFormat = "yyyy-mm-dd";
    } else if (rowCount > 0 && kind.percentage) {
      sheet.getRange(`${letter}2:${letter}${lastRow}`).format.numberFormat = "0.00%";
    }
  });
}


function writeTable(sheet, columns, rows) {
  const safeColumns = columns.length ? columns : ["说明"];
  const safeRows = columns.length ? convertRows(columns, rows) : [["无记录"]];
  const grid = [safeColumns, ...safeRows];
  const lastColumn = columnLetter(safeColumns.length);
  const lastRow = grid.length;
  sheet.getRange(`A1:${lastColumn}${lastRow}`).values = grid;
  styleSheet(sheet, safeColumns, safeRows.length);
  return { columns: safeColumns, lastColumn, lastRow };
}


function hasDeclaredChart(sheetSpec) {
  return Object.prototype.hasOwnProperty.call(sheetSpec, "chart");
}


function validateDeclaredChart(sheetSpec, workbookFilename) {
  if (!hasDeclaredChart(sheetSpec)) {
    return null;
  }
  const chartSpec = sheetSpec.chart;
  const context = `${workbookFilename}/${sheetSpec.name}`;
  if (!chartSpec || !Array.isArray(chartSpec.columns) || chartSpec.columns.length < 2) {
    throw new Error(`${context}声明chart但类别/数值列不足`);
  }
  if (!Array.isArray(chartSpec.rows) || chartSpec.rows.length === 0) {
    throw new Error(`${context}声明chart但源行数为0`);
  }
  if (
    chartSpec.rows.some(
      (row) => !Array.isArray(row) || row.length !== chartSpec.columns.length,
    )
  ) {
    throw new Error(`${context}声明chart但源行列宽与columns不一致`);
  }
  const categoryPresent = chartSpec.rows.some(
    (row) => row[0] !== null && row[0] !== undefined && String(row[0]).trim() !== "",
  );
  const numericColumnPresent = chartSpec.columns.slice(1).some((_, offset) => (
    chartSpec.rows.some((row) => (
      typeof row[offset + 1] === "number" && Number.isFinite(row[offset + 1])
    ))
  ));
  if (!categoryPresent || !numericColumnPresent) {
    throw new Error(`${context}声明chart但缺少有效类别或数值列`);
  }
  return chartSpec;
}


function addTraceableChart(sheet, tableInfo, sheetSpec, workbookFilename) {
  const chartSpec = validateDeclaredChart(sheetSpec, workbookFilename);
  if (chartSpec === null) {
    return null;
  }
  const startRow = tableInfo.lastRow + 3;
  const chartRows = convertRows(chartSpec.columns, chartSpec.rows);
  const chartLastColumn = columnLetter(chartSpec.columns.length);
  const chartLastRow = startRow + chartRows.length;
  const sourceRange = `A${startRow}:${chartLastColumn}${chartLastRow}`;
  sheet.getRange(sourceRange).values = [chartSpec.columns, ...chartRows];
  const chartHeader = sheet.getRange(`A${startRow}:${chartLastColumn}${startRow}`);
  chartHeader.format.fill = "#dbeafe";
  chartHeader.format.font = { name: "PingFang SC", size: 10, bold: true, color: "#1e3a8a" };
  const chart = sheet.charts.add(chartSpec.type, sheet.getRange(sourceRange), "Columns");
  chart.title.text = chartSpec.title;
  chart.hasLegend = true;
  chart.legend.position = "bottom";
  chart.yAxis = { numberFormatCode: "0.00%", numberFormatSourceLinked: false };
  chart.width = 600;
  chart.height = 320;
  const positionStartColumn = chartSpec.columns.length + 2;
  const positionEndColumn = positionStartColumn + 8;
  chart.setPosition(
    sheet.getRange(
      `${columnLetter(positionStartColumn)}${startRow}:${columnLetter(positionEndColumn)}${startRow + 16}`,
    ),
  );
  return {
    title: chartSpec.title,
    type: chartSpec.type,
    source_range: sourceRange,
    source_sheet: sheet.name,
    source_rows: chartRows.length,
  };
}


function coverRows(workbookSpec, payload) {
  const context = payload.verification_context ?? {};
  const rows = [
    ["项目", payload.report_id],
    ["工作簿", workbookSpec.filename],
    ["标题", workbookSpec.title],
    ["说明", workbookSpec.subtitle],
    ["复现模式", payload.reproduction_mode],
    ["验证状态", payload.verification_status],
    ["验证阶段", payload.verification_state ?? "pending_verifier"],
    ["验证结论", payload.verdict ?? "NOT_VERIFIED"],
    ["验证上下文SHA-256", context.context_sha256 ?? "NOT_AVAILABLE"],
    ["验证报告", context.verify_report ?? "NOT_AVAILABLE"],
    ["证据清单", context.evidence_manifest ?? "NOT_AVAILABLE"],
    ["工作表数", workbookSpec.sheets.length],
    [
      "重要声明",
      payload.verification_state === "verified"
        ? "美国原值只作背景/不可比；PASS仅来自只读verifier上下文且不证明长期稳定"
        : "美国原值只作背景/不可比；本工作簿不包含verifier结论",
    ],
  ];
  for (const disclosure of payload.final_boundary_disclosures ?? []) {
    rows.push([`结论边界:${disclosure.disclosure_id}`, disclosure.text]);
  }
  return rows;
}


function splitSheet(sheetSpec) {
  if (sheetSpec.rows.length <= EXCEL_MAX_DATA_ROWS) {
    return [{ ...sheetSpec, name: safeSheetName(sheetSpec.name) }];
  }
  const parts = [];
  const { chart, ...sheetWithoutChart } = sheetSpec;
  for (let offset = 0, part = 1; offset < sheetSpec.rows.length; offset += EXCEL_MAX_DATA_ROWS, part += 1) {
    const split = {
      ...sheetWithoutChart,
      name: safeSheetName(sheetSpec.name, String(part)),
      rows: sheetSpec.rows.slice(offset, offset + EXCEL_MAX_DATA_ROWS),
    };
    if (part === 1 && hasDeclaredChart(sheetSpec)) {
      split.chart = chart;
    }
    parts.push(split);
  }
  return parts;
}


function scanPreExportGrid(formulaScan, columns, rows, context) {
  const safeColumns = columns.length ? columns : ["说明"];
  const safeRows = columns.length ? rows : [["无记录"]];
  const scanRow = (row, rowNumber) => {
    formulaScan.scanned_row_count += 1;
    formulaScan.scanned_cell_count += row.length;
    for (const value of row) {
      if (typeof value !== "string") {
        continue;
      }
      if (ERROR_TOKENS.includes(value)) {
        formulaScan.error_tokens.add(value);
      }
      if (value.startsWith("=")) {
        formulaScan.formula_expression_count += 1;
        throw new Error(`${context}第${rowNumber}行含未授权公式表达式`);
      }
    }
  };
  formulaScan.chunk_count += 1;
  scanRow(safeColumns, 1);
  for (let offset = 0; offset < safeRows.length; offset += FORMULA_INSPECT_ROWS_PER_CHUNK) {
    formulaScan.chunk_count += 1;
    const end = Math.min(offset + FORMULA_INSPECT_ROWS_PER_CHUNK, safeRows.length);
    for (let rowIndex = offset; rowIndex < end; rowIndex += 1) {
      scanRow(safeRows[rowIndex], rowIndex + 2);
    }
  }
}


async function inspectAndRender(workbook, workbookSpec, sheetRecords, qaDir) {
  const inspections = [];
  const previews = [];
  const charts = [];
  for (const record of sheetRecords) {
    const sheet = record.sheet;
    const inspectEndColumn = columnLetter(Math.min(PREVIEW_MAX_COLUMNS, record.tableInfo.columns.length));
    const inspectEndRow = sheet.name === "Cover"
      ? Math.min(12, record.tableInfo.lastRow)
      : Math.min(6, record.tableInfo.lastRow);
    const keyRange = `A1:${inspectEndColumn}${inspectEndRow}`;
    const inspected = await workbook.inspect({
      kind: "table",
      include: "values",
      sheetId: sheet.name,
      range: keyRange,
      maxChars: 5000,
      tableMaxRows: 6,
      tableMaxCols: PREVIEW_MAX_COLUMNS,
      tableMaxCellChars: 120,
    });
    inspections.push({ sheet: sheet.name, key_range: keyRange, ndjson: inspected.ndjson });
    if (record.chartInfo) {
      charts.push(record.chartInfo);
    }
    const renderEndRow = record.chartInfo
      ? Math.min(record.tableInfo.lastRow + 22, record.tableInfo.lastRow + record.chartInfo.source_rows + 20)
      : Math.min(PREVIEW_MAX_ROWS, record.tableInfo.lastRow);
    const renderEndColumn = columnLetter(
      Math.min(PREVIEW_MAX_COLUMNS, Math.max(record.tableInfo.columns.length, 12)),
    );
    const renderRange = `A1:${renderEndColumn}${Math.max(1, renderEndRow)}`;
    const image = await workbook.render({ sheetName: sheet.name, range: renderRange, format: "png" });
    const previewName = `${workbookSpec.filename.replace(/\.xlsx$/i, "")}__${sheet.name}.png`;
    const previewPath = path.join(qaDir, previewName);
    await writeFile(previewPath, Buffer.from(await image.arrayBuffer()));
    const previewStat = await stat(previewPath);
    previews.push({
      sheet: sheet.name,
      range: renderRange,
      path: previewPath,
      size_bytes: previewStat.size,
    });
  }
  return {
    inspections,
    previews,
    charts,
  };
}


function assertInMemoryQa(workbookSpec, records, qa, declaredCharts) {
  const sheetNames = records.map((record) => record.sheet.name);
  const inspectedNames = qa.inspections.map((record) => record.sheet);
  const previewNames = qa.previews.map((record) => record.sheet);
  if (
    sheetNames.length === 0
    || qa.inspections.length !== sheetNames.length
    || qa.previews.length !== sheetNames.length
    || new Set(inspectedNames).size !== sheetNames.length
    || new Set(previewNames).size !== sheetNames.length
    || sheetNames.some((name) => !inspectedNames.includes(name) || !previewNames.includes(name))
  ) {
    throw new Error(`${workbookSpec.filename} sheet/inspect/preview计数未闭环`);
  }
  if (qa.inspections.some((record) => !String(record.ndjson ?? "").trim())) {
    throw new Error(`${workbookSpec.filename}存在空inspect记录`);
  }
  if (qa.previews.some((record) => !(Number(record.size_bytes) > 0))) {
    throw new Error(`${workbookSpec.filename}存在空preview记录`);
  }
  if (
    qa.formula_scan.status !== "no_formula_errors"
    || qa.formula_scan.error_tokens.length > 0
    || qa.formula_scan.formula_expression_count !== 0
    || qa.formula_scan.scanned_row_count <= 0
    || qa.formula_scan.scanned_cell_count <= 0
    || qa.formula_scan.chunk_count <= 0
  ) {
    throw new Error(`${workbookSpec.filename}公式错误扫描失败`);
  }
  if (qa.charts.length !== declaredCharts.length) {
    throw new Error(
      `${workbookSpec.filename}必要chart记录不完整: `
      + `declared=${declaredCharts.length}, actual=${qa.charts.length}`,
    );
  }
  for (const declared of declaredCharts) {
    const actual = qa.charts.find((chart) => chart.source_sheet === declared.source_sheet);
    if (
      !actual
      || actual.source_rows !== declared.source_rows
      || actual.title !== declared.title
    ) {
      throw new Error(
        `${workbookSpec.filename}/${declared.source_sheet} chart声明与实际记录不一致`,
      );
    }
  }
}


function xmlAttributes(tag) {
  const attributes = {};
  for (const match of tag.matchAll(/([A-Za-z_][\w:.-]*)="([^"]*)"/g)) {
    attributes[match[1]] = match[2]
      .replaceAll("&quot;", '"')
      .replaceAll("&apos;", "'")
      .replaceAll("&lt;", "<")
      .replaceAll("&gt;", ">")
      .replaceAll("&amp;", "&");
  }
  return attributes;
}


function normalizedWorkbookTarget(target) {
  const portable = String(target).replaceAll("\\", "/");
  const joined = portable.startsWith("/")
    ? portable.slice(1)
    : path.posix.normalize(path.posix.join("xl", portable));
  if (!/^xl\/worksheets\/[^/]+\.xml$/.test(joined)) {
    throw new Error(`工作表关系Target越界或异常: ${target}`);
  }
  return joined;
}


async function workbookSheetEntries(extractedDir) {
  const workbookXml = await readFile(path.join(extractedDir, "xl/workbook.xml"), "utf8");
  const relationshipsXml = await readFile(
    path.join(extractedDir, "xl/_rels/workbook.xml.rels"),
    "utf8",
  );
  const relationTargets = new Map();
  for (const match of relationshipsXml.matchAll(/<(?:[\w.-]+:)?Relationship\b[^>]*\/?\s*>/g)) {
    const attributes = xmlAttributes(match[0]);
    if (String(attributes.Type ?? "").endsWith("/worksheet")) {
      relationTargets.set(attributes.Id, normalizedWorkbookTarget(attributes.Target));
    }
  }
  const sheets = [];
  for (const match of workbookXml.matchAll(/<(?:[\w.-]+:)?sheet\b[^>]*\/?\s*>/g)) {
    const attributes = xmlAttributes(match[0]);
    const relationshipId = attributes["r:id"];
    const entry = relationTargets.get(relationshipId);
    if (!attributes.name || !relationshipId || !entry) {
      throw new Error(`workbook.xml工作表关系不完整: ${match[0]}`);
    }
    sheets.push({ sheet: attributes.name, worksheet_entry: entry });
  }
  if (sheets.length === 0 || new Set(sheets.map((record) => record.sheet)).size !== sheets.length) {
    throw new Error("workbook.xml工作表清单为空或存在重名");
  }
  return sheets;
}


function withFrozenFirstRow(worksheetXml, context) {
  const viewCount = Array.from(
    worksheetXml.matchAll(/<(?:[\w.-]+:)?sheetView\b/g),
  ).length;
  if (viewCount !== 1) {
    throw new Error(`${context} sheetView数量必须为1，实际${viewCount}`);
  }
  const expanded = /<((?:[\w.-]+:)?sheetView)\b([^>]*)>([\s\S]*?)<\/\1>/;
  const selfClosing = /<((?:[\w.-]+:)?sheetView)\b([^>]*)\/\s*>/;
  const match = worksheetXml.match(expanded) ?? worksheetXml.match(selfClosing);
  if (!match) {
    throw new Error(`${context}无法定位sheetView`);
  }
  const tagName = match[1];
  const prefix = tagName.includes(":") ? `${tagName.split(":")[0]}:` : "";
  const existingBody = match.length >= 4 && match[3] !== undefined ? match[3] : "";
  const bodyWithoutPanes = existingBody.replace(
    /<(?:[\w.-]+:)?pane\b[^>]*(?:\/\s*>|>[\s\S]*?<\/(?:[\w.-]+:)?pane>)/g,
    "",
  );
  const pane = `<${prefix}pane ySplit="1" topLeftCell="${OOXML_FREEZE_CELL}" `
    + `activePane="bottomLeft" state="frozen" />`;
  const replacement = `<${tagName}${match[2]}>${pane}${bodyWithoutPanes}</${tagName}>`;
  return worksheetXml.replace(match[0], replacement);
}


function parseFreezePane(worksheetXml, context) {
  const paneMatches = Array.from(
    worksheetXml.matchAll(/<(?:[\w.-]+:)?pane\b[^>]*\/?\s*>/g),
  );
  if (paneMatches.length !== 1) {
    throw new Error(`${context} pane数量必须为1，实际${paneMatches.length}`);
  }
  const attributes = xmlAttributes(paneMatches[0][0]);
  const ySplit = Number(attributes.ySplit ?? 0);
  const xSplit = Number(attributes.xSplit ?? 0);
  const frozen = (
    attributes.state === "frozen"
    && ySplit === 1
    && xSplit === 0
    && attributes.topLeftCell === OOXML_FREEZE_CELL
  );
  if (!frozen) {
    throw new Error(
      `${context} 首行冻结未真实生效: state=${attributes.state ?? "missing"}, `
      + `ySplit=${attributes.ySplit ?? "0"}, xSplit=${attributes.xSplit ?? "0"}, `
      + `topLeftCell=${attributes.topLeftCell ?? "missing"}`,
    );
  }
  return {
    state: attributes.state,
    y_split: ySplit,
    x_split: xSplit,
    top_left_cell: attributes.topLeftCell,
    active_pane: attributes.activePane ?? null,
    equivalent_freeze_cell: OOXML_FREEZE_CELL,
    frozen_first_row: frozen,
  };
}


async function inspectExportedFreezePanes(outputPath, expectedSheetNames) {
  const extractedDir = await mkdtemp(path.join(os.tmpdir(), "r004_freeze_inspect_"));
  try {
    await execFileAsync("unzip", ["-q", outputPath, "-d", extractedDir], {
      maxBuffer: OOXML_COMMAND_MAX_BUFFER_BYTES,
    });
    const sheetEntries = await workbookSheetEntries(extractedDir);
    const actualNames = sheetEntries.map((record) => record.sheet);
    if (
      actualNames.length !== expectedSheetNames.length
      || actualNames.some((name, index) => name !== expectedSheetNames[index])
    ) {
      throw new Error(
        `${path.basename(outputPath)} 导出工作表映射与内存不一致: `
        + `actual=${actualNames.join("|")}, expected=${expectedSheetNames.join("|")}`,
      );
    }
    const records = [];
    for (const entry of sheetEntries) {
      const worksheetXml = await readFile(path.join(extractedDir, entry.worksheet_entry), "utf8");
      records.push({
        ...entry,
        ...parseFreezePane(worksheetXml, `${path.basename(outputPath)}/${entry.sheet}`),
      });
    }
    return records;
  } finally {
    await rm(extractedDir, { recursive: true, force: true });
  }
}


async function materializeFrozenFirstRows(outputPath, expectedSheetNames, faultSheetName = null) {
  const extractedDir = await mkdtemp(path.join(os.tmpdir(), "r004_freeze_patch_"));
  const rebuiltPath = path.join(
    os.tmpdir(),
    `${path.basename(outputPath)}.${process.pid}.${Date.now()}.freeze.tmp.xlsx`,
  );
  try {
    await execFileAsync("unzip", ["-q", outputPath, "-d", extractedDir], {
      maxBuffer: OOXML_COMMAND_MAX_BUFFER_BYTES,
    });
    const sheetEntries = await workbookSheetEntries(extractedDir);
    const actualNames = sheetEntries.map((record) => record.sheet);
    if (
      actualNames.length !== expectedSheetNames.length
      || actualNames.some((name, index) => name !== expectedSheetNames[index])
    ) {
      throw new Error(`${path.basename(outputPath)} 冻结注入前工作表映射不一致`);
    }
    for (const entry of sheetEntries) {
      const worksheetPath = path.join(extractedDir, entry.worksheet_entry);
      const originalXml = await readFile(worksheetPath, "utf8");
      let frozenXml = withFrozenFirstRow(
        originalXml,
        `${path.basename(outputPath)}/${entry.sheet}`,
      );
      if (entry.sheet === faultSheetName) {
        frozenXml = frozenXml.replace(
          /<(?:[\w.-]+:)?pane\b[^>]*(?:\/\s*>|>[\s\S]*?<\/(?:[\w.-]+:)?pane>)/,
          "",
        );
      }
      await writeFile(
        worksheetPath,
        frozenXml,
        "utf8",
      );
    }
    if (faultSheetName !== null && !actualNames.includes(faultSheetName)) {
      throw new Error(`${path.basename(outputPath)} 冻结故障注入sheet不存在: ${faultSheetName}`);
    }
    await execFileAsync("zip", ["-q", "-X", "-r", rebuiltPath, "."], {
      cwd: extractedDir,
      maxBuffer: OOXML_COMMAND_MAX_BUFFER_BYTES,
    });
    await rename(rebuiltPath, outputPath);
  } finally {
    await rm(extractedDir, { recursive: true, force: true });
    await rm(rebuiltPath, { force: true });
  }
}


async function inspectOoxml(outputPath, expectedSheetCount, expectedChartCount) {
  const tested = await execFileAsync(
    "unzip",
    ["-t", outputPath],
    { maxBuffer: OOXML_COMMAND_MAX_BUFFER_BYTES },
  );
  const listed = await execFileAsync(
    "unzip",
    ["-Z1", outputPath],
    { maxBuffer: OOXML_COMMAND_MAX_BUFFER_BYTES },
  );
  if (String(tested.stderr ?? "").trim() || String(listed.stderr ?? "").trim()) {
    throw new Error(
      `OOXML检查输出stderr: ${String(tested.stderr ?? "").trim()} `
      + `${String(listed.stderr ?? "").trim()}`,
    );
  }
  const entries = listed.stdout.split("\n").map((value) => value.trim()).filter(Boolean);
  const requiredEntries = [
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
  ];
  const requiredEntriesPresent = requiredEntries.every((entry) => entries.includes(entry));
  const worksheetCount = entries.filter(
    (entry) => /^xl\/worksheets\/sheet\d+\.xml$/.test(entry),
  ).length;
  const chartCount = entries.filter(
    (entry) => /^xl\/(?:drawings\/)?charts\/chart\d+\.xml$/.test(entry),
  ).length;
  if (
    !requiredEntriesPresent
    || worksheetCount !== expectedSheetCount
    || chartCount !== expectedChartCount
  ) {
    throw new Error(
      `OOXML结构不完整: required=${requiredEntriesPresent}, `
      + `sheets=${worksheetCount}/${expectedSheetCount}, charts=${chartCount}/${expectedChartCount}`,
    );
  }
  const extractedDir = await mkdtemp(path.join(os.tmpdir(), "r004_formula_inspect_"));
  let formulaCellCount = 0;
  const formulaErrorTokens = new Set();
  try {
    await execFileAsync("unzip", ["-q", outputPath, "-d", extractedDir], {
      maxBuffer: OOXML_COMMAND_MAX_BUFFER_BYTES,
    });
    const sheetEntries = await workbookSheetEntries(extractedDir);
    for (const entry of sheetEntries) {
      const worksheetXml = await readFile(
        path.join(extractedDir, entry.worksheet_entry),
        "utf8",
      );
      formulaCellCount += Array.from(
        worksheetXml.matchAll(/<(?:[\w.-]+:)?f(?:\s|>)/g),
      ).length;
      for (const token of ERROR_TOKENS) {
        if (worksheetXml.includes(`>${token}<`)) {
          formulaErrorTokens.add(token);
        }
      }
    }
  } finally {
    await rm(extractedDir, { recursive: true, force: true });
  }
  if (formulaErrorTokens.size > 0) {
    throw new Error(`OOXML检出公式错误: ${Array.from(formulaErrorTokens).join(",")}`);
  }
  return {
    crc_status: "ok",
    required_entries_present: requiredEntriesPresent,
    worksheet_count: worksheetCount,
    expected_worksheet_count: expectedSheetCount,
    chart_count: chartCount,
    expected_chart_count: expectedChartCount,
    formula_scan_complete: true,
    formula_cell_count: formulaCellCount,
    formula_error_tokens: Array.from(formulaErrorTokens),
  };
}


async function buildWorkbook(workbookSpec, payload, outputDir, qaDir) {
  const workbook = Workbook.create();
  const records = [];
  const declaredCharts = [];
  const formulaScan = {
    method: "chunked_full_source_grid_before_export_plus_full_ooxml_after_export",
    error_tokens: new Set(),
    formula_expression_count: 0,
    chunk_count: 0,
    rows_per_chunk: FORMULA_INSPECT_ROWS_PER_CHUNK,
    scanned_row_count: 0,
    scanned_cell_count: 0,
    status: "no_formula_errors",
  };
  const cover = workbook.worksheets.add("Cover");
  const coverData = coverRows(workbookSpec, payload);
  scanPreExportGrid(formulaScan, ["字段", "内容"], coverData, `${workbookSpec.filename}/Cover`);
  const coverTable = writeTable(cover, ["字段", "内容"], coverData);
  records.push({ sheet: cover, tableInfo: coverTable, chartInfo: null });

  for (const originalSheet of workbookSpec.sheets) {
    for (const sheetSpec of splitSheet(originalSheet)) {
      const sheet = workbook.worksheets.add(sheetSpec.name);
      scanPreExportGrid(
        formulaScan,
        sheetSpec.columns,
        sheetSpec.rows,
        `${workbookSpec.filename}/${sheetSpec.name}`,
      );
      const tableInfo = writeTable(sheet, sheetSpec.columns, sheetSpec.rows);
      const declaredChart = validateDeclaredChart(sheetSpec, workbookSpec.filename);
      if (declaredChart !== null) {
        scanPreExportGrid(
          formulaScan,
          declaredChart.columns,
          declaredChart.rows,
          `${workbookSpec.filename}/${sheetSpec.name}/chart`,
        );
        declaredCharts.push({
          source_sheet: sheet.name,
          source_rows: declaredChart.rows.length,
          title: declaredChart.title,
        });
      }
      const chartInfo = addTraceableChart(sheet, tableInfo, sheetSpec, workbookSpec.filename);
      records.push({ sheet, tableInfo, chartInfo });
    }
    originalSheet.rows = [];
    if (hasDeclaredChart(originalSheet)) {
      originalSheet.chart.rows = [];
    }
  }

  if (formulaScan.error_tokens.size > 0) {
    throw new Error(
      `${workbookSpec.filename} 源数据检出公式错误: `
      + `${Array.from(formulaScan.error_tokens).join(",")}`,
    );
  }
  workbook.recalculate();
  const qa = {
    ...await inspectAndRender(workbook, workbookSpec, records, qaDir),
    formula_scan: {
      ...formulaScan,
      error_tokens: Array.from(formulaScan.error_tokens),
      formula_record_count: formulaScan.formula_expression_count,
    },
  };
  assertInMemoryQa(workbookSpec, records, qa, declaredCharts);
  assertNoWarnings(`${workbookSpec.filename} inspect/render`);
  const exported = await SpreadsheetFile.exportXlsx(workbook);
  const outputPath = path.join(outputDir, workbookSpec.filename);
  await exported.save(outputPath);
  const freezeFault = payload.qa_fault_injection?.remove_freeze_pane;
  const faultSheetName = freezeFault?.filename === workbookSpec.filename
    ? freezeFault.sheet
    : null;
  await materializeFrozenFirstRows(
    outputPath,
    records.map((record) => record.sheet.name),
    faultSheetName,
  );
  const freezePanes = await inspectExportedFreezePanes(
    outputPath,
    records.map((record) => record.sheet.name),
  );
  const outputStat = await stat(outputPath);
  if (outputStat.size <= 0) {
    throw new Error(`工作簿为空: ${outputPath}`);
  }
  const ooxmlScan = await inspectOoxml(outputPath, records.length, declaredCharts.length);
  assertNoWarnings(`${workbookSpec.filename} export/OOXML`);
  return {
    filename: workbookSpec.filename,
    path: outputPath,
    size_bytes: outputStat.size,
    sheet_count: records.length,
    sheets: records.map((record) => record.sheet.name),
    declared_chart_count: declaredCharts.length,
    expected_chart_count: declaredCharts.length,
    actual_chart_count: qa.charts.length,
    declared_charts: declaredCharts,
    frozen_first_row_count: freezePanes.filter((record) => record.frozen_first_row).length,
    freeze_panes: freezePanes,
    ooxml_scan: ooxmlScan,
    ...qa,
  };
}


async function main() {
  const args = parseArgs(process.argv.slice(2));
  const version = await artifactToolVersion();
  assertNoWarnings("artifact-tool初始化");
  const inputStat = await stat(args.input);
  const payload = JSON.parse(await readFile(args.input, "utf8"));
  if (!Array.isArray(payload.workbooks) || payload.workbooks.length !== 1) {
    throw new Error(
      `工作簿worker必须且只能接收1本工作簿，实际${payload.workbooks?.length ?? 0}`,
    );
  }
  await mkdir(args.output, { recursive: true });
  await mkdir(args["qa-dir"], { recursive: true });
  const workbooks = [];
  for (const workbookSpec of payload.workbooks) {
    workbooks.push(await buildWorkbook(workbookSpec, payload, args.output, args["qa-dir"]));
  }
  assertNoWarnings("全部工作簿QA");
  const inspectComplete = workbooks.every(
    (workbook) => workbook.inspections.length === workbook.sheet_count
      && workbook.inspections.every((record) => String(record.ndjson ?? "").trim()),
  );
  const renderComplete = workbooks.every(
    (workbook) => workbook.previews.length === workbook.sheet_count
      && workbook.previews.every((record) => Number(record.size_bytes) > 0),
  );
  const formulaComplete = workbooks.every(
    (workbook) => workbook.formula_scan.status === "no_formula_errors"
      && workbook.formula_scan.error_tokens.length === 0
      && workbook.ooxml_scan.formula_scan_complete === true
      && workbook.ooxml_scan.formula_error_tokens.length === 0,
  );
  const chartComplete = workbooks.every(
    (workbook) => workbook.declared_chart_count === workbook.expected_chart_count
      && workbook.expected_chart_count === workbook.actual_chart_count
      && workbook.actual_chart_count === workbook.charts.length
      && workbook.declared_charts.length === workbook.declared_chart_count
      && workbook.ooxml_scan.expected_chart_count === workbook.declared_chart_count
      && workbook.ooxml_scan.chart_count === workbook.actual_chart_count,
  );
  const ooxmlComplete = workbooks.every(
    (workbook) => workbook.ooxml_scan.crc_status === "ok"
      && workbook.ooxml_scan.required_entries_present
      && workbook.ooxml_scan.worksheet_count === workbook.sheet_count,
  );
  const freezeComplete = workbooks.every(
    (workbook) => workbook.freeze_panes.length === workbook.sheet_count
      && workbook.frozen_first_row_count === workbook.sheet_count
      && workbook.freeze_panes.every((record) => (
        record.frozen_first_row
        && record.top_left_cell === OOXML_FREEZE_CELL
        && record.y_split === 1
        && record.x_split === 0
        && record.state === "frozen"
      )),
  );
  const manifest = {
    report_id: payload.report_id,
    verification_status: payload.verification_status,
    verification_state: payload.verification_state,
    verdict: payload.verdict,
    verification_context_sha256: payload.verification_context?.context_sha256 ?? null,
    generated_at: new Date().toISOString(),
    artifact_tool_package: "@oai/artifact-tool",
    artifact_tool_version: version,
    minimum_required_version: MINIMUM_ARTIFACT_TOOL_VERSION.join("."),
    input_payload_size_bytes: inputStat.size,
    qa_policy: {
      inspect_key_range_before_export: inspectComplete,
      scan_formula_errors_before_export: formulaComplete,
      render_every_user_sheet_before_export: renderComplete,
      native_chart_source_same_sheet: chartComplete,
      ooxml_crc_and_structure_checked: ooxmlComplete,
      first_row_frozen_in_export: freezeComplete,
      gridlines_hidden: true,
      header_bold_and_first_row_frozen: freezeComplete,
      autofit_then_width_cap: MAX_COLUMN_WIDTH,
    },
    warning_count: WARNING_MESSAGES.length,
    warnings: WARNING_MESSAGES,
    worker_process_memory: {
      max_rss_bytes: process.resourceUsage().maxRSS * 1024,
      heap_used_bytes_at_manifest: process.memoryUsage().heapUsed,
      heap_total_bytes_at_manifest: process.memoryUsage().heapTotal,
      external_bytes_at_manifest: process.memoryUsage().external,
    },
    workbooks,
  };
  await writeFile(args.manifest, JSON.stringify(manifest, null, 2), "utf8");
}


await main();
