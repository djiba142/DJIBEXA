import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/recherche/page";

export const Route = createFileRoute("/_authenticated/recherche")({
  ...PageRoute.options,
});
