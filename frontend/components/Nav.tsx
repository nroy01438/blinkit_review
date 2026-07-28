"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PRIMARY_LINKS = [
  { href: "/", label: "Home" },
  { href: "/themes", label: "Themes" },
  { href: "/insights", label: "Insights" },
  { href: "/ask", label: "Ask" },
  { href: "/upload", label: "Upload" },
];

const ADVANCED_LINKS = [
  { href: "/pipeline", label: "Pipeline" },
  { href: "/workflow", label: "Workflow" },
  { href: "/quality", label: "Quality" },
  { href: "/admin", label: "Admin" },
];

export default function Nav() {
  const pathname = usePathname();
  const linkClass = (href: string, muted = false) => {
    const active = pathname === href;
    if (active) return "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium bg-slate-900 text-white";
    return `shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition hover:bg-slate-100 ${
      muted ? "text-slate-400" : "text-slate-600"
    }`;
  };
  return (
    <nav className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-4 py-3">
        <span className="mr-4 shrink-0 text-lg font-semibold tracking-tight text-slate-900">AISLE</span>
        {PRIMARY_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className={linkClass(link.href)}>
            {link.label}
          </Link>
        ))}
        <span className="mx-2 h-5 shrink-0 border-l border-slate-200" aria-hidden />
        <span className="mr-1 shrink-0 text-xs uppercase tracking-wide text-slate-300">Advanced</span>
        {ADVANCED_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className={linkClass(link.href, true)}>
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
