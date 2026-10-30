import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/rapports-inventaire/page";

export const Route = createFileRoute("/_authenticated/rapports-inventaire")({
  ...PageRoute.options,
});
