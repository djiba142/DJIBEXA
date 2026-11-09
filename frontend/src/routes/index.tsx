import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "DJIBEXA — Solution numérique de gestion" },
      {
        name: "description",
        content:
          "DJIBEXA aide les entreprises à organiser leurs ventes, stocks, achats, clients et rapports dans un espace de gestion.",
      },
      { property: "og:title", content: "DJIBEXA — Solution numérique de gestion" },
      {
        property: "og:description",
        content: "Une gestion claire. Des décisions maîtrisées.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: lazyRouteComponent(() => import("@/pages/home/page"), "PublicHomePage"),
});
