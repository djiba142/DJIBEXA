import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocale, type Language } from "@/lib/locale";

const languages: { value: Language; labelKey: string }[] = [
  { value: "fr", labelKey: "settings.languageFrench" },
  { value: "en", labelKey: "settings.languageEnglish" },
  { value: "ar", labelKey: "settings.languageArabic" },
  { value: "zh", labelKey: "settings.languageChinese" },
];

export function LanguageSwitcher() {
  const { language, changeLanguage, t } = useLocale();

  return (
    <Select
      value={language}
      onValueChange={(value) =>
        void changeLanguage(value as Language).catch((error: unknown) =>
          toast.error(t("settings.languageSaveError"), {
            description: error instanceof Error ? error.message : t("common.unknownError"),
          }),
        )
      }
    >
      <SelectTrigger
        aria-label={t("settings.language")}
        className="w-auto min-w-28"
        data-testid="language-switcher"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {languages.map(({ value, labelKey }) => (
          <SelectItem key={value} value={value}>
            {t(labelKey)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
