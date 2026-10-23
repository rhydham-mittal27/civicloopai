"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLoad } from "@/lib/hooks";
import { AuthFrame } from "@/components/AuthFrame";
import { useToast } from "@/components/Toast";
import { Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [city, setCity] = useState("");
  const [pincode, setPincode] = useState("");
  const cities = useLoad(() => (city.trim().length >= 2 ? api.cities(city.trim()).catch(() => []) : Promise.resolve([])), [city]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.register({ name: name.trim(), email: email.trim(), password, city: city.trim(), pincode: pincode.trim() });
      const { access_token } = await api.login(email.trim(), password);
      signIn(access_token);
      toast("Account created");
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the account");
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <div>
        <h2>Create an account</h2>
        <p className="muted">Everything you see belongs to your city. New accounts can report incidents; supervisor and worker roles are assigned by a city admin.</p>
      </div>
      <form className="form" onSubmit={submit}>
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
        <div className="field">
          <label htmlFor="name">Full name</label>
          <input
            id="name"
            className="input"
            autoComplete="name"
            required
            maxLength={150}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            className="input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby="password-hint"
          />
          <span id="password-hint" className="hint">
            At least 12 characters.
          </span>
        </div>
        <div className="split">
          <div className="field">
            <label htmlFor="city">City</label>
            <input
              id="city"
              className="input"
              list="city-options"
              autoComplete="address-level2"
              required
              minLength={2}
              maxLength={120}
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
            <datalist id="city-options">
              {(cities.data ?? []).map((c) => (
                <option key={c.name} value={c.name} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor="pincode">Pincode</label>
            <input
              id="pincode"
              className="input mono"
              inputMode="numeric"
              autoComplete="postal-code"
              required
              pattern="[1-9][0-9]{5}"
              maxLength={6}
              placeholder="160017"
              value={pincode}
              onChange={(e) => setPincode(e.target.value.replace(/\D/g, ""))}
            />
          </div>
        </div>
        <span className="hint">
          {cities.data?.some((c) => c.name.toLowerCase() === city.trim().toLowerCase())
            ? "You will join this city."
            : city.trim().length > 1
              ? "This city is new here. Check the spelling: you will be its first account, and the platform team confirms new cities."
              : "Type your city. Known cities are suggested."}
        </span>
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy && <Spinner />}
          {busy ? "Creating account" : "Create account"}
        </button>
      </form>
      <p className="auth-switch">
        Already registered? <Link href="/login">Sign in</Link>
      </p>
    </AuthFrame>
  );
}
