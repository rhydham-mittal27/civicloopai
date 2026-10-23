import { Tabs } from "expo-router";
import { TabIcon, useFloatingTabBar } from "@civicloop/ui";

export default function TabLayout() {
  return (
    <Tabs screenOptions={useFloatingTabBar()}>
      <Tabs.Screen name="jobs" options={{ title: "Jobs", tabBarIcon: ({ color, focused }) => <TabIcon name="clipboard" color={String(color)} focused={focused} /> }} />
      <Tabs.Screen name="location" options={{ title: "Location", tabBarIcon: ({ color, focused }) => <TabIcon name="navigate-circle" color={String(color)} focused={focused} /> }} />
      <Tabs.Screen name="report" options={{ title: "Report", tabBarIcon: ({ color, focused }) => <TabIcon name="add" color={String(color)} focused={focused} raised /> }} />
      <Tabs.Screen name="account" options={{ title: "Account", tabBarIcon: ({ color, focused }) => <TabIcon name="person-circle" color={String(color)} focused={focused} /> }} />
    </Tabs>
  );
}
