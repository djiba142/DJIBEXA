import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowLeft, Eye, EyeOff, KeyRound, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/auth")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Connexion — ERP DJIBEXA" },
      {
        name: "description",
        content: "Connectez-vous à DJIBEXA.",
      },
      { property: "og:title", content: "Connexion — ERP DJIBEXA" },
      {
        property: "og:description",
        content: "Une gestion claire. Des décisions maîtrisées.",
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
  const [showPassword, setShowPassword] = useState(false);
  const [identifier, setIdentifier] = useState("");
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
      await signIn(identifier, password);
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
    <main className="min-h-screen bg-[#F5F7FA] lg:grid lg:grid-cols-2">
      <section className="relative hidden min-h-screen overflow-hidden bg-[#10243A] p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-14">
        <img
          src="/brand/djibexa-office-dark.jpeg"
          alt=""
          aria-hidden="true"
          className="absolute inset-0 size-full object-cover"
          fetchPriority="high"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-[#10243A]/55 via-[#10243A]/75 to-[#10243A]" />
        <Link
          to="/"
          className="relative z-10 inline-flex w-fit rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
        >
          <img src="/brand/djibexa-logo.svg" alt={t("landing.logoAlt")} className="w-56" />
        </Link>
        <div className="relative z-10 mx-auto w-full max-w-xl">
          <div className="space-y-4">
            <h1 className="text-3xl font-bold leading-tight tracking-tight xl:text-4xl">
              {t("auth.tagline")}
            </h1>
            <p className="max-w-lg leading-7 text-white/75">{t("auth.brandDescription")}</p>
          </div>
        </div>
        <p className="relative z-10 text-sm text-white/60">{t("auth.accessReserved")}</p>
      </section>

      <section className="flex min-h-screen flex-col px-5 py-5 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between gap-4">
          <Link
            to="/"
            className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2678C8] lg:hidden"
          >
            <img src="/brand/djibexa-logo.svg" alt={t("landing.logoAlt")} className="w-40" />
          </Link>
          <span className="hidden flex-1 lg:block" />
          <LanguageSwitcher />
        </header>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-md">
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="mb-7 -ms-3 text-[#526174] hover:text-[#10243A]"
              aria-label={t("auth.accessibilityReturn")}
            >
              <Link to="/">
                <ArrowLeft aria-hidden="true" />
                {t("auth.back")}
              </Link>
            </Button>

            {resetMode ? (
              <>
                <div className="mb-6 flex size-12 items-center justify-center rounded-xl bg-[#E7F0F9] text-[#174A78]">
                  <KeyRound className="size-6" aria-hidden="true" />
                </div>
                <h2 className="text-3xl font-bold tracking-tight text-[#10243A]">
                  {t("auth.forgotPassword")}
                </h2>
                <p className="mt-3 mb-7 leading-6 text-[#526174]">{t("auth.resetInstructions")}</p>
                <form
                  onSubmit={handlePasswordReset}
                  className="space-y-5 rounded-2xl border border-[#DCE3EB] bg-white p-5 shadow-sm sm:p-7"
                >
                  <div className="space-y-2">
                    <Label htmlFor="reset-email" className="text-[#202B38]">
                      {t("auth.emailAddress")}
                    </Label>
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
                      className="h-11 border-[#C9D3DE] focus-visible:ring-[#2678C8]"
                    />
                  </div>
                  <Button
                    type="submit"
                    className="h-11 w-full bg-[#174A78] text-white hover:bg-[#10243A]"
                    disabled={resetLoading}
                  >
                    <Mail aria-hidden="true" />
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
                    className="h-11 w-full text-[#174A78]"
                    onClick={() => setResetMode(false)}
                  >
                    <ArrowLeft aria-hidden="true" />
                    {t("auth.backToLogin")}
                  </Button>
                </form>
              </>
            ) : (
              <>
                <div className="mb-6 flex size-12 items-center justify-center rounded-xl bg-[#E7F0F9] text-[#174A78]">
                  <LockKeyhole className="size-6" aria-hidden="true" />
                </div>
                <h1 className="text-3xl font-bold tracking-tight text-[#10243A]">
                  {t("auth.workspace")}
                </h1>
                <p className="mt-3 mb-7 leading-6 text-[#526174]">{t("auth.loginDescription")}</p>

                <form
                  onSubmit={handleSubmit}
                  className="space-y-5 rounded-2xl border border-[#DCE3EB] bg-white p-5 shadow-sm sm:p-7"
                >
                  <div className="space-y-2">
                    <Label htmlFor="identifier" className="text-[#202B38]">
                      {t("auth.identifier")}
                    </Label>
                    <Input
                      id="identifier"
                      type="text"
                      autoComplete="username"
                      required
                      value={identifier}
                      onChange={(e) => setIdentifier(e.target.value)}
                      placeholder={t("auth.identifierPlaceholder")}
                      className="h-11 border-[#C9D3DE] focus-visible:ring-[#2678C8]"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password" className="text-[#202B38]">
                      {t("auth.password")}
                    </Label>
                    <div className="relative">
                      <Input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder={t("auth.passwordPlaceholder")}
                        className="h-11 border-[#C9D3DE] pe-12 focus-visible:ring-[#2678C8]"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="absolute end-1 top-1/2 -translate-y-1/2 text-[#526174] hover:bg-[#F5F7FA]"
                        aria-label={showPassword ? t("auth.hidePassword") : t("auth.showPassword")}
                        aria-pressed={showPassword}
                        onClick={() => setShowPassword((shown) => !shown)}
                      >
                        {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                      </Button>
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto px-0 text-sm text-[#174A78]"
                      onClick={() => {
                        setResetRequested(false);
                        setResetMode(true);
                      }}
                    >
                      {t("auth.forgotPassword")}
                    </Button>
                  </div>
                  <Button
                    type="submit"
                    className="h-11 w-full bg-[#174A78] text-white hover:bg-[#10243A]"
                    disabled={loading}
                  >
                    {t("auth.login")}
                  </Button>
                  <p className="flex items-start gap-2 text-sm leading-5 text-[#526174]">
                    <ShieldCheck
                      className="mt-0.5 size-4 shrink-0 text-[#2678C8]"
                      aria-hidden="true"
                    />
                    {t("auth.accessReserved")}
                  </p>
                </form>
              </>
            )}
          </div>
        </div>
        <footer className="text-center text-xs text-[#718096]">
          © {new Date().getFullYear()} DJIBEXA
        </footer>
      </section>
    </main>
  );
}
