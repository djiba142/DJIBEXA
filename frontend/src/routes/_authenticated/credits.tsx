import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/credits/page";

export const Route = createFileRoute("/_authenticated/credits")({
  ...PageRoute.options,
});
