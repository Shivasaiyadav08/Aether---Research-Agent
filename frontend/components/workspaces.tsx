"use client";

import { useEffect, useState } from "react";
import { FolderOpen, LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useResearch } from "@/stores/research";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Workspace } from "@/types";

export function Workspaces({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const {
    workspaces,
    workspaceId,
    streaming,
    uploading,
    update,
    newChat,
    sessionId,
  } = useResearch();
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Workspace | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    if (open)
      api<Workspace[]>("/workspaces")
        .then((records) => {
          if (active && useResearch.getState().sessionId === sessionId)
            update({ workspaces: records });
        })
        .catch((error) => {
          if (active) setError(error.message);
        });
    return () => {
      active = false;
    };
  }, [open, sessionId, update]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const record = await api<Workspace>(
        editing ? `/workspaces/${editing}` : "/workspaces",
        {
          method: editing ? "PATCH" : "POST",
          body: JSON.stringify({ name }),
        },
      );
      const records = await api<Workspace[]>("/workspaces");
      if (useResearch.getState().sessionId !== sessionId) return;
      update({ workspaces: records });
      if (!editing) {
        newChat();
        update({ workspaceId: record.id });
        if (sessionId && typeof window !== "undefined") {
          localStorage.setItem("crebry_workspace_" + sessionId, record.id);
        }
        onOpenChange(false);
      }
      setName("");
      setEditing(null);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not save workspace.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!deleting) return;
    setBusy(true);
    setError("");
    try {
      await api(`/workspaces/${deleting.id}`, { method: "DELETE" });
      const records = await api<Workspace[]>("/workspaces");
      if (useResearch.getState().sessionId !== sessionId) return;
      update({ workspaces: records });
      if (workspaceId === deleting.id) {
        newChat();
        const nextId = records[0]?.id ?? "";
        update({ workspaceId: nextId, conversations: [] });
        if (sessionId && typeof window !== "undefined") {
          localStorage.setItem("crebry_workspace_" + sessionId, nextId);
        }
      }
      setDeleting(null);
      setConfirmation("");
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not delete workspace.",
      );
    } finally {
      setBusy(false);
    }
  }
  const disabled = busy || streaming || uploading;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="workspace-manager">
        <div className="dialog-icon">
          <FolderOpen size={22} />
        </div>
        <DialogTitle>Your research spaces</DialogTitle>
        <DialogDescription>
          Private to your account. Give each project a home for its sources and
          discoveries.
        </DialogDescription>
        <div className="workspace-list">
          {workspaces.map((workspace) => (
            <div className="workspace-row" key={workspace.id}>
              <FolderOpen size={17} />
              <div
                className="workspace-info"
                role="button"
                tabIndex={0}
                style={{ cursor: "pointer" }}
                onClick={() => {
                  if (workspace.id !== workspaceId) {
                    newChat();
                    update({ workspaceId: workspace.id, conversations: [] });
                    if (sessionId && typeof window !== "undefined") {
                      localStorage.setItem(
                        "crebry_workspace_" + sessionId,
                        workspace.id,
                      );
                    }
                  }
                  onOpenChange(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    if (workspace.id !== workspaceId) {
                      newChat();
                      update({ workspaceId: workspace.id, conversations: [] });
                      if (sessionId && typeof window !== "undefined") {
                        localStorage.setItem(
                          "crebry_workspace_" + sessionId,
                          workspace.id,
                        );
                      }
                    }
                    onOpenChange(false);
                  }
                }}
              >
                <strong>{workspace.name}</strong>
                <small>
                  {workspace.document_count ?? 0} documents ·{" "}
                  {workspace.chunk_count ?? 0} chunks ·{" "}
                  {workspace.conversation_count ?? 0} chats
                </small>
              </div>
              {workspace.id === workspaceId && (
                <span className="active-badge">ACTIVE</span>
              )}
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Rename ${workspace.name}`}
                disabled={disabled}
                onClick={() => {
                  setEditing(workspace.id);
                  setName(workspace.name);
                  setDeleting(null);
                }}
              >
                <Pencil size={14} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete ${workspace.name}`}
                disabled={disabled}
                onClick={() => {
                  setDeleting(workspace);
                  setConfirmation("");
                }}
              >
                <Trash2 size={14} />
              </Button>
            </div>
          ))}
        </div>
        {deleting ? (
          <div className="delete-confirm">
            <strong>Delete “{deleting.name}”?</strong>
            <p>
              Its documents, original files, chats, and workflow records will be
              permanently removed. Type the workspace name to confirm.
            </p>
            <input
              aria-label="Confirm workspace name"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
            <div className="dialog-actions">
              <Button variant="ghost" onClick={() => setDeleting(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                disabled={disabled || confirmation !== deleting.name}
                onClick={() => void remove()}
              >
                Delete workspace
              </Button>
            </div>
          </div>
        ) : (
          <form className="workspace-form" onSubmit={save}>
            <label htmlFor="workspace-name">
              {editing ? "Rename workspace" : "Create a workspace"}
            </label>
            <div>
              <input
                id="workspace-name"
                placeholder="e.g. Climate research"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                maxLength={100}
              />
              <Button disabled={disabled || !name.trim()}>
                {busy ? (
                  <LoaderCircle className="spin" size={15} />
                ) : (
                  <Plus size={15} />
                )}
                {editing ? "Save" : "Create"}
              </Button>
            </div>
            {editing && (
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  setEditing(null);
                  setName("");
                }}
              >
                Cancel rename
              </button>
            )}
          </form>
        )}
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
