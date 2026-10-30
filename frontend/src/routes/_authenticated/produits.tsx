import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/produits/page";

export const Route = createFileRoute("/_authenticated/produits")({
  ...PageRoute.options,
});
