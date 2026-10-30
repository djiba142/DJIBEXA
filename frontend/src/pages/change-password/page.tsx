import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { brandLogo } from "@/lib/brand-assets";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/change-password")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Changer le mot de passe — DJIBEXA" },
      {
        name: "description",
        content: "Sécurisez votre compte DJIBEXA avec un nouveau mot de passe.",
      },
    ],
  }),
  component: RequiredPasswordChangePage,
});

function RequiredPasswordChangePage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { refreshSession } = useAuth();
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      toast.error(t("profile.passwordMismatch"));
      return;
    }

    setSaving(true);
    try {
      await api.post("users/change-password/", {
        current_password: temporaryPassword,
        new_password: newPassword,
      });
      await refreshSession();
      toast.success(t("auth.changePasswordSuccess"));
      await navigate({ to: "/dashboard", replace: true });
    } catch (error) {
      toast.error(t("profile.changeError"), {
        description: error instanceof Error ? error.message : t("common.unknownError"),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel mx-auto mt-10 w-full max-w-md space-y-6 p-6 sm:p-8">
      <div className="text-center">
        <img
          src={brandLogo}
          alt={t("landing.logoAlt")}
          className="mx-auto mb-4 h-16 w-40 object-contain"
        />
        <h1 className="text-2xl font-bold">{t("auth.changePasswordTitle")}</h1>
        <p className="text-muted-foreground mt-2 text-sm">{t("auth.changePasswordRequired")}</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="temporary-password">{t("auth.currentTemporaryPassword")}</Label>
          <Input
            id="temporary-password"
            type="password"
            autoComplete="current-password"
            required
            value={temporaryPassword}
            onChange={(event) => setTemporaryPassword(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="new-password">{t("auth.newPassword")}</Label>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm-password">{t("auth.confirmNewPassword")}</Label>
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
        <Button type="submit" className="w-full" disabled={saving}>
          <KeyRound />
          {t("auth.changePasswordContinue")}
        </Button>
      </form>
    </section>
  );
}
