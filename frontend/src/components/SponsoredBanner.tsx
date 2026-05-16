"use client";

interface SponsoredBannerProps {
  job: {
    id: string;
    title: string;
    company: string;
    url: string;
  };
}

export default function SponsoredBanner({ job }: SponsoredBannerProps) {
  return (
    <div className="bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Featured tag */}
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
              ⭐ Featured
            </span>
            <span className="text-xs text-amber-500 font-medium">Sponsored</span>
          </div>

          {/* Job info */}
          <h3 className="text-sm font-semibold text-gray-900 truncate">
            {job.title}
          </h3>
          <p className="text-xs text-gray-600 mt-0.5">
            {job.company}
          </p>
        </div>

        {/* View button */}
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap"
        >
          View Job
        </a>
      </div>
    </div>
  );
}