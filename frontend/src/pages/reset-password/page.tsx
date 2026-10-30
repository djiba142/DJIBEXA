import { Route as FileRoute } from "@/routes/reset-password";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { brandLogo } from "@/lib/brand-assets";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLocale } from "@/lib/locale";

const resetSearchSchema = z.object({
  uid: z.string().optional(),
  token: z.string().optional(),
});

export const PageRoute = createFileRoute("/reset-password")({
  ssr: false,
  validateSearch: resetSearchSchema,
  head: () => ({
    meta: [
      { title: "Nouveau mot de passe — DJIBEXA" },
      { name: "description", content: "Choisissez un nouveau mot de passe pour votre compte ERP." },
      { property: "og:title", content: "Nouveau mot de passe — DJIBEXA" },
      {
        property: "og:description",
        content: "Choisissez un nouveau mot de passe pour votre compte ERP.",
      },
    ],
  }),
  component: ResetPasswordPage,
});

function ResetPasswordPage() {
  const { t } = useLocale();
  const { uid, token } = FileRoute.useSearch();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const linkIsValid = Boolean(uid && token);

  useEffect(() => {
    document.title = t("auth.resetDocumentTitle");
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = t("auth.resetMetaDescription");
    const openGraphTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    if (openGraphTitle) openGraphTitle.content = t("auth.resetDocumentTitle");
    const openGraphDescription = document.querySelector<HTMLMetaElement>(
      'meta[property="og:description"]',
    );
    if (openGraphDescription) openGraphDescription.content = t("auth.resetMetaDescription");
  }, [t]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uid || !token) return;
    if (password !== confirmation) {
      toast.error(t("profile.passwordMismatch"));
      return;
    }

    setLoading(true);
    try {
      await api.post("users/pin-reset/confirm/", {
        uid,
        token,
        password,
      });
      toast.success(t("auth.passwordChanged"));
      await navigate({ to: "/auth", replace: true });
    } catch (error) {
      toast.error(t("auth.passwordResetError"), {
        description: error instanceof Error ? error.message : t("common.unknownError"),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="bg-muted/30 relative flex min-h-screen items-center justify-center px-4 py-10">
      <div className="absolute top-4 end-4">
        <LanguageSwitcher />
      </div>
      <section className="panel w-full max-w-md space-y-6 p-6 sm:p-8">
        <Button asChild variant="ghost" size="sm">
          <Link to="/auth">
            <ArrowLeft />
            {t("auth.backToLogin")}
          </Link>
        </Button>
        <div className="text-center">
          <img
            src={brandLogo}
            alt={t("landing.logoAlt")}
            className="mx-auto mb-4 h-16 w-40 object-contain"
          />
          <h1 className="text-2xl font-bold">{t("profile.newPassword")}</h1>
          <p className="text-muted-foreground mt-2 text-sm">{t("auth.chooseNewPassword")}</p>
        </div>
        {linkIsValid ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">{t("profile.newPassword")}</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">{t("auth.confirmPassword")}</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              <KeyRound />
              {loading ? t("auth.passwordSaving") : t("auth.saveNewPassword")}
            </Button>
          </form>
        ) : (
          <div className="space-y-4 text-center">
            <p className="text-destructive text-sm">{t("auth.invalidResetLink")}</p>
            <Button asChild className="w-full">
              <Link to="/auth">{t("auth.backToLogin")}</Link>
            </Button>
          </div>
        )}
      </section>
    </main>
  );
}
