import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/clients/page";

export const Route = createFileRoute("/_authenticated/clients")({
  ...PageRoute.options,
});
