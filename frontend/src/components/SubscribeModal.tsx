"use client";

import { useState } from "react";

interface SubscribeModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiBaseUrl: string;
}

export default function SubscribeModal({ isOpen, onClose, apiBaseUrl }: SubscribeModalProps) {
  const [step, setStep] = useState<"form" | "success" | "error">("form");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("Software Engineer");
  const [location, setLocation] = useState("London");
  const [daysAgo, setDaysAgo] = useState(7);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg("");

    try {
      const res = await fetch(`${apiBaseUrl}/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.toLowerCase().trim(),
          name: name.trim() || undefined,
          keywords: keywords
            .split(",")
            .map((k) => k.trim())
            .filter(Boolean),
          location: location.trim() || "London",
          days_ago: daysAgo,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to subscribe");
      }

      setStep("success");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setErrorMsg(message);
      setStep("error");
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
        {/* Close button */}
        <div className="flex justify-end p-4">
          <button
            onClick={() => { onClose(); setStep("form"); }}
            className="text-gray-400 hover:text-gray-600 text-xl"
          >
            &times;
          </button>
        </div>

        {step === "form" && (
          <div className="px-6 pb-6">
            <h2 className="text-xl font-bold text-gray-900 mb-2">Get Daily Job Alerts</h2>
            <p className="text-sm text-gray-500 mb-6">
              We&apos;ll email you new UK finance jobs matching your criteria. Free tier gets weekly alerts.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name (optional)</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Keywords (comma separated) *
                </label>
                <input
                  type="text"
                  required
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="Software Engineer, Data Scientist"
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="London, Manchester, Remote..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Show jobs from last
                </label>
                <select
                  value={daysAgo}
                  onChange={(e) => setDaysAgo(Number(e.target.value))}
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value={3}>3 days</option>
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                  <option value={30}>30 days</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg disabled:opacity-50 transition-colors"
              >
                {submitting ? "Subscribing..." : "Subscribe for Free"}
              </button>

              <p className="text-xs text-gray-400 text-center">
                Free: weekly alerts &middot; Upgrade to <strong>&#163;5/mo</strong> for daily alerts
              </p>
            </form>
          </div>
        )}

        {step === "success" && (
          <div className="px-6 pb-6 text-center">
            <div className="text-4xl mb-4">🎉</div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">You&apos;re subscribed!</h2>
            <p className="text-sm text-gray-500 mb-6">
              We&apos;ll send your first job alert to <strong>{email}</strong> within 24 hours.
            </p>
            <button
              onClick={() => { onClose(); setStep("form"); }}
              className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-lg transition-colors"
            >
              Done
            </button>
          </div>
        )}

        {step === "error" && (
          <div className="px-6 pb-6 text-center">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Something went wrong</h2>
            <p className="text-sm text-red-500 mb-6">{errorMsg}</p>
            <button
              onClick={() => setStep("form")}
              className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
