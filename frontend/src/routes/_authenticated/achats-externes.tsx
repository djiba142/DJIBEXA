import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/achats-externes")({
  beforeLoad: () => {
    throw redirect({ href: "/credits?tab=suppliers" });
  },
});
