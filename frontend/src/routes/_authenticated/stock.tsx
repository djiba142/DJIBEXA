import { createFileRoute } from "@tanstack/react-router";

import { Route as PageRoute } from "@/pages/stock/page";

export const Route = createFileRoute("/_authenticated/stock")({ ...PageRoute.options });
