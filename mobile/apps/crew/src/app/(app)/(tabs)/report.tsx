import { router } from "expo-router";
import { ReportForm, TabHeader } from "@civicloop/features";
import { Muted, Screen } from "@civicloop/ui";

export default function ReportFromTheField() {
  return (
    <Screen tabs header={<TabHeader title="Report a site" />}>
      <Muted>Found waste on your round? Report it with a photo and a pin. A supervisor reviews it.</Muted>
      <ReportForm
        reporterType="field_worker"
        draftKey="civicloop.crew.draft"
        onCreated={(incident, failed, reason) =>
          router.push({
            pathname: "/incident/[id]",
            params: { id: incident.id, ...(failed ? { notice: `${failed} photo${failed > 1 ? "s" : ""} did not upload. Add ${failed > 1 ? "them" : "it"} again below.${reason ? ` (${reason})` : ""}` } : {}) },
          })
        }
      />
    </Screen>
  );
}
