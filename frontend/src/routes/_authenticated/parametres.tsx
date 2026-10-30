import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/parametres/page";

export const Route = createFileRoute("/_authenticated/parametres")({
  ...PageRoute.options,
});
