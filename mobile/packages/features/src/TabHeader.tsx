import { router } from "expo-router";
import type { ReactNode } from "react";
import { AppBar, useSession } from "@civicloop/ui";

/** The bar pinned above a main screen: where you are, who is signed in, and a shortcut to the account page. */
export function TabHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  const { me } = useSession();
  return <AppBar title={title} subtitle={subtitle ?? (me ? `${me.name} · ${me.city}` : undefined)} name={me?.name} right={right} onProfile={() => router.navigate("/account")} />;
}
