import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/utilisateurs/page";

export const Route = createFileRoute("/_authenticated/utilisateurs")({
  ...PageRoute.options,
});
