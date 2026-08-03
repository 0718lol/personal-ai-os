import fs from "fs/promises";
import pdf from "pdf-parse/lib/pdf-parse.js";
import * as mupdf from "mupdf";

mupdf.setLog(null);

function normalizeText(text = "") {
  return String(text)
    .replace(/\0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function useful(text = "") {
  const compact = normalizeText(text).replace(/\s+/g, "");
  const signal = (compact.match(/[A-Za-z0-9\u4e00-\u9fff]/g) || []).length;
  return compact.length >= 24 && signal >= 18;
}

function parseWithMuPDF(buffer) {
  const doc = mupdf.PDFDocument.openDocument(buffer, "application/pdf");
  const pageCount = doc.countPages();
  const pages = [];
  for (let index = 0; index < pageCount; index += 1) {
    try {
      const page = doc.loadPage(index);
      const text = normalizeText(page.toStructuredText().asText() || "");
      if (text) pages.push(`Page ${index + 1}\n${text}`);
    } catch (error) {
      pages.push(`Page ${index + 1}\n[MuPDF extraction failed: ${error.message}]`);
    }
  }
  return { text: normalizeText(pages.join("\n\n")), pageCount };
}

async function main() {
  const filePath = process.argv[2];
  if (!filePath) throw new Error("Usage: node pdf_extract_node.mjs <pdf>");
  const buffer = await fs.readFile(filePath);
  const attempts = [];

  try {
    const mupdfResult = parseWithMuPDF(buffer);
    if (useful(mupdfResult.text)) {
      console.log(JSON.stringify({
        text: mupdfResult.text,
        meta: { engine: "node-mupdf", page_count: mupdfResult.pageCount, attempts }
      }));
      return;
    }
    attempts.push({ engine: "node-mupdf", status: "empty-or-low-text" });
  } catch (error) {
    attempts.push({ engine: "node-mupdf", status: "failed", error: error.message });
  }

  try {
    const parsed = await pdf(buffer);
    const text = normalizeText(parsed.text || "");
    if (useful(text)) {
      console.log(JSON.stringify({
        text,
        meta: { engine: "node-pdf-parse", page_count: parsed.numpages || 0, attempts }
      }));
      return;
    }
    attempts.push({ engine: "node-pdf-parse", status: "empty-or-low-text" });
  } catch (error) {
    attempts.push({ engine: "node-pdf-parse", status: "failed", error: error.message });
  }

  console.log(JSON.stringify({ text: "", meta: { engine: "node-empty", page_count: 0, attempts } }));
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
