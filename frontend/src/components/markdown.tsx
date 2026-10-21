import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders Markdown written in the admin area. Raw HTML is not rendered
 * (react-markdown's default), so content cannot inject scripts.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
