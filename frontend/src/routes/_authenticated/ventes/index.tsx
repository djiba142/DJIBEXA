import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/ventes/list/page";

export const Route = createFileRoute("/_authenticated/ventes/")({
  ...PageRoute.options,
});
