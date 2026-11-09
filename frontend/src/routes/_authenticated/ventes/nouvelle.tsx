import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/ventes/nouvelle")({
  head: () => ({
    meta: [
      { title: "Nouvelle vente — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Caisse rapide : recherche de pièces, panier, remise et encaissement en quelques clics.",
      },
      { property: "og:title", content: "Nouvelle vente — DJIBEXA" },
      { property: "og:description", content: "Interface de caisse du magasin." },
    ],
  }),
  component: lazyRouteComponent(() => import("@/pages/ventes/nouvelle/page"), "NouvelleVente"),
});
