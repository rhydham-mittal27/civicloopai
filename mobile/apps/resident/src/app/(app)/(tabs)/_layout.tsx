import { Tabs } from "expo-router";
import { TabIcon, useFloatingTabBar } from "@civicloop/ui";

export default function TabLayout() {
  return (
    <Tabs screenOptions={useFloatingTabBar()}>
      <Tabs.Screen name="reports" options={{ title: "My reports", tabBarIcon: ({ color, focused }) => <TabIcon name="document-text" color={String(color)} focused={focused} /> }} />
      <Tabs.Screen name="new" options={{ title: "Report", tabBarIcon: ({ color, focused }) => <TabIcon name="add" color={String(color)} focused={focused} raised /> }} />
      <Tabs.Screen name="account" options={{ title: "Account", tabBarIcon: ({ color, focused }) => <TabIcon name="person-circle" color={String(color)} focused={focused} /> }} />
    </Tabs>
  );
}
