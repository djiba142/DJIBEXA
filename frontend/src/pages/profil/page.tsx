import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { toast } from "sonner";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/profil")({
  head: () => ({
    meta: [
      { title: "Mon profil — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Consultez et modifiez vos informations personnelles, votre photo de profil et votre mot de passe dans DJIBEXA.",
      },
      { property: "og:title", content: "Mon profil — DJIBEXA" },
      {
        property: "og:description",
        content: "Gérez vos informations personnelles, votre photo et la sécurité de votre compte.",
      },
    ],
  }),
  component: Profil,
});

function Profil() {
  const { t, language } = useLocale();
  const { session, roles, expiresAt, signOut, refreshSession } = useAuth();
  const [profile, setProfile] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
  });
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!session?.user) return;
    setProfile({
      first_name: session.user.first_name,
      last_name: session.user.last_name,
      email: session.user.email,
      phone: session.user.phone,
    });
  }, [session?.user]);

  useEffect(
    () => () => {
      if (photoPreview?.startsWith("blob:")) URL.revokeObjectURL(photoPreview);
    },
    [photoPreview],
  );

  async function saveProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const formData = new FormData();
      Object.entries(profile).forEach(([key, value]) => formData.append(key, value));
      if (selectedPhoto) formData.append("photo", selectedPhoto);
      await api.patch("users/me/", formData);
      await refreshSession();
      setSelectedPhoto(null);
      setPhotoPreview(null);
      toast.success(t("profile.profileUpdated"));
    } catch (error) {
      toast.error(t("profile.profileSaveError"), {
        description: error instanceof Error ? error.message : t("common.unknownError"),
      });
    } finally {
      setSavingProfile(false);
    }
  }

  function selectPhoto(e: ChangeEvent<HTMLInputElement>) {
    const file = e.currentTarget.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error(t("profile.photoTypeError"));
      e.currentTarget.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error(t("profile.photoSizeError"));
      e.currentTarget.value = "";
      return;
    }
    setSelectedPhoto(file);
    setPhotoPreview(URL.createObjectURL(file));
  }

  async function changePassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (password !== confirm) {
      toast.error(t("profile.passwordMismatch"));
      return;
    }
    setSaving(true);
    try {
      await api.patch("users/me/", { password });
      setPassword("");
      setConfirm("");
      toast.success(t("profile.passwordUpdated"));
    } catch (error) {
      toast.error(t("profile.changeError"), {
        description: error instanceof Error ? error.message : t("common.unknownError"),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-wide uppercase">
          {t("profile.title")}
        </h1>
        <p className="text-muted-foreground text-sm">{t("profile.summary")}</p>
      </div>

      <form onSubmit={saveProfile} className="panel space-y-5 p-5">
        <h2 className="font-semibold">{t("profile.personalInfo")}</h2>
        <div className="flex flex-wrap items-center gap-4">
          <Avatar className="size-20">
            <AvatarImage
              src={photoPreview ?? session?.user.photo ?? undefined}
              alt={t("profile.photo")}
            />
            <AvatarFallback className="text-lg font-semibold">
              {`${profile.first_name.trim().charAt(0)}${profile.last_name.trim().charAt(0)}`.toUpperCase() ||
                session?.user.username.slice(0, 2).toUpperCase() ||
                "?"}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-56 flex-1 space-y-2">
            <Label htmlFor="profile-photo">{t("profile.photo")}</Label>
            <Input id="profile-photo" type="file" accept="image/*" onChange={selectPhoto} />
            <p className="text-muted-foreground text-xs">{t("profile.photoHelp")}</p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="profile-first-name">{t("profile.firstName")}</Label>
            <Input
              id="profile-first-name"
              value={profile.first_name}
              onChange={(e) =>
                setProfile((current) => ({ ...current, first_name: e.target.value }))
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="profile-last-name">{t("profile.lastName")}</Label>
            <Input
              id="profile-last-name"
              value={profile.last_name}
              onChange={(e) => setProfile((current) => ({ ...current, last_name: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="profile-email">{t("users.email")}</Label>
            <Input
              id="profile-email"
              type="email"
              value={profile.email}
              onChange={(e) => setProfile((current) => ({ ...current, email: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="profile-phone">{t("settings.phone")}</Label>
            <Input
              id="profile-phone"
              type="tel"
              value={profile.phone}
              onChange={(e) => setProfile((current) => ({ ...current, phone: e.target.value }))}
            />
          </div>
        </div>
        <div className="flex items-center justify-between gap-4 border-t pt-4 text-sm">
          <span className="text-muted-foreground">{t("users.role")}</span>
          <span className="font-medium">
            {roles.map((assignedRole) => t(`role.${assignedRole}`)).join(" + ") || "—"}
          </span>
        </div>
        <Button type="submit" disabled={savingProfile}>
          {savingProfile ? t("profile.savingProfile") : t("profile.saveProfile")}
        </Button>
      </form>

      <div className="panel space-y-3 p-5 text-sm">
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">{t("profile.expires")}</span>
          <span className="font-medium">
            {expiresAt
              ? new Intl.DateTimeFormat({ fr: "fr-FR", en: "en", ar: "ar", zh: "zh" }[language], {
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(expiresAt))
              : "—"}
          </span>
        </div>
        <p className="text-muted-foreground text-xs">{t("profile.sessionSecurity")}</p>
      </div>

      <form onSubmit={changePassword} className="panel space-y-4 p-5">
        <h2 className="font-semibold">{t("profile.changePassword")}</h2>
        <div className="space-y-2">
          <Label htmlFor="new-password">{t("profile.newPassword")}</Label>
          <Input
            id="new-password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm-password">{t("profile.confirm")}</Label>
          <Input
            id="confirm-password"
            type="password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={saving}>
            {t("profile.update")}
          </Button>
          <Button type="button" variant="outline" onClick={() => void signOut()}>
            {t("profile.signOut")}
          </Button>
        </div>
      </form>
    </div>
  );
}
