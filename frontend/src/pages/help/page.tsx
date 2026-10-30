import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, BookOpen, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import type { Permission } from "@/lib/permissions";

export const PageRoute = createFileRoute("/aide")({
  head: () => ({
    meta: [
      { title: "Aide et tutoriels — ERP DJIBEXA" },
      {
        name: "description",
        content: "Guides pas à pas pour les tâches courantes dans DJIBEXA.",
      },
    ],
  }),
  component: HelpPage,
});

type HelpRoute =
  | "/ventes/nouvelle"
  | "/recherche"
  | "/commandes"
  | "/entrepots"
  | "/inventaire"
  | "/ventes"
  | "/parametres";

type Tutorial = {
  id: string;
  route: HelpRoute;
  permission: Permission;
  steps: string[];
};

const tutorials: Tutorial[] = [
  {
    id: "sale",
    route: "/ventes/nouvelle",
    permission: "sales.create",
    steps: [
      "help.tutorial.sale.step1",
      "help.tutorial.sale.step2",
      "help.tutorial.sale.step3",
      "help.tutorial.sale.step4",
    ],
  },
  {
    id: "search",
    route: "/recherche",
    permission: "products.view",
    steps: [
      "help.tutorial.search.step1",
      "help.tutorial.search.step2",
      "help.tutorial.search.step3",
      "help.tutorial.search.step4",
    ],
  },
  {
    id: "order",
    route: "/commandes",
    permission: "purchases.view",
    steps: [
      "help.tutorial.order.step1",
      "help.tutorial.order.step2",
      "help.tutorial.order.step3",
      "help.tutorial.order.step4",
    ],
  },
  {
    id: "transfer",
    route: "/entrepots",
    permission: "warehouses.view",
    steps: [
      "help.tutorial.transfer.step1",
      "help.tutorial.transfer.step2",
      "help.tutorial.transfer.step3",
    ],
  },
  {
    id: "inventory",
    route: "/inventaire",
    permission: "inventory.view",
    steps: [
      "help.tutorial.inventory.step1",
      "help.tutorial.inventory.step2",
      "help.tutorial.inventory.step3",
    ],
  },
  {
    id: "cancel",
    route: "/ventes",
    permission: "sales.manage",
    steps: [
      "help.tutorial.cancel.step1",
      "help.tutorial.cancel.step2",
      "help.tutorial.cancel.step3",
    ],
  },
  {
    id: "company",
    route: "/parametres",
    permission: "users.manage",
    steps: [
      "help.tutorial.company.step1",
      "help.tutorial.company.step2",
      "help.tutorial.company.step3",
      "help.tutorial.company.step4",
    ],
  },
];

const faqIds = ["invoice", "stock", "seller", "session", "partner"];

function HelpPage() {
  const { t } = useLocale();
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const filteredTutorials = useMemo(
    () =>
      tutorials.filter((tutorial) => {
        if (!can(tutorial.permission)) return false;
        const searchableText = [
          t(`help.tutorial.${tutorial.id}.title`),
          ...tutorial.steps.map((step) => t(step)),
        ]
          .join(" ")
          .toLocaleLowerCase();
        return searchableText.includes(normalizedSearch);
      }),
    [can, normalizedSearch, t],
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="space-y-2">
        <h1 className="font-display flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
          <BookOpen className="text-primary size-6" aria-hidden="true" />
          {t("help.title")}
        </h1>
        <p className="text-muted-foreground">{t("help.description")}</p>
      </header>

      <div className="relative max-w-2xl">
        <Search
          className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          id="help-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("help.search")}
          aria-label={t("help.search")}
          className="pl-9"
        />
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label={t("help.title")}>
        {filteredTutorials.map((tutorial) => (
          <Card key={tutorial.id} className="flex h-full flex-col">
            <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
              <CardTitle className="text-lg">{t(`help.tutorial.${tutorial.id}.title`)}</CardTitle>
              <Button asChild variant="outline" size="sm" className="shrink-0">
                <Link to={tutorial.route}>
                  {t("help.open")}
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent className="flex-1">
              <ol className="text-muted-foreground list-inside list-decimal space-y-2 text-sm">
                {tutorial.steps.map((step) => (
                  <li key={step}>{t(step)}</li>
                ))}
              </ol>
            </CardContent>
          </Card>
        ))}
        {filteredTutorials.length === 0 && (
          <p className="text-muted-foreground col-span-full rounded-lg border border-dashed p-6 text-center">
            {t("help.noResults")}
          </p>
        )}
      </section>

      <section className="space-y-3" aria-labelledby="help-faq-heading">
        <h2 id="help-faq-heading" className="text-xl font-semibold">
          {t("help.faq")}
        </h2>
        <div className="divide-y rounded-lg border">
          {faqIds.map((id) => (
            <details key={id} className="p-4">
              <summary className="cursor-pointer font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {t(`help.faq.${id}.question`)}
              </summary>
              <p className="text-muted-foreground mt-3 text-sm">{t(`help.faq.${id}.answer`)}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
