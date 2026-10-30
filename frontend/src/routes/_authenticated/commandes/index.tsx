import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/commandes/list/page";

export const Route = createFileRoute("/_authenticated/commandes/")({
  ...PageRoute.options,
});
