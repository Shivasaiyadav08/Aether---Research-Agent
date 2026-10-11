"use client";

import { ArrowUpRight, FileText, Globe2 } from "lucide-react";
import { useResearch } from "@/stores/research";
import { API_URL } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function SourceDialog() {
  const { selectedSource: source, workspaceId, update } = useResearch();
  const safeWebUrl =
    source?.url && /^https?:\/\//i.test(source.url) ? source.url : undefined;
  return (
    <Dialog
      open={!!source}
      onOpenChange={(open) => {
        if (!open) update({ selectedSource: null });
      }}
    >
      <DialogContent className="source-dialog">
        <div className="dialog-icon">
          {source?.kind === "web" ? (
            <Globe2 size={22} />
          ) : (
            <FileText size={22} />
          )}
        </div>
        <DialogTitle>{source?.name ?? "Source details"}</DialogTitle>
        <DialogDescription>
          {source
            ? `[${source.id}] · ${source.kind === "web" ? "Web evidence" : `Document evidence${source.page ? ` · Page ${source.page}` : ""}`}`
            : "Selected evidence"}
        </DialogDescription>
        {source?.relevance !== undefined && (
          <div className="source-metrics">
            <span>
              Relevance <strong>{Math.round(source.relevance * 100)}%</strong>
            </span>
            <span>
              Similarity{" "}
              <strong>{Math.round((source.similarity ?? 0) * 100)}%</strong>
            </span>
          </div>
        )}
        {source?.reason && <p className="source-reason">{source.reason}</p>}
        <div className="source-excerpt">{source?.text}</div>
        {source?.kind === "document" && source.document_id && (
          <Button asChild variant="secondary">
            <a
              href={`${API_URL}/workspaces/${encodeURIComponent(workspaceId)}/documents/${encodeURIComponent(source.document_id)}/file`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Download original <ArrowUpRight size={15} />
            </a>
          </Button>
        )}
        {safeWebUrl && (
          <Button asChild variant="secondary">
            <a href={safeWebUrl} target="_blank" rel="noopener noreferrer">
              Open web source <ArrowUpRight size={15} />
            </a>
          </Button>
        )}
        <small className="muted">
          Source references are checked for valid IDs. LLM grounding checks can
          still miss errors; inspect important claims yourself.
        </small>
      </DialogContent>
    </Dialog>
  );
}
