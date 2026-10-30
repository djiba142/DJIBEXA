import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/profil/page";

export const Route = createFileRoute("/_authenticated/profil")({
  ...PageRoute.options,
});
