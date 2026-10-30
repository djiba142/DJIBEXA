import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/stock-echantillons/page";

export const Route = createFileRoute("/_authenticated/stock-echantillons")({
  ...PageRoute.options,
});
