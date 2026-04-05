"use client";

interface KeywordInputProps {
  keyword: string;
  onRemove: () => void;
}

export default function KeywordInput({ keyword, onRemove }: KeywordInputProps) {
  return (
    <span className="keyword-pill inline-flex items-center gap-1 bg-blue-50 text-blue-700 text-sm font-medium px-3 py-1 rounded-full cursor-pointer">
      {keyword}
      <button
        onClick={onRemove}
        className="ml-1 text-blue-400 hover:text-red-500 transition-colors"
        title={`Remove "${keyword}"`}
      >
        ×
      </button>
    </span>
  );
}
