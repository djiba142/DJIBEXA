import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/devis-clients/page";

export const Route = createFileRoute("/_authenticated/devis-clients")({
  ...PageRoute.options,
});
