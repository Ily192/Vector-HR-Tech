import { Slot } from "@radix-ui/react-slot";
import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";
import { cn } from "./utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold ring-offset-background transition-all duration-fast ease-out-quint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        // Primary CTA: Vortex orange — energía, rebeldía, jovialidad
        default:
          "bg-vector-orange-500 text-vector-cian-dark-500 hover:bg-vector-orange-400 hover:shadow-glow-orange active:bg-vector-orange-600",
        // Secondary: outline cian electric — tech accent
        secondary:
          "border border-vector-cian-electric-500 bg-transparent text-vector-cian-electric-700 hover:bg-vector-cian-electric-500/10 dark:text-vector-cian-electric-500",
        // Ghost: transparent
        ghost: "hover:bg-vector-cian-dark-500/5 dark:hover:bg-vector-cian-electric-500/10",
        // Destructive
        destructive: "bg-danger-500 text-white hover:bg-danger-700",
        // Link
        link: "text-vector-orange-500 underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-9 px-3 text-xs",
        default: "h-10 px-4 py-2",
        lg: "h-12 px-8 text-base",
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
