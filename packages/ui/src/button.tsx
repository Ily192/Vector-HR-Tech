import { Slot } from "@radix-ui/react-slot";
import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";
import { cn } from "./utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full border-[1.5px] border-transparent font-bold transition-[transform,background-color,border-color,box-shadow] duration-fast ease-out-quint active:translate-y-px focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-55",
  {
    variants: {
      variant: {
        // CTA: flame con texto en tinta (6,1:1). Uno por pantalla.
        default: "bg-flame-500 text-ink-900 shadow-cta hover:bg-flame-400 active:bg-flame-600",
        // Primario sobrio: tinta. En oscuro se invierte.
        ink: "bg-ink-900 text-white hover:bg-ink-800 dark:bg-ink-50 dark:text-ink-900 dark:hover:bg-white",
        // Secundario: superficie con borde, como los "fantasma" de la demo.
        secondary:
          "border-mist-200 bg-card text-foreground hover:border-ink-300 hover:bg-ink-50 dark:border-white/20 dark:bg-transparent dark:hover:border-white/50 dark:hover:bg-white/10",
        ghost: "text-foreground hover:bg-mist-100 dark:hover:bg-white/10",
        destructive: "bg-danger-500 text-white hover:bg-danger-700",
        link: "rounded-md px-0 text-aqua-700 underline-offset-4 hover:underline dark:text-aqua-300",
      },
      size: {
        sm: "h-9 px-4 text-sm",
        default: "h-11 px-5 text-[15px]",
        lg: "h-12 px-7 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        type={asChild ? undefined : (props.type ?? "button")}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
