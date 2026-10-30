import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/ventes/nouvelle/page";

export const Route = createFileRoute("/_authenticated/ventes/nouvelle")({
  ...PageRoute.options,
});
