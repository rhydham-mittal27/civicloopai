import { router } from "expo-router";
import { Intro, useIntro, type IntroSlide } from "@civicloop/ui";

const SLIDES: IntroSlide[] = [
  { icon: "camera", accents: ["location", "checkmark-circle"], title: "See waste? Report it", text: "Take a photo, drop a pin, and send it. It takes under a minute." },
  { icon: "people", accents: ["shield-checkmark", "eye"], title: "A person reviews every report", text: "A supervisor checks each report before anyone is sent, so crews go where they are needed." },
  { icon: "notifications", accents: ["time", "checkmark-done"], title: "Follow it until it is clean", text: "Watch your report move from reviewed to assigned to cleaned, with proof from the crew." },
];

export default function Welcome() {
  const { finish } = useIntro("resident");
  return (
    <Intro
      appName="CivicLoop"
      slides={SLIDES}
      onDone={() => {
        finish();
        router.replace("/login");
      }}
    />
  );
}
