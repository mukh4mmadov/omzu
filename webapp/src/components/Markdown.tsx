import { Check, Copy } from "lucide-react";
import { memo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function CodeBlock({ children, lang }: { children: ReactNode; lang?: string }) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, "");
  return (
    <div className="my-3 overflow-hidden rounded-xl border border-line bg-code">
      <div className="flex items-center justify-between border-b border-line px-3 py-1.5 text-xs text-faint">
        <span>{lang || "kod"}</span>
        <button
          className="flex items-center gap-1 rounded-md px-1.5 py-0.5 transition hover:bg-surface-2 hover:text-fg"
          onClick={async () => {
            try { await navigator.clipboard.writeText(text); } catch {  }
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          }}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Nusxalandi" : "Nusxa"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3.5 font-mono text-[13px] leading-relaxed"><code>{text}</code></pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
          pre: ({ children }) => <>{children}</>,
          code: ({ className, children }) => {
            const lang = /language-(\w+)/.exec(className || "")?.[1];
            const isBlock = Boolean(lang) || String(children).includes("\n");
            return isBlock ? <CodeBlock lang={lang}>{children}</CodeBlock> : <code>{children}</code>;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
