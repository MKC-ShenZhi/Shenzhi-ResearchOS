import type { Components } from "streamdown";

export const markdownElements = {
  p: ({ children }) => <p className="my-2">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
  h1: ({ children }) => <h2 className="mb-2 mt-5 text-lg font-semibold">{children}</h2>,
  h2: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1 mt-3 font-semibold">{children}</h4>,
  strong: ({ children }) => <strong>{children}</strong>,
  code: ({ children }) => <code className="rounded bg-chip px-1 font-mono text-[13px]">{children}</code>,
  pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-xl bg-panel p-3 leading-6">{children}</pre>,
  a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a>,
  table: ({ children }) => <div className="my-3 overflow-x-auto"><table className="w-full border-collapse">{children}</table></div>,
  th: ({ children }) => <th className="border border-line bg-sidebar px-3 py-2 text-left">{children}</th>,
  td: ({ children }) => <td className="border border-line px-3 py-2">{children}</td>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-primary/40 pl-3 text-muted">{children}</blockquote>,
} satisfies Components;
