import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/platform/page";

export const Route = createFileRoute("/_authenticated/platform/")({
  ...PageRoute.options,
});
