export const STATUS_LABELS: Record<string, string> = {
  brouillon: "Brouillon",
  envoyee: "Envoyée",
  recue: "Reçue",
  annulee: "Annulée",
  draft: "Brouillon",
  submitted: "Soumise",
  approved: "Approuvée",
  partial_received: "Réception partielle",
  received: "Reçue",
  cancelled: "Annulée",
};

export function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "recue" || status === "received") return "default";
  if (status === "annulee" || status === "cancelled") return "destructive";
  if (["envoyee", "submitted", "approved", "partial_received"].includes(status)) return "secondary";
  return "outline";
}
