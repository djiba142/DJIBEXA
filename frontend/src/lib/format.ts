let currentLocale = "fr-FR";

export const setFormatLocale = (language: "fr" | "en" | "ar" | "zh") => {
  currentLocale = { fr: "fr-FR", en: "en-US", ar: "ar", zh: "zh-CN" }[language];
};

export const money = (value: number | string | null | undefined, currency = "GNF") => {
  const fractionDigits = new Intl.NumberFormat("en", {
    style: "currency",
    currency,
  }).resolvedOptions().maximumFractionDigits;
  const amount = new Intl.NumberFormat(currentLocale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(Number(value ?? 0));
  return `${amount} ${currency}`;
};

export const formatNumber = (value: number) => new Intl.NumberFormat(currentLocale).format(value);

const frenchUnits = [
  "zéro",
  "un",
  "deux",
  "trois",
  "quatre",
  "cinq",
  "six",
  "sept",
  "huit",
  "neuf",
  "dix",
  "onze",
  "douze",
  "treize",
  "quatorze",
  "quinze",
  "seize",
];

const frenchUnit = (value: number) => frenchUnits[value] ?? formatNumber(value);

function frenchUnderHundred(value: number): string {
  if (value < frenchUnits.length) return frenchUnit(value);
  if (value < 20) return `dix-${frenchUnit(value - 10)}`;
  const tens = Math.floor(value / 10) * 10;
  const unit = value % 10;
  if (tens === 70) {
    return unit === 0 ? "soixante-dix" : `soixante-${frenchUnderHundred(10 + unit)}`;
  }
  if (tens === 80) {
    return unit === 0 ? "quatre-vingts" : `quatre-vingt-${frenchUnit(unit)}`;
  }
  if (tens === 90) return `quatre-vingt-${frenchUnderHundred(10 + unit)}`;
  if (unit === 0)
    return tens === 20
      ? "vingt"
      : tens === 30
        ? "trente"
        : tens === 40
          ? "quarante"
          : tens === 50
            ? "cinquante"
            : "soixante";
  if (unit === 1 && tens !== 80) {
    const name =
      tens === 20
        ? "vingt"
        : tens === 30
          ? "trente"
          : tens === 40
            ? "quarante"
            : tens === 50
              ? "cinquante"
              : "soixante";
    return `${name} et un`;
  }
  return `${frenchUnderHundred(tens)}-${frenchUnit(unit)}`;
}

function frenchUnderThousand(value: number): string {
  if (value < 100) return frenchUnderHundred(value);
  const hundreds = Math.floor(value / 100);
  const remainder = value % 100;
  const prefix =
    hundreds === 1 ? "cent" : `${frenchUnit(hundreds)} cent${remainder === 0 ? "s" : ""}`;
  return remainder ? `${prefix} ${frenchUnderHundred(remainder)}` : prefix;
}

export function numberToFrenchWords(value: number): string {
  const integer = Math.floor(Math.abs(value));
  if (!Number.isSafeInteger(integer)) return formatNumber(integer);
  if (integer < 1000) return frenchUnderThousand(integer);

  const groups: string[] = [];
  let remaining = integer;
  const scales = ["", "mille", "million", "milliard", "billion"];
  let scale = 0;
  while (remaining > 0 && scale < scales.length) {
    const group = remaining % 1000;
    if (group > 0) {
      const groupWords = scale === 1 && group === 1 ? "" : frenchUnderThousand(group);
      const scaleName = scales[scale];
      const scaleLabel = scale === 1 ? scaleName : `${scaleName}${group > 1 ? "s" : ""}`;
      groups.unshift([groupWords, scaleLabel].filter(Boolean).join(" "));
    }
    remaining = Math.floor(remaining / 1000);
    scale += 1;
  }
  return groups.join(" ");
}

export const formatFileSize = (bytes: number) => {
  const unit = bytes < 1024 ? "byte" : bytes < 1024 ** 2 ? "kilobyte" : "megabyte";
  const divisor = unit === "byte" ? 1 : unit === "kilobyte" ? 1024 : 1024 ** 2;

  return new Intl.NumberFormat(currentLocale, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: 0,
  }).format(bytes / divisor);
};

export const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString(currentLocale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString(currentLocale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
