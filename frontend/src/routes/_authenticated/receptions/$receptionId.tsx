import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/receptions/detail/page";

export const Route = createFileRoute("/_authenticated/receptions/$receptionId")({
  ...PageRoute.options,
});
