import { Toaster as Sonner } from "sonner";
import { brandMark } from "@/lib/brand-assets";

type ToasterProps = React.ComponentProps<typeof Sonner>;

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      className="toaster group"
      icons={{
        success: <img src={brandMark} alt="" className="size-4" />,
        info: <img src={brandMark} alt="" className="size-4" />,
        warning: <img src={brandMark} alt="" className="size-4" />,
        error: <img src={brandMark} alt="" className="size-4" />,
        loading: <img src={brandMark} alt="" className="size-4" />,
      }}
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton: "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton: "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
