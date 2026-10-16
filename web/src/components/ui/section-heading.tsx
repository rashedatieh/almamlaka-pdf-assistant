import type * as React from "react";

/** almamlakatv.com section heading: bold red text behind a thick red bar at the start edge. */
export function SectionHeading({ children, as: Tag = "h2" }: { children: React.ReactNode; as?: "h2" | "h3" }) {
  return (
    <Tag className="border-s-4 border-primary ps-2.5 text-base font-bold leading-tight text-primary dark:text-accent-foreground">
      {children}
    </Tag>
  );
}
