import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/rapports/page";

export const Route = createFileRoute("/_authenticated/rapports")({
  ...PageRoute.options,
});
