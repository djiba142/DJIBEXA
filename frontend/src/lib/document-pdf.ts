import QRCode from "qrcode";

import { money } from "@/lib/format";
import { loadSettings } from "@/lib/settings";

export type DocLine = { label: string; sub?: string; qty: number; price?: number };

export type DocPdfLabels = {
  lineNumber: string;
  designation: string;
  quantity: string;
  unitPrice: string;
  amount: string;
  subtotal: string;
  discount: string;
  total: string;
  paid: string;
  balanceDue: string;
};

export type DocPdfInput = {
  kind: string;
  number: string;
  date: string;
  parties: { label: string; value: string }[];
  lines: DocLine[];
  fixedLineCount?: number;
  subtotal?: number;
  discount?: number;
  total?: number;
  paid?: number;
  balanceDue?: number;
  currency?: string;
  amountInWords?: string;
  labels?: Partial<DocPdfLabels>;
  verifyUrl?: string;
  footer?: string;
  signerName?: string;
  signatureDate?: string;
  signatureLabel?: string;
  stampLabel?: string;
  issuedByLabel?: string;
};

/** Construit un PDF de facture ou de document partageable, sans dépendre du CSS de la page. */
export async function buildDocumentPdf(input: DocPdfInput): Promise<Blob> {
  const { jsPDF } = await import("jspdf");
  const s = loadSettings();
  const doc = new jsPDF({
    unit: "mm",
    format: s.paperFormat.toLowerCase() as "a4" | "a5",
  });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const left = 12;
  const right = W - 12;
  let y = 14;
  const labels = {
    lineNumber: "N°",
    designation: "Designation",
    quantity: "Qte",
    unitPrice: "Prix unit.",
    amount: "Montant",
    subtotal: "Sous-total",
    discount: "Remise",
    total: "TOTAL",
    paid: "Montant paye",
    balanceDue: "Reste a payer",
    ...input.labels,
  };
  const formatMoney = (value: number) => money(value, input.currency ?? "GNF");

  doc.setTextColor(27, 74, 112).setFont("helvetica", "bold").setFontSize(14);
  doc.text(s.companyName.toUpperCase(), left, y);
  doc.setTextColor(0).setFont("helvetica", "normal").setFontSize(8);
  if (s.slogan) doc.text(s.slogan, left, y + 4.5, { maxWidth: W * 0.58 });
  doc.text(s.address, left, y + 8.5, { maxWidth: W * 0.58 });
  const contact = [s.phone && `Tel. ${s.phone}`, s.whatsapp && `WhatsApp ${s.whatsapp}`, s.email]
    .filter(Boolean)
    .join(" - ");
  if (contact) doc.text(contact, left, y + 12.5, { maxWidth: W * 0.58 });
  const legal = [s.rccm && `RCCM ${s.rccm}`, s.nif && `NIF ${s.nif}`].filter(Boolean).join(" - ");
  if (legal) doc.text(legal, left, y + 16.5, { maxWidth: W * 0.58 });

  const headingY = y;
  doc.setTextColor(27, 74, 112).setFont("helvetica", "bold").setFontSize(11);
  doc.text(input.kind.toUpperCase(), right, headingY, { align: "right" });
  doc.setTextColor(0).setFont("helvetica", "normal").setFontSize(9);
  doc.text(input.number, right, headingY + 4.5, { align: "right" });
  doc.setFontSize(8);
  doc.text(input.date, right, headingY + 8.5, { align: "right" });

  y += legal ? 20 : contact ? 16 : 12;
  doc.setDrawColor(27, 74, 112).setLineWidth(0.5).line(left, y, right, y);
  y += 6;

  doc.setFontSize(9);
  input.parties.forEach((p) => {
    const label = `${p.label} :`;
    doc.setFont("helvetica", "bold").text(label, left, y);
    doc.setFont("helvetica", "normal").text(p.value || "-", left + 30, y, {
      maxWidth: right - left - 30,
    });
    y += 5;
  });

  y += 3;
  const numberX = left + 6;
  const descriptionX = left + 10;
  const quantityX = W * 0.61;
  const priceX = W * 0.78;
  doc.setFillColor(232, 241, 248).rect(left, y - 4, right - left, 7, "F");
  doc.setTextColor(27, 74, 112).setFont("helvetica", "bold").setFontSize(8);
  doc.text(labels.lineNumber, left + 1, y);
  doc.text(labels.designation, descriptionX, y);
  doc.text(labels.quantity, quantityX, y, { align: "right" });
  doc.text(labels.unitPrice, priceX, y, { align: "right" });
  doc.text(labels.amount, right - 1, y, { align: "right" });
  y += 5;
  doc.setDrawColor(27, 74, 112).setLineWidth(0.35).line(left, y, right, y);
  y += 5;

  doc.setTextColor(0).setFont("helvetica", "normal");
  const lines = input.fixedLineCount
    ? Array.from(
        { length: Math.max(input.fixedLineCount, input.lines.length) },
        (_, index) => input.lines[index] ?? null,
      )
    : input.lines;
  lines.forEach((l, index) => {
    const labelLines = l ? doc.splitTextToSize(l.label, quantityX - descriptionX - 4) : [];
    const subLines = l?.sub ? doc.splitTextToSize(l.sub, quantityX - descriptionX - 4) : [];
    const rowHeight = Math.max(5.5, labelLines.length * 4 + subLines.length * 3);
    if (y + rowHeight > H - 48) {
      doc.addPage();
      y = 16;
      doc.setFillColor(232, 241, 248).rect(left, y - 4, right - left, 7, "F");
      doc.setTextColor(27, 74, 112).setFont("helvetica", "bold").setFontSize(8);
      doc.text(labels.lineNumber, left + 1, y);
      doc.text(labels.designation, descriptionX, y);
      doc.text(labels.quantity, quantityX, y, { align: "right" });
      doc.text(labels.unitPrice, priceX, y, { align: "right" });
      doc.text(labels.amount, right - 1, y, { align: "right" });
      y += 5;
      doc.setDrawColor(27, 74, 112).line(left, y, right, y);
      y += 5;
      doc.setTextColor(0).setFont("helvetica", "normal");
    }
    doc.setFontSize(8.5).text(String(index + 1), left + 1, y);
    if (l) {
      doc.text(labelLines, descriptionX, y);
      doc.text(String(l.qty), quantityX, y, { align: "right" });
      if (l.price != null) {
        doc.text(formatMoney(l.price), priceX, y, { align: "right" });
        doc.text(formatMoney(l.qty * l.price), right - 1, y, { align: "right" });
      }
    }
    if (subLines.length) {
      doc
        .setFontSize(7)
        .setTextColor(120)
        .text(subLines, descriptionX, y + labelLines.length * 4);
      doc.setTextColor(0);
    }
    y += rowHeight;
    doc
      .setDrawColor(205)
      .setLineWidth(0.2)
      .line(left, y - 1.5, right, y - 1.5);
  });

  if (y + 46 > H - 10) {
    doc.addPage();
    y = 18;
  }
  if (input.subtotal != null) {
    doc.setFont("helvetica", "normal").setFontSize(8);
    doc.text(labels.subtotal, right - 48, y, { align: "right" });
    doc.text(formatMoney(input.subtotal), right, y, { align: "right" });
    y += 4;
  }
  if (input.discount != null && input.discount > 0) {
    doc.text(labels.discount, right - 48, y, { align: "right" });
    doc.text(`-${formatMoney(input.discount)}`, right, y, { align: "right" });
    y += 4;
  }
  if (input.total != null) {
    doc
      .setDrawColor(27, 74, 112)
      .setLineWidth(0.4)
      .line(right - 60, y, right, y);
    y += 5;
    doc.setTextColor(27, 74, 112).setFont("helvetica", "bold").setFontSize(10);
    doc.text(labels.total, right - 48, y, { align: "right" });
    doc.text(formatMoney(input.total), right, y, { align: "right" });
    doc.setTextColor(0);
    y += 5;
  }
  if (input.paid != null || input.balanceDue != null) {
    doc.setFont("helvetica", "normal").setFontSize(8);
    if (input.paid != null) {
      doc.text(labels.paid, right - 48, y, { align: "right" });
      doc.text(formatMoney(input.paid), right, y, { align: "right" });
      y += 4;
    }
    if (input.balanceDue != null) {
      doc.setFont("helvetica", "bold");
      doc.text(labels.balanceDue, right - 48, y, { align: "right" });
      doc.text(formatMoney(input.balanceDue), right, y, { align: "right" });
      y += 5;
    }
  }

  if (input.amountInWords) {
    const amountLines = doc.splitTextToSize(input.amountInWords, right - left - 4) as string[];
    const amountHeight = amountLines.length * 4;
    if (y + amountHeight + 40 > H - 8) {
      doc.addPage();
      y = 18;
    }
    doc.setFont("helvetica", "bold").setFontSize(7);
    doc.text(amountLines, left, y + 2);
    y += amountHeight + 4;
  }

  if (input.signerName) {
    if (y + 40 > H - 8) {
      doc.addPage();
      y = 18;
    }
    doc.setDrawColor(180).line(left, y, right, y);
    y += 4;
    const stampX = left + 15;
    const stampY = y + 14;
    doc.setDrawColor(27, 74, 112).setTextColor(27, 74, 112).setLineWidth(0.7);
    doc.circle(stampX, stampY, 12);
    doc.setLineWidth(0.25).circle(stampX, stampY, 10);
    doc.setFont("helvetica", "bold").setFontSize(5.5);
    doc.text(s.companyName.toUpperCase().slice(0, 24), stampX, stampY - 2, {
      align: "center",
      maxWidth: 18,
    });
    doc.setFont("helvetica", "normal").setFontSize(5);
    if (s.rccm) doc.text(`RCCM ${s.rccm}`.slice(0, 32), stampX, stampY + 2, { align: "center" });
    if (s.nif) doc.text(`NIF ${s.nif}`.slice(0, 32), stampX, stampY + 5, { align: "center" });

    const signX = left + 36;
    doc.setTextColor(0).setFont("helvetica", "bold").setFontSize(8);
    doc.text(input.signatureLabel ?? "Signature electronique", signX, y + 4);
    doc.setFont("helvetica", "italic").setFontSize(10);
    doc.text(input.signerName.slice(0, 40), signX, y + 13);
    doc.setFont("helvetica", "normal").setFontSize(7);
    doc.text(input.issuedByLabel ?? "Emise par le vendeur", signX, y + 18);
    doc.text(input.signatureDate ?? input.date, signX, y + 22);

    if (s.printQrOnDocs && input.verifyUrl) {
      const dataUrl = await QRCode.toDataURL(input.verifyUrl, { margin: 0, width: 240 });
      doc.addImage(dataUrl, "PNG", right - 28, y + 1, 24, 24);
      doc.setFontSize(5.5).setTextColor(90);
      doc.text(input.stampLabel ?? "Verification", right - 16, y + 28, { align: "center" });
    }
    y += 32;
    doc.setTextColor(0);
  } else if (s.printQrOnDocs && input.verifyUrl) {
    const dataUrl = await QRCode.toDataURL(input.verifyUrl, { margin: 0, width: 240 });
    doc.addImage(dataUrl, "PNG", 12, y, 24, 24);
    doc.setFont("helvetica", "normal").setFontSize(7).setTextColor(90);
    doc.text("Scannez ce QR code pour verifier", 39, y + 8);
    doc.text("l'authenticite de ce document.", 39, y + 12);
    doc.setTextColor(0);
    y += 28;
  }

  doc.setFontSize(7).setTextColor(120);
  doc.text(input.footer ?? `Merci de votre confiance - ${s.companyName}`, W / 2, y + 4, {
    align: "center",
    maxWidth: W - 24,
  });

  return doc.output("blob");
}

/** Partage le PDF via WhatsApp (partage natif si possible, sinon lien wa.me). */
export async function shareOnWhatsApp(
  pdf: Blob,
  fileName: string,
  message: string,
  phone?: string,
) {
  const file = new File([pdf], fileName, { type: "application/pdf" });
  const nav = navigator as Navigator & {
    canShare?: (d: { files?: File[] }) => boolean;
    share?: (d: { files?: File[]; text?: string; title?: string }) => Promise<void>;
  };

  if (nav.canShare?.({ files: [file] }) && nav.share) {
    try {
      await nav.share({ files: [file], text: message, title: fileName });
      return "shared" as const;
    } catch {
      /* l'utilisateur a annulé ou le partage a échoué : on retombe sur wa.me */
    }
  }

  downloadPdfBlob(pdf, fileName);

  const digits = (phone ?? "").replace(/\D/g, "");
  window.open(`https://wa.me/${digits}?text=${encodeURIComponent(message)}`, "_blank", "noopener");
  return "downloaded" as const;
}

export function downloadPdfBlob(pdf: Blob, fileName: string) {
  const url = URL.createObjectURL(pdf);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
