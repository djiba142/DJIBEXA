import { money } from "@/lib/format";
import { brandLogo } from "@/lib/brand-assets";
import { loadSettings } from "@/lib/settings";

export type PurchaseOrderPdfInput = {
  number: string;
  date: string;
  status: string;
  currency: string;
  supplier: {
    name: string;
    companyName?: string;
    contactName?: string;
    email?: string;
    phone?: string;
    address?: string;
  };
  lines: {
    name: string;
    reference: string;
    quantity: number;
    unitCost: number | null;
  }[];
  notes?: string;
  exchangeRate?: string;
  total: number | null;
};

async function getLogoDataUrl(source: string): Promise<string> {
  const response = await fetch(source);
  if (!response.ok) throw new Error("Impossible de charger le logo configuré.");
  const blob = await response.blob();
  const image = await createImageBitmap(blob);
  const scale = Math.min(1, 900 / image.width, 600 / image.height);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.width * scale));
  canvas.height = Math.max(1, Math.round(image.height * scale));
  const context = canvas.getContext("2d");
  if (!context) {
    image.close();
    throw new Error("Le logo configuré n’a pas pu être traité.");
  }
  context.fillStyle = "#fff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  image.close();
  return canvas.toDataURL("image/jpeg", 0.82);
}

export async function buildPurchaseOrderPdf(input: PurchaseOrderPdfInput): Promise<Blob> {
  const settings = loadSettings();
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const width = doc.internal.pageSize.getWidth();
  const height = doc.internal.pageSize.getHeight();
  const left = 14;
  const right = width - 14;
  const contentWidth = right - left;
  const logoSource = settings.invoiceShowLogo ? settings.invoiceLogoUrl || brandLogo : "";
  const companyX = logoSource ? left + 35 : left;
  const companyWidth = right - companyX;
  if (logoSource) {
    const logo = await getLogoDataUrl(logoSource);
    const image = doc.getImageProperties(logo);
    const scale = Math.min(30 / image.width, 22 / image.height);
    const imageWidth = image.width * scale;
    const imageHeight = image.height * scale;
    doc.addImage(
      logo,
      "JPEG",
      left,
      11 + (22 - imageHeight) / 2,
      imageWidth,
      imageHeight,
      undefined,
      "FAST",
    );
  }
  doc.setFont("helvetica", "bold").setFontSize(13).setTextColor(27, 74, 112);
  doc.text(settings.companyName, companyX, 16, { maxWidth: companyWidth });
  doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(40);
  let companyY = 21;
  for (const value of [
    settings.address,
    settings.phone,
    settings.email,
    settings.rccm ? `RCCM ${settings.rccm}` : "",
    settings.nif ? `NIF ${settings.nif}` : "",
  ].filter(Boolean)) {
    doc.text(value, companyX, companyY, { maxWidth: companyWidth });
    companyY += 4;
  }

  let y = Math.max(42, companyY + 3);
  doc.setDrawColor(27, 74, 112).setLineWidth(0.6).line(left, y, right, y);
  y += 9;
  doc.setFont("helvetica", "bold").setFontSize(15).setTextColor(27, 74, 112);
  doc.text("BON DE COMMANDE FOURNISSEUR", width / 2, y, { align: "center" });
  y += 10;

  const statusBoxWidth = 58;
  const detailsY = y;
  doc.setFillColor(240, 245, 249).roundedRect(left, detailsY - 5, contentWidth, 19, 2, 2, "F");
  doc.setFont("helvetica", "bold").setFontSize(8).setTextColor(27, 74, 112);
  doc.text("Référence", left + 4, detailsY);
  doc.text("Date", left + 64, detailsY);
  doc.text("Statut", right - statusBoxWidth + 4, detailsY);
  doc.setFont("helvetica", "normal").setTextColor(0);
  doc.text(input.number, left + 4, detailsY + 7);
  doc.text(input.date, left + 64, detailsY + 7);
  doc.text(input.status, right - statusBoxWidth + 4, detailsY + 7, {
    maxWidth: statusBoxWidth - 8,
  });
  y += 24;

  doc.setFont("helvetica", "bold").setFontSize(9).setTextColor(27, 74, 112);
  doc.text("FOURNISSEUR", left, y);
  y += 5;
  doc.setFont("helvetica", "bold").setFontSize(9).setTextColor(0);
  doc.text(input.supplier.companyName || input.supplier.name, left, y);
  y += 4.5;
  doc.setFont("helvetica", "normal").setFontSize(8);
  for (const value of [
    input.supplier.companyName && input.supplier.name !== input.supplier.companyName
      ? input.supplier.name
      : "",
    input.supplier.contactName,
    input.supplier.address,
    input.supplier.phone,
    input.supplier.email,
  ].filter(Boolean)) {
    doc.text(value!, left, y, { maxWidth: contentWidth / 2 });
    y += 4;
  }
  if (input.currency !== "GNF" && input.exchangeRate) {
    y += 2;
    doc.setFontSize(7).setTextColor(90);
    doc.text(`Taux appliqué : ${input.exchangeRate} GNF/USD`, left, y);
    doc.setTextColor(0);
    y += 4;
  }
  y += 4;

  const columns = {
    number: left + 4,
    designation: left + 13,
    quantity: right - 53,
    unitCost: right - 28,
    amount: right - 3,
  };
  const drawTableHeader = () => {
    doc.setFillColor(232, 241, 248).rect(left, y - 4, contentWidth, 8, "F");
    doc.setFont("helvetica", "bold").setFontSize(7.5).setTextColor(27, 74, 112);
    doc.text("N°", columns.number, y);
    doc.text("DÉSIGNATION / RÉFÉRENCE", columns.designation, y);
    doc.text("QTÉ", columns.quantity, y, { align: "right" });
    if (input.lines.every((line) => line.unitCost != null)) {
      doc.text("PRIX UNIT.", columns.unitCost, y, { align: "right" });
      doc.text("TOTAL", columns.amount, y, { align: "right" });
    }
    y += 7;
    doc.setDrawColor(27, 74, 112).setLineWidth(0.3).line(left, y, right, y);
    y += 5;
    doc.setFont("helvetica", "normal").setTextColor(0);
  };
  drawTableHeader();

  input.lines.forEach((line, index) => {
    const nameLines = doc.splitTextToSize(line.name, columns.quantity - columns.designation - 4);
    const referenceLines = line.reference
      ? doc.splitTextToSize(line.reference, columns.quantity - columns.designation - 4)
      : [];
    const rowHeight = Math.max(8, nameLines.length * 4 + referenceLines.length * 3);
    if (y + rowHeight > height - 52) {
      doc.addPage();
      y = 18;
      drawTableHeader();
    }
    doc.setFontSize(8).text(String(index + 1), columns.number, y);
    doc.setFont("helvetica", "bold").text(nameLines, columns.designation, y);
    doc.setFont("helvetica", "normal");
    if (referenceLines.length) {
      doc
        .setFontSize(7)
        .setTextColor(110)
        .text(referenceLines, columns.designation, y + nameLines.length * 4);
      doc.setTextColor(0);
    }
    doc.setFontSize(8).text(String(line.quantity), columns.quantity, y, { align: "right" });
    if (line.unitCost != null) {
      doc.text(money(line.unitCost, input.currency), columns.unitCost, y, { align: "right" });
      doc.text(money(line.unitCost * line.quantity, input.currency), columns.amount, y, {
        align: "right",
      });
    }
    y += rowHeight;
    doc
      .setDrawColor(215)
      .setLineWidth(0.2)
      .line(left, y - 2, right, y - 2);
    y += 2;
  });

  if (input.total != null) {
    if (y + 18 > height - 12) {
      doc.addPage();
      y = 18;
    }
    doc
      .setDrawColor(27, 74, 112)
      .setLineWidth(0.4)
      .line(right - 70, y, right, y);
    y += 6;
    doc.setFont("helvetica", "bold").setFontSize(10).setTextColor(27, 74, 112);
    doc.text("TOTAL DE LA COMMANDE", right - 5, y, { align: "right" });
    doc.text(money(input.total, input.currency), right, y + 6, { align: "right" });
    y += 12;
  }

  if (input.notes?.trim()) {
    if (y + 24 > height - 12) {
      doc.addPage();
      y = 18;
    }
    y += 4;
    doc.setFont("helvetica", "bold").setFontSize(8).setTextColor(27, 74, 112);
    doc.text("NOTES / CONDITIONS", left, y);
    y += 5;
    doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(0);
    const noteLines = doc.splitTextToSize(input.notes.trim(), contentWidth);
    doc.text(noteLines, left, y);
    y += noteLines.length * 4 + 8;
  }

  if (y + 27 > height - 10) {
    doc.addPage();
    y = 18;
  }
  y += 3;
  doc.setDrawColor(150).setLineWidth(0.25);
  doc.line(left, y, left + 76, y);
  doc.line(right - 76, y, right, y);
  doc.setFont("helvetica", "normal").setFontSize(7).setTextColor(70);
  doc.text("Validation de l’acheteur", left + 38, y + 5, { align: "center" });
  doc.text("Accord du fournisseur", right - 38, y + 5, { align: "center" });
  doc.setFontSize(6).setTextColor(110);
  doc.text(settings.invoiceFooter || settings.companyName, width / 2, height - 8, {
    align: "center",
    maxWidth: contentWidth,
  });

  return doc.output("blob");
}
