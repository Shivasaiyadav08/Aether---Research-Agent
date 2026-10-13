"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, FolderOpen, Plus, Settings } from "lucide-react";
import type { Workspace } from "@/types";

interface WorkspacePickerProps {
  workspaces: Workspace[];
  workspaceId: string;
  busy: boolean;
  connecting: boolean;
  onSelect: (id: string) => void;
  onOpenManage: () => void;
}

export function WorkspacePicker({
  workspaces,
  workspaceId,
  busy,
  connecting,
  onSelect,
  onOpenManage,
}: WorkspacePickerProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentWorkspace = workspaces.find((w) => w.id === workspaceId);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="workspace-picker-wrapper" ref={containerRef}>
      <div className={`workspace-picker-custom ${open ? "open" : ""}`}>
        <button
          type="button"
          className="workspace-trigger"
          disabled={busy || connecting || !workspaces.length}
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-label="Switch workspace"
        >
          <FolderOpen size={15} className="workspace-folder-icon" />
          <span className="workspace-current-name">
            {connecting
              ? "Connecting…"
              : currentWorkspace?.name || "No workspace"}
          </span>
          <ChevronDown
            size={13}
            className={`workspace-chevron ${open ? "rotated" : ""}`}
          />
        </button>
        <button
          type="button"
          className="workspace-add-trigger"
          title="Create or manage workspaces"
          aria-label="Create workspace"
          disabled={busy}
          onClick={() => {
            setOpen(false);
            onOpenManage();
          }}
        >
          <Plus size={14} />
        </button>
      </div>

      {open && (
        <div className="workspace-dropdown-menu" role="listbox">
          <div className="workspace-dropdown-header">
            <span>Workspaces</span>
            <small>{workspaces.length}</small>
          </div>
          <div className="workspace-dropdown-list">
            {workspaces.map((workspace) => {
              const isSelected = workspace.id === workspaceId;
              return (
                <button
                  key={workspace.id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={`workspace-dropdown-item ${isSelected ? "selected" : ""}`}
                  onClick={() => {
                    onSelect(workspace.id);
                    setOpen(false);
                  }}
                >
                  <FolderOpen size={14} />
                  <div className="workspace-item-text">
                    <strong>{workspace.name}</strong>
                    <small>
                      {workspace.document_count ?? 0} docs ·{" "}
                      {workspace.chunk_count ?? 0} chunks
                    </small>
                  </div>
                  {isSelected && (
                    <Check size={14} className="workspace-check-icon" />
                  )}
                </button>
              );
            })}
          </div>
          <div className="workspace-dropdown-divider" />
          <div className="workspace-dropdown-actions">
            <button
              type="button"
              className="workspace-action-btn"
              onClick={() => {
                setOpen(false);
                onOpenManage();
              }}
            >
              <Settings size={13} />
              <span>Manage workspaces…</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
