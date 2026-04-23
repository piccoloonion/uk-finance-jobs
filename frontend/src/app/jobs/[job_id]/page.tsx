import { notFound } from "next/navigation";
import { Metadata } from "next";
import Link from "next/link";

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

async function getJob(job_id: string): Promise<Job | null> {
  try {
    const res = await fetch(`${API_URL}/job/${encodeURIComponent(job_id)}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: { job_id: string };
}): Promise<Metadata> {
  const job = await getJob(params.job_id);
  if (!job) {
    return {
      title: "Job Not Found | UK Finance Jobs",
    };
  }
  const title = `${job.title} at ${job.company} | UK Finance Jobs`;
  const description =
    job.description?.slice(0, 160).replace(/<[^>]*>/g, "") ||
    `Apply for ${job.title} at ${job.company}`;
  return {
    title,
    description,
    openGraph: {
      title: job.title,
      description,
      type: "article",
    },
    twitter: {
      card: "summary",
      title,
      description,
    },
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

export default async function JobPage({
  params,
}: {
  params: { job_id: string };
}) {
  const job = await getJob(params.job_id);
  if (!job) return notFound();

  const displaySalary = () => {
    if (job.salary_min && job.salary_max) {
      return `${formatSalary(job.salary_min)} - ${formatSalary(job.salary_max)}`;
    }
    if (job.salary_min) return formatSalary(job.salary_min);
    if (job.salary_max) return `Up to ${formatSalary(job.salary_max)}`;
    return "Salary not disclosed";
  };

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <Link
            href="/"
            className="text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            ← Back to jobs
          </Link>
        </div>
      </header>

      <article className="max-w-3xl mx-auto px-4 py-8">
        {/* Title */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 mb-6">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold text-gray-900 mb-2">
                {job.title}
              </h1>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-800">
                  {job.company}
                </span>
                <span className="text-gray-400">•</span>
                <span className="text-gray-600">{job.location}</span>
              </div>
            </div>
            {job.whitelist_match && (
              <span className="text-xs text-green-700 bg-green-50 px-3 py-1 rounded-full font-medium shrink-0">
                ⭐ Top Bank
              </span>
            )}
          </div>

          {/* Meta tags */}
          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <span className="text-sm font-medium text-blue-600 bg-blue-50 px-3 py-1 rounded-full">
              {displaySalary()}
              {job.salary_predicted && (
                <span className="text-amber-600 ml-1">(Est.)</span>
              )}
            </span>
            {job.contract_type && job.contract_type !== "permanent" && (
              <span className="text-sm text-purple-600 bg-purple-50 px-3 py-1 rounded-full">
                {job.contract_type}
              </span>
            )}
            {job.category && (
              <span className="text-sm text-gray-600 bg-gray-100 px-3 py-1 rounded-full">
                {job.category}
              </span>
            )}
            <span className="text-sm text-gray-500">
              Posted {daysAgo(job.created)}
            </span>
          </div>
        </div>

        {/* Description */}
        {job.description && (
          <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">
              Job Description
            </h2>
            <div
              className="text-gray-700 leading-relaxed whitespace-pre-line"
              dangerouslySetInnerHTML={{
                __html: job.description
                  .replace(/<[^>]*>/g, "")
                  .replace(/&nbsp;/g, " ")
                  .replace(/&amp;/g, "&")
                  .replace(/&lt;/g, "<")
                  .replace(/&gt;/g, ">"),
              }}
            />
          </div>
        )}

        {/* CTA */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <p className="text-sm text-gray-500">
                Apply through Adzuna — job ID: {job.id}
              </p>
            </div>
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-3 rounded-lg transition-colors text-center w-full sm:w-auto"
            >
              Apply for this role →
            </a>
          </div>
        </div>
      </article>
    </main>
  );
}
