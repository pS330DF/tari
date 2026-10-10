import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "../../lib/utils";

export function Switch({ checked, onCheckedChange, disabled, id }: { checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean; id?: string }) {
  return (
    <SwitchPrimitive.Root
      id={id}
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      className={cn(
        "relative inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full border border-line-strong bg-raised transition-colors",
        "data-[state=checked]:border-accent/60 data-[state=checked]:bg-accent/80 disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      <SwitchPrimitive.Thumb className="block size-3 translate-x-[3px] rounded-full bg-fg shadow transition-transform data-[state=checked]:translate-x-[15px] data-[state=checked]:bg-[#04201c]" />
    </SwitchPrimitive.Root>
  );
}
