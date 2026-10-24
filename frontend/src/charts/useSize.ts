import { useEffect, useRef, useState, type RefObject } from "react";

/** Tracks the rendered width of an element so SVG charts can lay themselves out responsively. */
export function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = (value: number) => setWidth(Math.max(280, Math.floor(value)));
    update(element.clientWidth || 640);
    const observer = new ResizeObserver(([entry]) => update(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}
