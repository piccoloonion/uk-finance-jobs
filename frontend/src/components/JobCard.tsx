"use client";

interface JobCardProps {
  job: {
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
  };
}

function formatSalary(amount: number | null): string {
  if (!amount) return "";
  if (amount >= 1000) {
    return `£${Math.round(amount / 1000)}k`;
  }
  return `£${amount}`;
}

function daysAgo(dateStr: string): string {
  const created = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - created.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

export default function JobCard({ job }: JobCardProps) {
  const displaySalary = (): string => {
    if (job.salary_min && job.salary_max) {
      return `${formatSalary(job.salary_min)} - ${formatSalary(job.salary_max)}`;
    }
    if (job.salary_min) {
      return formatSalary(job.salary_min);
    }
    return "Salary not disclosed";
  };

  const predictedTag = job.salary_predicted ? (
    <span className="text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
      Est.
    </span>
  ) : null;

  const contractTag = job.contract_type && job.contract_type !== 'permanent' ? (
    <span className={`text-xs px-2 py-0.5 rounded-full ${
      job.contract_type === 'contract' 
        ? 'text-purple-600 bg-purple-50' 
        : 'text-gray-600 bg-gray-50'
    }`}>
      {job.contract_type}
    </span>
  ) : null;

  return (
    <a
      href={job.url}
      target="_blank"
      rel="noopener noreferrer"
      className="job-card block bg-white rounded-xl p-5 shadow-sm border border-gray-100 hover:border-blue-200"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-gray-900 truncate">
              {job.title}
            </h3>
            {job.whitelist_match && (
              <span className="text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
                ⭐ Whitelist
              </span>
            )}
          </div>

          {/* Company & Location */}
          <div className="flex items-center gap-2 mt-1 text-sm text-gray-600">
            <span className="font-medium text-gray-800">{job.company}</span>
            <span className="text-gray-400">•</span>
            <span>{job.location}</span>
          </div>

          {/* Tags row */}
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-sm font-medium text-blue-600">
              {displaySalary()}
            </span>
            {predictedTag}
            {contractTag}
            {job.category && (
              <span className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded-full">
                {job.category}
              </span>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="ml-4 flex flex-col items-end gap-1 shrink-0">
          <span className="text-sm text-gray-500 whitespace-nowrap">
            {daysAgo(job.created)}
          </span>
          <span className="text-blue-600 hover:text-blue-700 text-sm font-medium">
            Apply →
          </span>
        </div>
      </div>

      {/* Description preview */}
      {job.description && (
        <p className="text-sm text-gray-500 mt-3 line-clamp-2 leading-relaxed">
          {job.description.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ')}
        </p>
      )}
    </a>
  );
}
