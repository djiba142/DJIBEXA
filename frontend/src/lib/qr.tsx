import { useEffect, useState } from "react";
import QRCode from "qrcode";

/** Rend un QR code en image PNG (client uniquement). */
export function QrImage({
  value,
  size = 128,
  className,
  alt = "QR code",
}: {
  value: string;
  size?: number;
  className?: string;
  alt?: string;
}) {
  const [src, setSrc] = useState("");

  useEffect(() => {
    let cancelled = false;
    void QRCode.toDataURL(value, { margin: 0, width: size * 2 }).then((url) => {
      if (!cancelled) setSrc(url);
    });
    return () => {
      cancelled = true;
    };
  }, [value, size]);

  if (!src) return <div style={{ width: size, height: size }} className={className} />;
  return <img src={src} width={size} height={size} className={className} alt={alt} />;
}

/** Préfixes des différents types de QR de l'ERP. */
export const QR_PREFIX = {
  carton: "KAP-CTN-",
  sample: "KAP-SMP-",
  invoice: "KAP-INV-",
  order: "KAP-CMD-",
  delivery: "KAP-BL-",
} as const;

export const invoiceQrValue = (origin: string, token: string) => `${origin}/verifier/${token}`;
export const docQrValue = invoiceQrValue;

/** Origine du site, vide côté serveur. */
export const siteOrigin = () => (typeof window === "undefined" ? "" : window.location.origin);

/** Numéro lisible pour un nouveau document. */
export function docNumber(prefix: string) {
  const d = new Date();
  const stamp = `${String(d.getFullYear()).slice(2)}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const rand = Math.floor(Math.random() * 9000 + 1000);
  return `${prefix}-${stamp}-${rand}`;
}
