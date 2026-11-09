import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useLocale } from "@/lib/locale";

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

type InstallAppButtonProps = {
  compact?: boolean;
};

function isStandaloneMode() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in navigator &&
      Boolean((navigator as Navigator & { standalone?: boolean }).standalone))
  );
}

export function InstallAppButton({ compact = false }: InstallAppButtonProps) {
  const { t } = useLocale();
  const [promptEvent, setPromptEvent] = useState<InstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [isAppleMobile, setIsAppleMobile] = useState(false);

  useEffect(() => {
    const updateInstalledState = () => setInstalled(isStandaloneMode());
    const handleInstallPrompt = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as InstallPromptEvent);
    };
    const handleInstalled = () => {
      setInstalled(true);
      setPromptEvent(null);
    };
    const handleDisplayModeChange = () => updateInstalledState();
    const displayMode = window.matchMedia("(display-mode: standalone)");
    const userAgent = navigator.userAgent;

    setIsAppleMobile(
      /iPhone|iPad|iPod/.test(userAgent) ||
        (/Macintosh/.test(userAgent) && navigator.maxTouchPoints > 1),
    );
    updateInstalledState();
    window.addEventListener("beforeinstallprompt", handleInstallPrompt);
    window.addEventListener("appinstalled", handleInstalled);
    displayMode.addEventListener("change", handleDisplayModeChange);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleInstallPrompt);
      window.removeEventListener("appinstalled", handleInstalled);
      displayMode.removeEventListener("change", handleDisplayModeChange);
    };
  }, []);

  const handleClick = async () => {
    if (!promptEvent) {
      setInstructionsOpen(true);
      return;
    }

    try {
      await promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      setPromptEvent(null);
      if (choice.outcome === "accepted") setInstalled(true);
    } catch (error) {
      console.error("Impossible de démarrer l’installation de DJIBEXA.", error);
      toast.error(t("pwa.installFailed"));
    }
  };

  if (installed) return null;

  return (
    <>
      <Button
        type="button"
        variant={compact ? "ghost" : "outline"}
        size={compact ? "icon" : "sm"}
        aria-label={t("pwa.install")}
        title={t("pwa.install")}
        onClick={() => void handleClick()}
      >
        <Download className="size-4" aria-hidden="true" />
        <span className={compact ? "sr-only" : "ms-2"}>{t("pwa.install")}</span>
      </Button>
      <Dialog open={instructionsOpen} onOpenChange={setInstructionsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("pwa.installTitle")}</DialogTitle>
            <DialogDescription>{t("pwa.installDescription")}</DialogDescription>
          </DialogHeader>
          <p className="text-sm leading-6 text-muted-foreground">
            {isAppleMobile ? t("pwa.iosInstructions") : t("pwa.browserInstructions")}
          </p>
        </DialogContent>
      </Dialog>
    </>
  );
}
