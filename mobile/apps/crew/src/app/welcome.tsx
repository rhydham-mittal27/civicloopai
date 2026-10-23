import { router } from "expo-router";
import { Intro, useIntro, type IntroSlide } from "@civicloop/ui";

const SLIDES: IntroSlide[] = [
  { icon: "clipboard", accents: ["flag", "checkmark-circle"], title: "Your jobs, most urgent first", text: "Cleanups your supervisor assigned to you, with the report, photos and location." },
  { icon: "map", accents: ["navigate", "time"], title: "A route planned for you", text: "When your supervisor approves a route, it shows up here in order. One tap to navigate to each stop." },
  { icon: "camera", accents: ["location", "shield-checkmark"], title: "Share location, send proof", text: "Share the vehicle position while you drive, and finish each job with a photo." },
];

export default function Welcome() {
  const { finish } = useIntro("crew");
  return (
    <Intro
      appName="CivicLoop Crew"
      slides={SLIDES}
      onDone={() => {
        finish();
        router.replace("/login");
      }}
    />
  );
}
