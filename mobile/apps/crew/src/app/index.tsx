import { Redirect } from "expo-router";
import { Loading, Screen, useIntro, useSession } from "@civicloop/ui";

/** The address "/" sends people to the right place: the app when signed in, the welcome screens on first launch, otherwise sign in. */
export default function Index() {
  const { status } = useSession();
  const { seen } = useIntro("crew");
  if (status === "signedIn") return <Redirect href="/jobs" />;
  if (seen === null) {
    return (
      <Screen scroll={false}>
        <Loading />
      </Screen>
    );
  }
  return <Redirect href={seen ? "/login" : "/welcome"} />;
}
