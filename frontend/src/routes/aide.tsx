import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/help/page";

export const Route = createFileRoute("/aide")({
  ...PageRoute.options,
});
