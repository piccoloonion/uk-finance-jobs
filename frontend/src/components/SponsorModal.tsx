"use client";

import { useState } from "react";

interface SponsorModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiBaseUrl: string;
}

export default function SponsorModal({ isOpen, onClose, apiBaseUrl }: SponsorModalProps) {
  const [step, setStep] = useState<"form" | "redirecting" | "error">("form");
  const [jobTitle, setJobTitle] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg("");

    try {
      const res = await fetch(`${apiBaseUrl}/sponsor-checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_title: jobTitle.trim(),
          company_name: companyName.trim(),
          job_url: jobUrl.trim(),
          contact_email: contactEmail.toLowerCase().trim(),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to create checkout");
      }

      setStep("redirecting");

      // Redirect to Stripe Checkout
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setErrorMsg(message);
      setStep("error");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setStep("form");
    setJobTitle("");
    setCompanyName("");
    setJobUrl("");
    setContactEmail("");
    setErrorMsg("");
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
        {/* Close button */}
        <div className="flex justify-end p-4">
          <button
            onClick={() => { onClose(); resetForm(); }}
            className="text-gray-400 hover:text-gray-600 text-xl"
          >
            &times;
          </button>
        </div>

        {step === "form" && (
          <div className="px-6 pb-6">
            <h2 className="text-xl font-bold text-gray-900 mb-2">Sponsor a Job Listing</h2>
            <p className="text-sm text-gray-500 mb-6">
              Get your job featured at the top of UK Finance Jobs for 30 days. <strong>£49 one-time payment.</strong>
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Job Title *</label>
                <input
                  type="text"
                  required
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  placeholder="e.g. Senior Python Developer"
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Company Name *</label>
                <input
                  type="text"
                  required
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. Barclays"
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Job URL *</label>
                <input
                  type="url"
                  required
                  value={jobUrl}
                  onChange={(e) => setJobUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Contact Email *</label>
                <input
                  type="email"
                  required
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
                <p className="text-xs text-gray-400 mt-1">We&apos;ll send a confirmation to this email.</p>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-xs text-amber-800">
                  <strong>What you get:</strong>
                </p>
                <ul className="text-xs text-amber-700 mt-1 list-disc list-inside space-y-0.5">
                  <li>⭐ Featured badge at the top of search results</li>
                  <li>30 days of prominent visibility</li>
                  <li>Direct link to your application page</li>
                  <li>No recurring fees — one-time £49</li>
                </ul>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-amber-500 hover:bg-amber-600 text-white font-medium py-2.5 rounded-lg disabled:opacity-50 transition-colors"
              >
                {submitting ? "Creating checkout..." : "Continue to Payment — £49"}
              </button>

              <p className="text-xs text-gray-400 text-center">
                Secure payment via Stripe. Your listing goes live immediately after payment.
              </p>
            </form>
          </div>
        )}

        {step === "redirecting" && (
          <div className="px-6 pb-6 text-center">
            <div className="text-4xl mb-4">🔄</div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Redirecting to payment...</h2>
            <p className="text-sm text-gray-500 mb-6">
              Taking you to Stripe&apos;s secure checkout to complete your payment.
            </p>
          </div>
        )}

        {step === "error" && (
          <div className="px-6 pb-6 text-center">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Something went wrong</h2>
            <p className="text-sm text-red-500 mb-6">{errorMsg}</p>
            <button
              onClick={() => setStep("form")}
              className="bg-amber-500 hover:bg-amber-600 text-white font-medium py-2.5 px-6 rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}