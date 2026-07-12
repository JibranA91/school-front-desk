"use client";

import { useEffect, useRef, useState } from "react";

import { fetchGraph, type GraphEdge, type GraphNode } from "@/lib/frontDesk";

// Brightwheel-adjacent palette; types beyond this list fall back to gray.
const TYPE_COLORS: Record<string, string> = {
  Hours: "#5463D6",
  Tuition: "#3BBA6E",
  Enrollment: "#29B9BB",
  Health: "#E0556E",
  Meal: "#FF9D17",
  Attendance: "#8A6FE8",
  Safety: "#E08A0B",
  Behavior: "#C558B0",
  Communication: "#2F9BD6",
  Supplies: "#7A8AA3",
  Curriculum: "#4FA88B",
  Policy: "#6C74E0",
  Program: "#D98A3D",
  Holiday: "#D14B8F",
  General: "#9497A6",
};
const FALLBACK = "#9497A6";
const colorOf = (t: string) => TYPE_COLORS[t] ?? FALLBACK;

interface Sim extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
}

export default function KnowledgeGraph({ reloadToken = 0 }: { reloadToken?: number }) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState<[string, number][]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | null = null;

    (async () => {
      setLoading(true);
      setError(null);
      let data;
      try {
        data = await fetchGraph();
      } catch {
        if (!cancelled) {
          setError("Couldn't load the graph.");
          setLoading(false);
        }
        return;
      }
      if (cancelled) return;

      const wrap = wrapRef.current;
      const canvas = canvasRef.current;
      if (!wrap || !canvas) return;

      // Type counts for the legend.
      const byType = new Map<string, number>();
      for (const n of data.nodes) byType.set(n.type, (byType.get(n.type) ?? 0) + 1);
      setCounts([...byType.entries()].sort((a, b) => b[1] - a[1]));
      setTotal(data.nodes.length);
      setLoading(false);

      const width = wrap.clientWidth;
      const height = 380;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.scale(dpr, dpr);

      const cx = width / 2;
      const cy = height / 2;

      // Type anchors on a ring — gives each type its own neighborhood so the
      // structure reads even though most handbook nodes have no edges yet.
      const types = [...byType.keys()];
      const ringR = Math.min(width, height) * 0.34;
      const anchor = new Map<string, { x: number; y: number }>();
      types.forEach((t, i) => {
        const a = (i / types.length) * Math.PI * 2 - Math.PI / 2;
        anchor.set(t, { x: cx + Math.cos(a) * ringR, y: cy + Math.sin(a) * ringR });
      });

      // Seed a deterministic-ish layout near each node's type anchor.
      const nodes: Sim[] = data.nodes.map((n, i) => {
        const base = anchor.get(n.type)!;
        const ang = (i * 2.399963); // golden-angle spread
        const rad = 18 + (i % 7) * 6;
        return {
          ...n,
          x: base.x + Math.cos(ang) * rad,
          y: base.y + Math.sin(ang) * rad,
          vx: 0,
          vy: 0,
          r: n.handbook ? 4.5 : 7,
        };
      });
      const index = new Map(nodes.map((n) => [n.id, n]));
      const edges = data.edges.filter(
        (e) => index.has(e.source) && index.has(e.target),
      ) as GraphEdge[];

      let hover: Sim | null = null;
      const neighbors = new Set<string>();

      const onMove = (ev: MouseEvent) => {
        const rect = canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        let best: Sim | null = null;
        let bestD = 14 * 14;
        for (const n of nodes) {
          const dx = n.x - mx;
          const dy = n.y - my;
          const d = dx * dx + dy * dy;
          if (d < bestD) {
            bestD = d;
            best = n;
          }
        }
        if (best !== hover) {
          hover = best;
          neighbors.clear();
          if (best) {
            for (const e of edges) {
              if (e.source === best.id) neighbors.add(e.target);
              if (e.target === best.id) neighbors.add(e.source);
            }
          }
          canvas.style.cursor = best ? "pointer" : "default";
          draw();
        }
      };
      const onLeave = () => {
        if (hover) {
          hover = null;
          neighbors.clear();
          draw();
        }
      };
      canvas.addEventListener("mousemove", onMove);
      canvas.addEventListener("mouseleave", onLeave);

      function draw() {
        if (!ctx) return;
        ctx.clearRect(0, 0, width, height);

        // Edges. Authored typed edges (servedBy, …) read stronger than the
        // similarity ("related") links. When hovering, only the incident edges
        // stay visible so the node's neighborhood pops.
        for (const e of edges) {
          const a = index.get(e.source)!;
          const b = index.get(e.target)!;
          const incident = hover && (e.source === hover.id || e.target === hover.id);
          const authored = e.rel !== "related";
          if (hover && !incident) {
            ctx.strokeStyle = "#EAEEF5";
            ctx.lineWidth = 0.8;
          } else if (incident) {
            ctx.strokeStyle = "#5463D6";
            ctx.lineWidth = 1.8;
          } else if (authored) {
            ctx.strokeStyle = "#9FA8E0";
            ctx.lineWidth = 1.4;
          } else {
            ctx.strokeStyle = "#D9DFEA";
            ctx.lineWidth = 0.9;
          }
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }

        // Nodes
        for (const n of nodes) {
          const dim = hover && n !== hover && !neighbors.has(n.id);
          ctx.globalAlpha = dim ? 0.28 : 1;
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
          ctx.fillStyle = colorOf(n.type);
          ctx.fill();
          if (!n.handbook) {
            // Curated/seed nodes get a ring so they stand out from imports.
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#FFFFFF";
            ctx.stroke();
          }
          ctx.globalAlpha = 1;
        }

        // Hover label
        if (hover) {
          const label = hover.name;
          ctx.font =
            "600 12px ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif";
          const padX = 8;
          const w = ctx.measureText(label).width + padX * 2;
          const h = 22;
          let lx = hover.x + 10;
          let ly = hover.y - h - 6;
          if (lx + w > width) lx = width - w - 2;
          if (ly < 0) ly = hover.y + 12;
          ctx.fillStyle = "#1E2549";
          roundRect(ctx, lx, ly, w, h, 6);
          ctx.fill();
          ctx.fillStyle = "#FFFFFF";
          ctx.textBaseline = "middle";
          ctx.fillText(label, lx + padX, ly + h / 2);
          ctx.fillStyle = colorOf(hover.type);
          ctx.beginPath();
          ctx.arc(hover.x, hover.y, hover.r + 2.5, 0, Math.PI * 2);
          ctx.lineWidth = 2;
          ctx.strokeStyle = colorOf(hover.type);
          ctx.stroke();
        }
      }

      // ---- Force simulation (repulsion + type gravity + edge springs) ----
      let alpha = 1;
      let ticks = 0;
      const step = () => {
        // Repulsion (O(n^2) — fine for a couple hundred nodes).
        for (let i = 0; i < nodes.length; i++) {
          const a = nodes[i];
          for (let j = i + 1; j < nodes.length; j++) {
            const b = nodes[j];
            let dx = a.x - b.x;
            let dy = a.y - b.y;
            let d2 = dx * dx + dy * dy;
            if (d2 < 0.01) {
              dx = (i - j) * 0.1 + 0.1;
              dy = 0.1;
              d2 = dx * dx + dy * dy;
            }
            const force = (300 * alpha) / d2;
            const dist = Math.sqrt(d2);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.vx += fx;
            a.vy += fy;
            b.vx -= fx;
            b.vy -= fy;
          }
        }
        // Type gravity — pull each node toward its type anchor.
        for (const n of nodes) {
          const t = anchor.get(n.type)!;
          n.vx += (t.x - n.x) * 0.012 * alpha;
          n.vy += (t.y - n.y) * 0.012 * alpha;
        }
        // Edge springs.
        for (const e of edges) {
          const a = index.get(e.source)!;
          const b = index.get(e.target)!;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const k = ((dist - 66) / dist) * 0.035 * alpha;
          a.vx += dx * k;
          a.vy += dy * k;
          b.vx -= dx * k;
          b.vy -= dy * k;
        }
        // Integrate with damping + keep in bounds.
        for (const n of nodes) {
          n.vx *= 0.85;
          n.vy *= 0.85;
          n.x = Math.max(n.r + 2, Math.min(width - n.r - 2, n.x + n.vx));
          n.y = Math.max(n.r + 2, Math.min(height - n.r - 2, n.y + n.vy));
        }
        alpha *= 0.985;
        ticks++;
        draw();
        if (alpha > 0.02 && ticks < 600) {
          rafRef.current = requestAnimationFrame(step);
        }
      };
      step();

      cleanup = () => {
        canvas.removeEventListener("mousemove", onMove);
        canvas.removeEventListener("mouseleave", onLeave);
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
      };
    })();

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      cleanup?.();
    };
  }, [reloadToken]);

  return (
    <div
      style={{
        marginTop: 18,
        background: "#FFFFFF",
        border: "1px solid #EBEFF4",
        borderRadius: 20,
        padding: 20,
        boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          fontSize: 15,
          fontWeight: 700,
          color: "#18181D",
        }}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#5463D6"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="5" cy="6" r="3" />
          <circle cx="19" cy="6" r="3" />
          <circle cx="12" cy="18" r="3" />
          <path d="M8 6h8M6.5 8.5 10.5 15.5M17.5 8.5 13.5 15.5" />
        </svg>
        <span style={{ flex: 1 }}>Knowledge graph</span>
        <span style={{ fontSize: "12.5px", color: "#737685", fontWeight: 600 }}>
          {total} entities
        </span>
      </div>
      <div style={{ fontSize: "13.5px", color: "#5C5E6A", marginTop: 6, lineHeight: 1.5 }}>
        Every fact the front desk can draw on. Lines link related topics; curated
        facts have a white ring, imported handbook facts are solid. Hover any node
        to trace its connections.
      </div>

      <div
        ref={wrapRef}
        style={{
          position: "relative",
          marginTop: 14,
          borderRadius: 14,
          background: "#F7F9FB",
          border: "1px solid #EBEFF4",
          overflow: "hidden",
          minHeight: 380,
        }}
      >
        <canvas ref={canvasRef} style={{ display: "block" }} />
        {loading && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
              fontSize: 13,
              color: "#737685",
            }}
          >
            Loading graph…
          </div>
        )}
        {error && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
              fontSize: 13,
              color: "#CF193A",
            }}
          >
            {error}
          </div>
        )}
      </div>

      {counts.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 14 }}>
          {counts.map(([type, n]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 999,
                  background: colorOf(type),
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: "12.5px", color: "#5C5E6A", fontWeight: 600 }}>
                {type}
                <span style={{ color: "#A2A6B4", fontWeight: 500 }}> {n}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
