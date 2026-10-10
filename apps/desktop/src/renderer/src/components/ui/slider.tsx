import * as SliderPrimitive from "@radix-ui/react-slider";

export function Slider({ value, min, max, step, onValueChange, onValueCommit }: {
  value: number; min: number; max: number; step: number; onValueChange?: (v: number) => void; onValueCommit?: (v: number) => void;
}) {
  return (
    <SliderPrimitive.Root
      className="relative flex h-5 w-full touch-none select-none items-center"
      value={[value]}
      min={min}
      max={max}
      step={step}
      onValueChange={(v) => onValueChange?.(v[0]!)}
      onValueCommit={(v) => onValueCommit?.(v[0]!)}
    >
      <SliderPrimitive.Track className="relative h-1 grow overflow-hidden rounded-full bg-line-strong">
        <SliderPrimitive.Range className="absolute h-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block size-3.5 rounded-full border border-accent bg-bg shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50" />
    </SliderPrimitive.Root>
  );
}
