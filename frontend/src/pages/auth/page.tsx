import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowLeft, KeyRound, Mail } from "lucide-react";
import { toast } from "sonner";

import { brandLogo } from "@/lib/brand-assets";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/auth")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Connexion — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Accès sécurisé à l'ERP de gestion commerciale de DJIBEXA : ventes, stock, produits et clients.",
      },
      { property: "og:title", content: "Connexion — ERP DJIBEXA" },
      {
        property: "og:description",
        content: "Espace de gestion réservé au personnel de DJIBEXA, Madina Conakry.",
      },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const { session, signIn, isPlatformAdmin } = useAuth();
  const { t } = useLocale();
  const [loading, setLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetMode, setResetMode] = useState(false);
  const [resetRequested, setResetRequested] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    document.title = t("auth.documentTitle");
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = t("auth.metaDescription");
    const openGraphTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    if (openGraphTitle) openGraphTitle.content = t("auth.documentTitle");
    const openGraphDescription = document.querySelector<HTMLMetaElement>(
      'meta[property="og:description"]',
    );
    if (openGraphDescription) openGraphDescription.content = t("auth.metaDescription");
  }, [t]);

  useEffect(() => {
    if (session) {
      navigate({
        to: session.user.must_change_password
          ? "/change-password"
          : isPlatformAdmin
            ? "/platform"
            : "/dashboard",
        replace: true,
      });
    }
  }, [session, isPlatformAdmin, navigate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await signIn(email, password);
    } catch (error) {
      toast.error(t("auth.loginFailed"), {
        description: error instanceof Error ? error.message : t("common.unknownError"),
      });
    } finally {
      setLoading(false);
    }
  }

  async function handlePasswordReset(e: React.FormEvent) {
    e.preventDefault();
    setResetLoading(true);
    try {
      await api.post("users/pin-reset/request/", { email });
      setResetRequested(true);
      toast.success(t("auth.resetSuccess"), { description: t("auth.resetSent") });
    } catch (error) {
      toast.error(t("auth.resetFailed"), {
        description: error instanceof Error ? error.message : t("common.unknownError"),
      });
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="brand-gradient relative hidden flex-col justify-between p-10 lg:flex">
        <img src={brandLogo} alt={t("landing.logoAlt")} className="w-56 rounded-xl" />
        <div className="text-primary-foreground space-y-4">
          <h1 className="text-4xl font-bold tracking-wide uppercase">{t("auth.tagline")}</h1>
          <p className="text-primary-foreground/75 max-w-md text-sm">
            {t("auth.brandDescription")}
          </p>
        </div>
      </div>

      <div className="relative flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="mb-6"
            aria-label={t("auth.accessibilityReturn")}
          >
            <Link to="/">
              <ArrowLeft />
              {t("auth.back")}
            </Link>
          </Button>
          <img src={brandLogo} alt={t("landing.logoAlt")} className="mx-auto mb-6 w-40 lg:hidden" />
          {resetMode ? (
            <>
              <h2 className="text-3xl font-bold uppercase">{t("auth.forgotPassword")}</h2>
              <p className="text-muted-foreground mb-6 text-sm">{t("auth.resetInstructions")}</p>
              <form onSubmit={handlePasswordReset} className="panel space-y-4 p-5">
                <div className="space-y-2">
                  <Label htmlFor="reset-email">{t("auth.emailAddress")}</Label>
                  <Input
                    id="reset-email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      setResetRequested(false);
                    }}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={resetLoading}>
                  <Mail />
                  {resetLoading ? t("auth.sending") : t("auth.sendLink")}
                </Button>
                {resetRequested && (
                  <p className="text-sm text-emerald-700" role="status">
                    {t("auth.resetSent")}
                  </p>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  onClick={() => setResetMode(false)}
                >
                  <ArrowLeft />
                  {t("auth.backToLogin")}
                </Button>
              </form>
            </>
          ) : (
            <>
              <h2 className="text-3xl font-bold uppercase">{t("auth.workspace")}</h2>
              <p className="text-muted-foreground mb-6 text-sm">{t("auth.loginDescription")}</p>

              <form onSubmit={handleSubmit} className="panel space-y-4 p-5">
                <div className="space-y-2">
                  <Label htmlFor="email">{t("auth.email")}</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">{t("auth.password")}</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                <div className="flex justify-end">
                  <Button
                    type="button"
                    variant="link"
                    className="h-auto px-0 text-sm"
                    onClick={() => {
                      setResetRequested(false);
                      setResetMode(true);
                    }}
                  >
                    <KeyRound />
                    {t("auth.forgotPassword")}
                  </Button>
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {t("auth.login")}
                </Button>
                <p className="text-muted-foreground text-xs">{t("auth.accountsNote")}</p>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
