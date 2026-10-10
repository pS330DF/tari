import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

export function Select<T extends string>({ value, onValueChange, options, placeholder, width = "w-56" }: {
  value: T | ""; onValueChange: (v: T) => void; options: { value: T; label: string; hint?: string }[]; placeholder?: string; width?: string;
}) {
  return (
    <SelectPrimitive.Root value={value || undefined} onValueChange={(v) => onValueChange(v as T)}>
      <SelectPrimitive.Trigger className={`inline-flex h-8 ${width} items-center justify-between gap-2 rounded-md border border-line-strong bg-panel px-2.5 text-[13px] text-fg outline-none hover:bg-raised focus-visible:ring-2 focus-visible:ring-accent/50`}>
        <span className="truncate"><SelectPrimitive.Value placeholder={placeholder} /></span>
        <SelectPrimitive.Icon><ChevronDown className="size-3.5 text-fg-muted" /></SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content position="popper" sideOffset={4} className="z-50 max-h-80 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border border-line-strong bg-[#11161a] shadow-xl shadow-black/50">
          <SelectPrimitive.Viewport className="p-1">
            {options.map((o) => (
              <SelectPrimitive.Item key={o.value} value={o.value} className="relative flex cursor-default select-none items-center rounded px-2 py-1.5 pr-7 text-[13px] text-fg outline-none data-[highlighted]:bg-raised">
                <div className="flex flex-col">
                  <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                  {o.hint && <span className="text-[11px] text-fg-subtle">{o.hint}</span>}
                </div>
                <SelectPrimitive.ItemIndicator className="absolute right-2"><Check className="size-3.5 text-accent" /></SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
