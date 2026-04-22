"use client";

import { useState, useEffect } from "react";
import JobCard from "@/components/JobCard";
import KeywordInput from "@/components/KeywordInput";
import SubscribeModal from "@/components/SubscribeModal";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_predicted: boolean;
  created: string;
  description: string;
  url: string;
  category: string;
  whitelist_match: boolean;
  contract_type: string;
}

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [keywords, setKeywords] = useState<string[]>([
    "Senior Software Engineer",
    "Senior Data Engineer",
  ]);
  const [daysAgo, setDaysAgo] = useState(7);
  const [lastFetchSource, setLastFetchSource] = useState<string>("");
  const [showSubscribe, setShowSubscribe] = useState(false);
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(20);
  const [totalJobs, setTotalJobs] = useState(0);

  const fetchJobs = async (newPage = page) => {
    setLoading(true);
    setLastFetchSource("");
    try {
      const res = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keywords,
          days_ago: daysAgo,
          limit,
          offset: newPage * limit,
        }),
      });

      if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
      }

      const data = await res.json();
      setJobs(data);
      setPage(newPage);

      const totalHeader = res.headers.get("x-total-count");
      setTotalJobs(totalHeader ? parseInt(totalHeader, 10) : data.length);

      setLastFetchSource("Data loaded");
    } catch (error) {
      console.error("Fetch error:", error);
      setJobs([]);
      setTotalJobs(0);
      setLastFetchSource("Error loading jobs");
    } finally {
      setLoading(false);
    }
  };

  const handleKeywordChange = (newKeywords: string[]) => {
    setKeywords(newKeywords);
    setPage(0);
    setTimeout(() => fetchJobs(0), 100);
  };

  const addKeyword = (keyword: string) => {
    if (keyword.trim() && !keywords.includes(keyword.trim())) {
      handleKeywordChange([...keywords, keyword.trim()]);
    }
  };

  const removeKeyword = (keyword: string) => {
    handleKeywordChange(keywords.filter((k) => k !== keyword));
  };

  useEffect(() => {
    fetchJobs(0);
  }, []);

  const whitelistCount = jobs.filter((j) => j.whitelist_match).length;
  const financeCount = jobs.length - whitelistCount;
  const totalPages = Math.ceil(totalJobs / limit);
  const startIdx = totalJobs > 0 ? page * limit + 1 : 0;
  const endIdx = Math.min((page + 1) * limit, totalJobs);

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
          {/* Title row */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
              UK Finance Jobs
            </h1>
            <div className="flex items-center gap-2">
              {lastFetchSource && (
                <span className="bg-gray-100 px-3 py-1 rounded-full text-sm text-gray-500 self-start sm:self-auto">
                  {lastFetchSource}
                </span>
              )}
              <button
                onClick={() => setShowSubscribe(true)}
                className="bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors whitespace-nowrap"
              >
                Get Job Alerts
              </button>
            </div>
          </div>

          <p className="text-gray-600 text-xs sm:text-sm mb-4">
            Aggregated from Adzuna • UK Financial Sector • Daily Cached
          </p>

          {/* Controls - stacked on mobile, inline on desktop */}
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              {/* Date Filter */}
              <div className="flex items-center gap-2 bg-gray-100 rounded-lg px-3 py-2">
                <label className="text-sm font-medium text-gray-700">
                  Date Range:
                </label>
                <select
                  value={daysAgo}
                  onChange={(e) => {
                    setDaysAgo(Number(e.target.value));
                    setPage(0);
                    setTimeout(() => fetchJobs(0), 100);
                  }}
                  className="bg-white border rounded px-2 py-1 text-sm"
                >
                  <option value={7}>Last 7 days</option>
                  <option value={14}>Last 14 days</option>
                </select>
              </div>

              {/* Page size */}
              <div className="flex items-center gap-2 bg-gray-100 rounded-lg px-3 py-2">
                <label className="text-sm font-medium text-gray-700">Per page:</label>
                <select
                  value={limit}
                  onChange={(e) => {
                    setLimit(Number(e.target.value));
                    setPage(0);
                    setTimeout(() => fetchJobs(0), 100);
                  }}
                  className="bg-white border rounded px-2 py-1 text-sm"
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </select>
              </div>

              {/* Refresh */}
              <button
                onClick={() => fetchJobs(page)}
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg disabled:opacity-50 transition-colors"
              >
                {loading ? "Loading..." : "Refresh Jobs"}
              </button>
            </div>

            {/* Keyword Pills */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-gray-500 font-medium">Keywords:</span>
              {keywords.map((kw) => (
                <KeywordInput
                  key={kw}
                  keyword={kw}
                  onRemove={() => removeKeyword(kw)}
                />
              ))}
              <input
                type="text"
                placeholder="+ Add keyword..."
                className="border rounded-lg px-3 py-1 text-sm w-full sm:w-40"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const val = (e.target as HTMLInputElement).value;
                    addKeyword(val);
                    (e.target as HTMLInputElement).value = "";
                  }
                }}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Results */}
      <section className="max-w-6xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
        {/* Summary - stacked on mobile */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6 gap-2">
          <h2 className="text-base sm:text-lg font-semibold text-gray-800">
            {loading ? (
              <span className="animate-pulse">Searching for jobs...</span>
            ) : (
              `${totalJobs} jobs found` +
              (totalJobs > 0 ? ` (showing ${startIdx}-${endIdx})` : "")
            )}
          </h2>
          <div className="flex items-center gap-3 sm:gap-4 text-xs sm:text-sm text-gray-500">
            <span>
              {whitelistCount} whitelist match{whitelistCount !== 1 ? "es" : ""}
            </span>
            <span className="text-gray-300">|</span>
            <span>
              {financeCount} finance-relevant
            </span>
          </div>
        </div>

        {/* Job Grid */}
        {jobs.length === 0 && !loading ? (
          <div className="text-center py-16">
            <p className="text-gray-500 text-lg">No jobs found</p>
            <p className="text-gray-400 text-sm mt-2">
              Try different keywords or expand the date range
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3 sm:gap-4">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalJobs > 0 && (
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
            <button
              onClick={() => fetchJobs(page - 1)}
              disabled={page === 0 || loading}
              className="bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              ← Previous
            </button>
            <span className="text-sm text-gray-600">
              Page {page + 1} of {totalPages || 1}
            </span>
            <button
              onClick={() => fetchJobs(page + 1)}
              disabled={page >= totalPages - 1 || loading}
              className="bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next →
            </button>
          </div>
        )}
      </section>

      <SubscribeModal
        isOpen={showSubscribe}
        onClose={() => setShowSubscribe(false)}
        apiBaseUrl={API_URL}
      />
    </main>
  );
}
