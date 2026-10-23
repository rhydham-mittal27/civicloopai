"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { Dashboard } from "@/components/dashboard/Dashboard";
import { Loading } from "@/components/ui";
import { isSupervisor, useAuth } from "@/lib/auth";

export default function HomePage() {
  return (
    <AppShell>
      <Home />
    </AppShell>
  );
}

/** Supervisors land on the command center. Everyone else goes straight to their incident list. */
function Home() {
  const { principal } = useAuth();
  const router = useRouter();
  const supervisor = isSupervisor(principal?.role);

  useEffect(() => {
    if (principal && !supervisor) router.replace("/incidents");
  }, [principal, supervisor, router]);

  return supervisor ? <Dashboard /> : <Loading />;
}
