import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/verification/page";

export const Route = createFileRoute("/verifier/$token")({
  ...PageRoute.options,
});
