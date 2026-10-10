import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-[#04201c] hover:bg-accent-strong",
        secondary: "bg-raised text-fg border border-line-strong hover:bg-[#1e242a]",
        ghost: "text-fg-muted hover:text-fg hover:bg-raised",
        danger: "bg-[#2a1416] text-danger border border-[#4a2226] hover:bg-[#341a1d]",
        outline: "border border-line-strong text-fg hover:bg-raised",
      },
      size: { sm: "h-7 px-2.5", md: "h-8 px-3", lg: "h-9 px-4", icon: "h-8 w-8" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => (
  <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";
