import { router } from "expo-router";
import { ReportForm, TabHeader } from "@civicloop/features";
import { Muted, Screen } from "@civicloop/ui";

export default function NewReport() {
  return (
    <Screen tabs header={<TabHeader title="Report waste" />}>
      <Muted>Add a photo and a pin. A supervisor reviews every report.</Muted>
      <ReportForm
        reporterType="resident"
        draftKey="civicloop.resident.draft"
        onCreated={(incident, failed) =>
          router.push({
            pathname: "/incident/[id]",
            params: { id: incident.id, ...(failed ? { notice: `${failed} photo${failed > 1 ? "s" : ""} did not upload. Add ${failed > 1 ? "them" : "it"} again below.` } : {}) },
          })
        }
      />
    </Screen>
  );
}
