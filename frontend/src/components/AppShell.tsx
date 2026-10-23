"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { api, ROLE_LABEL, setTenant, type Role } from "@/lib/api";
import { NAV, resolveLabel, type BadgeKey, type NavItem } from "@/lib/access";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import { BrandMark, Icon } from "./ui";

/* ---- the collapsed/expanded choice lives in localStorage so it survives navigation and reloads */
const KEY = "civicloop.sidebar";
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
};
const readCollapsed = () => {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
};
const writeCollapsed = (value: boolean) => {
  try {
    localStorage.setItem(KEY, value ? "1" : "0");
  } catch {
    /* the choice just will not persist */
  }
  listeners.forEach((cb) => cb());
};

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 5 ? "Good night" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

function initials(name: string | undefined, fallback: string): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return fallback.slice(0, 2).toUpperCase();
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function AppShell({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const { principal, ready, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const collapsed = useSyncExternalStore(subscribe, readCollapsed, () => false);
  const me = useLoad(() => (principal ? api.me() : Promise.resolve(null)), [principal?.userId]);
  const isPlatform = !!me.data?.is_platform_admin;
  const cityList = useLoad(() => (isPlatform ? api.platformCities() : Promise.resolve([])), [isPlatform]);
  const badges = useLoad(() => (principal ? api.badges() : Promise.resolve({})), [principal?.userId]);
  const reloadBadges = badges.reload;

  useEffect(() => {
    if (ready && !principal) router.replace("/login");
  }, [ready, principal, router]);

  // counts of waiting work refresh quietly, and whenever the person moves to another page
  useEffect(() => {
    reloadBadges();
    const timer = setInterval(reloadBadges, 45_000);
    return () => clearInterval(timer);
  }, [pathname, reloadBadges]);

  if (!ready || !principal) {
    return <div className="boot">Loading…</div>;
  }

  const role = principal.role;
  const items = NAV.filter((item) => item.roles.includes(role) && (!item.platform || isPlatform));
  const allowed = !roles || roles.includes(role);
  const counts: Partial<Record<BadgeKey, number>> = badges.data ?? {};

  const current = (href: string) => {
    if (href === "/") return pathname === "/";
    // the incident list also owns the pages of individual incidents, but not the "report" form
    if (href === "/incidents") return pathname === "/incidents" || (pathname.startsWith("/incidents/") && pathname !== "/incidents/new");
    return pathname === href || pathname.startsWith(href + "/");
  };

  const link = (item: NavItem) => {
    const label = resolveLabel(item, role);
    const n = item.badge ? (counts[item.badge] ?? 0) : 0;
    return (
      <Link key={item.href} href={item.href} className="side-link" aria-current={current(item.href) ? "page" : undefined} title={collapsed ? label : undefined}>
        <Icon name={item.icon} />
        <span className="side-text">{label}</span>
        {n > 0 && (
          <span className="nbadge" aria-label={`${n} waiting`}>
            {n > 99 ? "99+" : n}
          </span>
        )}
      </Link>
    );
  };

  const group = (key: NavItem["group"], label: string, card: boolean) => {
    const rows = items.filter((item) => item.group === key);
    if (rows.length === 0) return null;
    return (
      <section className="side-group" data-card={card ? "" : undefined} aria-label={label}>
        <div className="side-label">
          <span className="side-text">{label}</span>
          <b>{rows.length}</b>
        </div>
        <nav className="side-nav" aria-label={label}>
          {rows.map(link)}
        </nav>
      </section>
    );
  };

  const name = me.data?.name;
  return (
    <div className="shell" data-collapsed={collapsed ? "" : undefined}>
      <aside className="side" aria-label="Sidebar">
        <div className="side-head">
          <Link href="/" className="avatar" aria-label="CivicLoop home" title={name ?? ROLE_LABEL[role]}>
            {initials(name, role)}
          </Link>
          <div className="side-who side-text">
            <span className="hello">{greeting()}</span>
            <strong>{name ?? ROLE_LABEL[role]}</strong>
            <span className="who-role">
              {ROLE_LABEL[role]}
              {me.data?.city ? ` · ${me.data.city}` : ""}
            </span>
          </div>
          <button type="button" className="side-toggle" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={() => writeCollapsed(!collapsed)}>
            <Icon name="chev" />
          </button>
        </div>

        <div className="side-scroll">
          {isPlatform && (cityList.data?.length ?? 0) > 1 && (
            <label className="city-switch side-text">
              <span>Working in</span>
              <select
                className="select select-sm"
                value={me.data?.tenant_id ?? ""}
                onChange={(e) => {
                  setTenant(e.target.value);
                  window.location.reload();
                }}
              >
                {cityList.data?.filter((c) => c.is_active).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {group("main", "Menu", false)}
          {group("tools", "Tools", true)}
          {group("admin", "Administration", true)}
        </div>

        <div className="side-foot">
          <Link href="/incidents/new" className="side-cta" aria-label="Report incident">
            <span className="cta-plus">
              <Icon name="plus" />
            </span>
            <span className="cta-text side-text">
              <strong>Report incident</strong>
              <small>Photo, place and a few words</small>
            </span>
          </Link>
          <button
            type="button"
            className="side-out"
            title={collapsed ? "Sign out" : undefined}
            onClick={() => {
              signOut();
              router.replace("/login");
            }}
          >
            <Icon name="out" />
            <span className="side-text">Sign out</span>
          </button>
          <span className="side-brand side-text">
            <BrandMark />
            CivicLoop
          </span>
        </div>
      </aside>

      <main className={pathname === "/" ? "page page-wide" : "page"}>
        {allowed ? (
          children
        ) : (
          <div className="empty" style={{ justifyItems: "start", textAlign: "left", padding: "24px 0" }}>
            <h1>This page is not available to your role</h1>
            <p>You are signed in as {ROLE_LABEL[role].toLowerCase()}. Ask an admin if you need more access.</p>
            <Link href="/incidents" className="btn">
              Back to incidents
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}
