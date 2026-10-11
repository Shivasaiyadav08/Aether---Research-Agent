"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  FileText,
  FolderOpen,
  Globe2,
  MessageSquare,
  Plus,
  ArrowUp,
  Paperclip,
} from "lucide-react";
import { BrandMark } from "@/components/brand";

const sources = [
  {
    id: "D1",
    name: "Literature review.pdf",
    kind: "Document · page 12",
    text: "The review distinguishes the quality of retrieved evidence from the quality of the final answer. Both require evaluation against the original research question.",
  },
  {
    id: "D2",
    name: "Research notes.md",
    kind: "Document · 4 passages",
    text: "A useful evaluation checks relevance, coverage, and whether each claim can be traced back to a supporting source.",
  },
  {
    id: "W1",
    name: "Evaluation framework",
    kind: "Web source",
    text: "Testing on representative questions makes gaps in retrieval and answer grounding easier to identify.",
  },
];

export function ResearchPreview() {
  const [tab, setTab] = useState("research");
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div
      className="product-preview"
      aria-label="Interactive example of the Aether workspace"
    >
      <aside className="preview-sidebar">
        <div className="preview-brand">
          <BrandMark />
          <strong>aether</strong>
        </div>
        <div className="preview-workspace">
          <FolderOpen size={14} /> Literature review <ChevronRight size={12} />
        </div>
        <Link href="/research" className="preview-new">
          <Plus size={15} /> New research
        </Link>
        <span className="preview-label">Workspace</span>
        <button
          aria-pressed={tab === "research"}
          className={tab === "research" ? "selected" : ""}
          onClick={() => setTab("research")}
        >
          <MessageSquare size={15} /> Research
        </button>
        <button
          aria-pressed={tab === "documents"}
          className={tab === "documents" ? "selected" : ""}
          onClick={() => setTab("documents")}
        >
          <BookOpen size={15} /> Documents
        </button>
        <span className="preview-label">Recent research</span>
        <span className="preview-recent">Evaluating research quality</span>
        <span className="preview-recent">A closer look at retrieval</span>
        <div className="preview-profile">
          <span>JD</span>
          <div>
            Personal workspace<small>Your sources, connected</small>
          </div>
        </div>
      </aside>
      <div className="preview-main">
        <header>
          <span>
            Literature review <ChevronRight size={12} />{" "}
            <strong>{tab === "research" ? "Research" : "Documents"}</strong>
          </span>
          <span className="preview-example">Example workspace</span>
        </header>
        {tab === "research" ? (
          <>
            <div className="preview-reading">
              <div className="preview-question">
                <span>Your question</span>
                <h3>What makes a research answer reliable?</h3>
              </div>
              <div className="preview-answer-label">
                <BrandMark />
                <strong>Aether</strong>
                <span>
                  <Check size={12} /> Evidence reviewed
                </span>
              </div>
              <h4>Clarity starts with the evidence.</h4>
              <p>
                A reliable answer connects its claims to relevant sources,
                acknowledges gaps, and makes its reasoning easy to inspect.{" "}
                <button
                  className="inline-citation"
                  onClick={() => setSelected("D1")}
                >
                  D1
                </button>
              </p>
              <div className="preview-finding">
                <span>01</span>
                <div>
                  <strong>Look beyond relevance</strong>
                  <p>
                    A source can be related to a question without providing
                    enough evidence to answer it.
                  </p>
                </div>
              </div>
              <div className="preview-finding">
                <span>02</span>
                <div>
                  <strong>Keep every claim traceable</strong>
                  <p>
                    Read the original passage alongside the answer to understand
                    its context.{" "}
                    <button
                      className="inline-citation"
                      onClick={() => setSelected("D2")}
                    >
                      D2
                    </button>
                  </p>
                </div>
              </div>
              <div className="preview-answer-footer">
                <FileText size={12} /> 2 documents <span>·</span>
                <Globe2 size={12} /> 1 web source
              </div>
            </div>
            <Link href="/research" className="preview-composer">
              <span>Ask a follow-up question…</span>
              <div>
                <Paperclip size={15} />
                <small>Work with your sources</small>
                <small className="preview-model">Gemini · Free tier</small>
                <small
                  className="preview-relevance"
                  title="Example: minimum relevance score for each document chunk. Adjust it in your research workspace."
                >
                  Relevance 50%
                </small>
                <span>
                  <ArrowUp size={16} />
                </span>
              </div>
            </Link>
          </>
        ) : (
          <div className="preview-reading preview-library">
            <span className="eyebrow">Your sources</span>
            <h3>Knowledge library</h3>
            <p>One place for the material behind your research.</p>
            {sources
              .filter((s) => s.id.startsWith("D"))
              .map((s) => (
                <button key={s.id} onClick={() => setSelected(s.id)}>
                  <FileText size={20} />
                  <span>
                    <strong>{s.name}</strong>
                    <small>{s.kind}</small>
                  </span>
                  <Check size={14} />
                </button>
              ))}
            <Link className="button button-outline" href="/research">
              <Plus size={14} /> Add your documents
            </Link>
          </div>
        )}
      </div>
      <aside className="preview-sources">
        <header>
          <BookOpen size={14} />
          <strong>Evidence</strong>
          <span>03</span>
        </header>
        <div className="preview-source-body">
          <span className="eyebrow">Behind the answer</span>
          <p>A clear path back to the source.</p>
          {sources.map((source) => (
            <button
              key={source.id}
              className={`preview-source ${selected === source.id ? "expanded" : ""}`}
              aria-expanded={selected === source.id}
              onClick={() =>
                setSelected(selected === source.id ? null : source.id)
              }
            >
              <span className="citation-tag">{source.id}</span>
              <strong>{source.name}</strong>
              <small>{source.kind}</small>
              <ArrowUpRight size={13} />
              {selected === source.id && <p>{source.text}</p>}
            </button>
          ))}
          <div className="preview-source-note">
            <Check size={13} />
            <span>
              Document evidence, expanded with web research when needed.
            </span>
          </div>
        </div>
      </aside>
    </div>
  );
}
