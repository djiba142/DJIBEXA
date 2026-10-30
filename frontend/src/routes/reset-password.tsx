import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/reset-password/page";

export const Route = createFileRoute("/reset-password")({
  ...PageRoute.options,
});
