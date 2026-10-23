import { BrandMark } from "./ui";

const LOOP = ["Observe", "Understand", "Predict", "Prioritise", "Act", "Verify", "Learn"];

export function AuthFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth">
      <section className="auth-aside">
        <span className="brand">
          <BrandMark />
          CivicLoop
        </span>
        <div>
          <h1>Clean the right street first.</h1>
          <p>
            Residents and field workers report waste sites. Supervisors review what the AI found, approve the work and
            check the cleanup. Nothing is closed without evidence.
          </p>
        </div>
        <ol className="loop" aria-label="How CivicLoop works">
          {LOOP.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
      <main className="auth-main">
        <div className="auth-card">{children}</div>
      </main>
    </div>
  );
}
