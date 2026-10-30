import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/partenaires/page";

export const Route = createFileRoute("/_authenticated/partenaires")({
  ...PageRoute.options,
});
