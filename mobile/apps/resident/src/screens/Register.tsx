import { useEffect, useState } from "react";
import { Row } from "@civicloop/ui";
import { isValidPincode, type CityOption } from "@civicloop/core";
import { router } from "expo-router";
import { Banner, Button, Card, Chip, Field, Muted, Screen, Title, TopBar, space, useAction, useSession } from "@civicloop/ui";

export function RegisterScreen() {
  const { api, signInWithToken, serverUrl } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [city, setCity] = useState("");
  const [pincode, setPincode] = useState("");
  const [suggestions, setSuggestions] = useState<CityOption[]>([]);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const { busy, error, run } = useAction();

  // known cities appear as you type; a name nobody has used yet opens a new city
  useEffect(() => {
    const q = city.trim();
    if (q.length < 2 || !serverUrl) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(() => {
      api.cities(q).then(setSuggestions).catch(() => setSuggestions([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [city, api, serverUrl]);

  const exact = suggestions.some((c) => c.name.toLowerCase() === city.trim().toLowerCase());

  const submit = async () => {
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = "Enter your name.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) found.email = "Enter a valid email address.";
    if (password.length < 12) found.password = "Use at least 12 characters.";
    if (city.trim().length < 2) found.city = "Enter your city.";
    if (!isValidPincode(pincode)) found.pincode = "A pincode has 6 digits and does not start with 0.";
    setProblems(found);
    if (Object.keys(found).length) return;
    await run("register", async () => {
      await api.register({ name: name.trim(), email: email.trim(), password, city: city.trim(), pincode });
      const { access_token } = await api.login(email.trim(), password);
      await signInWithToken(access_token);
    });
  };

  return (
    <Screen edges={["top", "bottom"]}>
      <TopBar title="Create an account" onBack={() => router.back()} />
      <Title>Create an account</Title>
      <Muted>Everything you see belongs to your city. You can report waste and follow each report until it is cleaned.</Muted>
      <Card>
        <Field label="Full name" value={name} onChangeText={setName} autoComplete="name" textContentType="name" error={problems.name} />
        <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" textContentType="username" error={problems.email} />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="new-password" textContentType="newPassword" hint="At least 12 characters." error={problems.password} />
        <Field
          label="City"
          value={city}
          onChangeText={setCity}
          autoCapitalize="words"
          error={problems.city}
          hint={
            exact
              ? "You will join this city."
              : city.trim().length > 1
                ? "This city is new here. Check the spelling: you will be its first account, and the platform team confirms new cities."
                : "Type your city. Known cities are suggested."
          }
        />
        {suggestions.length > 0 && !exact ? (
          <Row style={{ flexWrap: "wrap", gap: space.sm }}>
            {suggestions.map((c) => (
              <Chip key={c.name} label={c.name} onPress={() => setCity(c.name)} />
            ))}
          </Row>
        ) : null}
        <Field label="Pincode" value={pincode} onChangeText={(t) => setPincode(t.replace(/\D/g, "").slice(0, 6))} keyboardType="number-pad" maxLength={6} placeholder="160017" error={problems.pincode} />
        {error ? <Banner tone="bad">{error}</Banner> : null}
        <Button label="Create account" busy={busy === "register"} disabled={!serverUrl} onPress={submit} />
        {!serverUrl ? <Banner tone="warn">Set the server address on the sign-in screen first.</Banner> : null}
      </Card>
    </Screen>
  );
}
