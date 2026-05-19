"use client";

import { useEffect, useRef, useState } from "react";
import { fmtNumber } from "@/lib/format";
import type { Direction } from "@/lib/types";

interface PriceCellProps {
  price: number | null;
  direction?: Direction | null;
  className?: string;
}

export default function PriceCell({ price, direction, className = "" }: PriceCellProps) {
  const [flash, setFlash] = useState<"" | "price-flash-up" | "price-flash-down">("");
  const lastPriceRef = useRef<number | null>(null);

  useEffect(() => {
    if (price === null || price === undefined) return;
    const prev = lastPriceRef.current;
    if (prev !== null && prev !== price) {
      const dir = direction || (price > prev ? "up" : price < prev ? "down" : "flat");
      if (dir === "up") setFlash("price-flash-up");
      else if (dir === "down") setFlash("price-flash-down");
      const t = setTimeout(() => setFlash(""), 600);
      lastPriceRef.current = price;
      return () => clearTimeout(t);
    }
    lastPriceRef.current = price;
  }, [price, direction]);

  return (
    <span
      className={`inline-block px-1 rounded tabular ${flash} ${className}`}
    >
      {price === null || price === undefined ? "—" : fmtNumber(price)}
    </span>
  );
}
