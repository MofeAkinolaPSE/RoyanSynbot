import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

/**
 * Sign-on-the-tablet pad: the HMO patient signs with a finger or stylus at the pharmacy, and the signature goes on
 * the HMO claims form for the visit. Produces a PNG File so it uploads through the existing signature endpoint.
 */
export function SignaturePad({ onChange }: { onChange: (file: File | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [empty, setEmpty] = useState(true);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ratio = window.devicePixelRatio || 1;
    c.width = c.offsetWidth * ratio;
    c.height = c.offsetHeight * ratio;
    const ctx = c.getContext("2d")!;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#111";
  }, []);

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const down = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const ctx = e.currentTarget.getContext("2d")!;
    const p = point(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  };
  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const ctx = e.currentTarget.getContext("2d")!;
    const p = point(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    if (empty) setEmpty(false);
  };
  const up = () => {
    if (!drawing.current) return;
    drawing.current = false;
    canvas.current?.toBlob((b) => onChange(b ? new File([b], "signature.png", { type: "image/png" }) : null), "image/png");
  };
  const clear = () => {
    const c = canvas.current;
    if (!c) return;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    setEmpty(true);
    onChange(null);
  };

  return (
    <div className="space-y-1">
      <canvas
        ref={canvas}
        className="h-32 w-full touch-none rounded border border-dashed border-border bg-white"
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up}
      />
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{empty ? "Patient signs here" : "Signed"}</span>
        <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={clear}>Clear</Button>
      </div>
    </div>
  );
}
