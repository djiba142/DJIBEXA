import { useEffect, useState } from "react";

/** Réglages de l'entreprise, enregistrés sur cet appareil. */
export type AppSettings = {
  companyName: string;
  slogan: string;
  distributorDetails: string;
  address: string;
  phone: string;
  phoneNumbers: string[];
  emailAddresses: string[];
  additionalInvoiceLines: string[];
  invoiceLineDisplayMode: "compact" | "carnet";
  invoiceHeaderAlignment: "left" | "center";
  invoiceHeaderColor: string;
  invoiceTextColor: string;
  invoiceShowCompanyName: boolean;
  invoiceShowActivity: boolean;
  invoiceShowDistributor: boolean;
  invoiceShowAddress: boolean;
  invoiceShowPhones: boolean;
  invoiceShowEmails: boolean;
  invoiceShowRccm: boolean;
  invoiceShowNif: boolean;
  invoiceShowLogo: boolean;
  invoiceShowAutomotiveImage: boolean;
  invoiceShowWatermark: boolean;
  invoiceShowStamp: boolean;
  invoiceShowQr: boolean;
  invoiceLogoUrl: string;
  invoiceAutomotiveImageUrl: string;
  invoiceWatermarkUrl: string;
  invoiceStampImageUrl: string;
  invoiceStampSizeMm: number;
  invoiceStampOpacity: number;
  invoiceStampPosition: "left" | "center" | "right";
  invoiceShowSellerSignature: boolean;
  invoiceSellerSignatureName: string;
  invoiceSellerSignatureTitle: string;
  invoiceSellerSignatureUrl: string;
  whatsapp: string;
  email: string;
  rccm: string;
  nif: string;
  currency: string;
  vatRate: number;
  invoicePrefix: string;
  invoiceFooter: string;
  paperFormat: "A4" | "A5";
  lowStockThreshold: number;
  sessionMinutes: number;
  language: "fr" | "en" | "ar" | "zh";
  showPartnerOnDocs: boolean;
  printQrOnDocs: boolean;
  website: string;
  openingHours: string;
  bankName: string;
  bankAccount: string;
  mobileMoney: string;
  orderPrefix: string;
  deliveryPrefix: string;
  printCopies: number;
  defaultMarginPct: number;
  allowNegativeSale: boolean;
  whatsappMessage: string;
};

export const DEFAULT_SETTINGS: AppSettings = {
  companyName: "KOUROUMA AUTO PARTS",
  slogan: "VENDEUR DE PIÈCES DE VOITURE ET DES ROULEMENTS",
  distributorDetails: "",
  address: "",
  phone: "",
  phoneNumbers: [],
  emailAddresses: [],
  additionalInvoiceLines: [],
  invoiceLineDisplayMode: "compact",
  invoiceHeaderAlignment: "center",
  invoiceHeaderColor: "#123D60",
  invoiceTextColor: "#FFFFFF",
  invoiceShowCompanyName: true,
  invoiceShowActivity: true,
  invoiceShowDistributor: true,
  invoiceShowAddress: true,
  invoiceShowPhones: true,
  invoiceShowEmails: true,
  invoiceShowRccm: true,
  invoiceShowNif: true,
  invoiceShowLogo: true,
  invoiceShowAutomotiveImage: true,
  invoiceShowWatermark: true,
  invoiceShowStamp: true,
  invoiceShowQr: true,
  invoiceLogoUrl: "",
  invoiceAutomotiveImageUrl: "",
  invoiceWatermarkUrl: "",
  invoiceStampImageUrl: "",
  invoiceStampSizeMm: 20,
  invoiceStampOpacity: 100,
  invoiceStampPosition: "center",
  invoiceShowSellerSignature: true,
  invoiceSellerSignatureName: "",
  invoiceSellerSignatureTitle: "",
  invoiceSellerSignatureUrl: "",
  whatsapp: "",
  email: "",
  rccm: "",
  nif: "",
  currency: "GNF",
  vatRate: 0,
  invoicePrefix: "FA",
  invoiceFooter: "LES MARCHANDISES VENDUES NE SONT NI REMBOURSÉES NI ÉCHANGÉES.",
  paperFormat: "A4",
  lowStockThreshold: 5,
  sessionMinutes: 30,
  language: "fr",
  showPartnerOnDocs: true,
  printQrOnDocs: true,
  website: "",
  openingHours: "Lun–Sam · 8h–19h",
  bankName: "",
  bankAccount: "",
  mobileMoney: "",
  orderPrefix: "BC",
  deliveryPrefix: "BL",
  printCopies: 1,
  defaultMarginPct: 30,
  allowNegativeSale: true,
  whatsappMessage: "Bonjour, voici votre document DJIBEXA :",
};

const KEY = "kap-settings";

export function loadSettings(): AppSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<AppSettings>;
    const settings = { ...DEFAULT_SETTINGS, ...saved };
    const legacyBusinessName = [
      "DJIBEXA",
      "Kourouma Auto Part",
      "KOURAUMA AUTO PARTS",
      "KOUROUMA AUTO PART",
    ].includes(settings.companyName);
    if (legacyBusinessName) {
      settings.companyName = DEFAULT_SETTINGS.companyName;
    }
    if (settings.slogan === "Pièces détachées automobiles — gros & détail") {
      settings.slogan = DEFAULT_SETTINGS.slogan;
    }
    if (settings.address === "Marché Madina, Conakry, Guinée") {
      settings.address = DEFAULT_SETTINGS.address;
    }
    if (!settings.phone) settings.phone = DEFAULT_SETTINGS.phone;
    if (!settings.email) settings.email = DEFAULT_SETTINGS.email;
    if (legacyBusinessName) {
      if (
        [
          "Bonjour, voici votre document DJIBEXA :",
          "Bonjour, voici votre document Kourouma Auto Part :",
        ].includes(settings.whatsappMessage)
      ) {
        settings.whatsappMessage = DEFAULT_SETTINGS.whatsappMessage;
      }
    }
    return settings;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(s: AppSettings) {
  localStorage.setItem(KEY, JSON.stringify(s));
}

export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  useEffect(() => setSettings(loadSettings()), []);
  return settings;
}
