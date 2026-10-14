"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import { UserButton, useUser } from "@clerk/nextjs";
import Link from "next/link";
import {
  BookOpen,
  ChevronRight,
  Command,
  FolderOpen,
  MessageSquare,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
  Plus,
  RefreshCw,
  Search,
  Settings,
  History,
  Sun,
  Trash2,
} from "lucide-react";
import { api } from "@/lib/api";
import {
  restoreResearchConversation,
  setResearchSession,
} from "@/lib/research-stream";
import { useResearch } from "@/stores/research";
import { Button } from "@/components/ui/button";
import { Chat } from "@/components/chat";
import { Documents } from "@/components/documents";
import { Workspaces } from "@/components/workspaces";
import { WorkspacePicker } from "@/components/workspace-picker";
import { SourceDialog } from "@/components/source-dialog";
import { BrandMark } from "@/components/brand";
import { FreeModelPicker } from "@/components/free-model-picker";
import { RelevancePicker } from "@/components/relevance-picker";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Conversation, Health, Model, View, Workspace } from "@/types";

const Intelligence = dynamic(
  () =>
    import("@/components/intelligence").then((module) => module.Intelligence),
  { ssr: false },
);
const navigation: {
  id: View;
  title: string;
  icon: typeof Search;
  hint?: string;
}[] = [
  { id: "research", title: "Research", icon: Search },
  { id: "documents", title: "Documents", icon: BookOpen },
];
const subscribeToMount = () => () => {};

export function ResearchApp({ userId }: { userId: string }) {
  const { user } = useUser();
  const state = useResearch();
  const {
    view,
    sidebarCollapsed,
    intelligenceOpen,
    workspaceId,
    workspaces,
    conversations,
    conversationId,
    health,
    streaming,
    uploading,
    error,
    update,
    newChat,
  } = state;
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const mounted = useSyncExternalStore(
    subscribeToMount,
    () => true,
    () => false,
  );
  const [connecting, setConnecting] = useState(true);
  const [chatSearch, setChatSearch] = useState("");
  const busy = streaming || uploading;
  useEffect(() => {
    if (!mobileOpen) return;
    const menuButton = menuRef.current;
    const focusable = () =>
      Array.from(
        sidebarRef.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), a[href], select:not(:disabled), input:not(:disabled)",
        ) ?? [],
      ).filter((element) => element.getClientRects().length > 0);
    focusable()[0]?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setMobileOpen(false);
      if (event.key === "Tab") {
        const controls = focusable();
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    const query = window.matchMedia("(max-width: 700px)");
    const closeOnResize = () => {
      if (!query.matches) setMobileOpen(false);
    };
    query.addEventListener("change", closeOnResize);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      query.removeEventListener("change", closeOnResize);
      menuButton?.focus();
    };
  }, [mobileOpen]);
  const initialize = useCallback(async () => {
    try {
      const [health, workspaces] = await Promise.all([
        api<Health>("/health"),
        api<Workspace[]>("/workspaces"),
      ]);
      if (useResearch.getState().sessionId !== userId) return;
      const currentId = useResearch.getState().workspaceId;
      const savedId =
        typeof window !== "undefined"
          ? localStorage.getItem("crebry_workspace_" + userId)
          : null;
      const targetId = workspaces.some((w) => w.id === savedId)
        ? savedId!
        : workspaces.some((workspace) => workspace.id === currentId)
          ? currentId
          : (workspaces[0]?.id ?? "");

      update({
        health,
        workspaces,
        workspaceId: targetId,
        error: "",
      });
      if (targetId && typeof window !== "undefined") {
        localStorage.setItem("crebry_workspace_" + userId, targetId);
      }
      try {
        const models = await api<Model[]>("/models");
        if (useResearch.getState().sessionId !== userId) return;
        update({
          models,
          selectedModel: useResearch.getState().selectedModel || "auto",
          modelNotice: "",
        });
      } catch (error) {
        update({
          modelNotice:
            error instanceof Error
              ? error.message
              : "Could not load free models.",
        });
      }
      if (targetId) {
        const conversations = await api<Conversation[]>(
          `/workspaces/${targetId}/conversations`,
        );
        const current = useResearch.getState();
        if (current.sessionId !== userId || current.workspaceId !== targetId)
          return;
        update({ conversations });
        const savedChat =
          current.conversationId ||
          localStorage.getItem(`crebry_chat_${userId}_${targetId}`);
        if (
          !current.streaming &&
          savedChat &&
          conversations.some((chat) => chat.id === savedChat)
        )
          await restoreResearchConversation(targetId, savedChat);
      }
    } catch (error) {
      if (useResearch.getState().sessionId !== userId) return;
      update({
        health: null,
        error:
          error instanceof Error
            ? error.message
            : "Could not connect to the backend.",
      });
    } finally {
      setConnecting(false);
    }
  }, [update, userId]);
  useEffect(() => {
    setResearchSession(userId);
    if (window.matchMedia("(max-width: 700px)").matches)
      update({ sidebarCollapsed: true });
    if (window.matchMedia("(max-width: 980px)").matches)
      update({ intelligenceOpen: false });
    void initialize();
  }, [initialize, update, userId]);
  useEffect(() => {
    let refreshing = false;
    const refresh = () => {
      const state = useResearch.getState();
      if (
        refreshing ||
        document.visibilityState !== "visible" ||
        state.streaming ||
        state.uploading ||
        state.sessionId !== userId
      )
        return;
      refreshing = true;
      void initialize().finally(() => {
        refreshing = false;
      });
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [initialize, userId]);
  useEffect(() => {
    let active = true;
    if (workspaceId)
      api<Conversation[]>(`/workspaces/${workspaceId}/conversations`)
        .then((conversations) => {
          if (active) update({ conversations });
        })
        .catch((error) => {
          if (active) update({ error: error.message });
        });
    return () => {
      active = false;
    };
  }, [workspaceId, update]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "k") {
        event.preventDefault();
        if (
          !useResearch.getState().streaming &&
          !useResearch.getState().uploading
        )
          newChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [newChat]);

  async function openChat(conversation: Conversation) {
    if (busy) return;
    try {
      await restoreResearchConversation(workspaceId, conversation.id);
    } catch (error) {
      update({
        error:
          error instanceof Error
            ? error.message
            : "Could not open conversation.",
      });
    }
  }
  async function deleteChat(conversation: Conversation) {
    try {
      await api(`/workspaces/${workspaceId}/conversations/${conversation.id}`, {
        method: "DELETE",
      });
      if (useResearch.getState().sessionId !== userId) return;
      update({
        conversations: conversations.filter(
          (chat) => chat.id !== conversation.id,
        ),
      });
      if (conversationId === conversation.id) newChat();
    } catch (error) {
      update({
        error:
          error instanceof Error
            ? error.message
            : "Could not delete conversation.",
      });
    }
  }
  const currentWorkspace = workspaces.find(
    (workspace) => workspace.id === workspaceId,
  );
  const currentChat = conversations.find(
    (conversation) => conversation.id === conversationId,
  );

  if (state.sessionId !== userId)
    return (
      <div className="auth-loading">
        <RefreshCw size={16} className="spin" /> Opening your research
        workspace…
      </div>
    );
  return (
    <div
      className={`research-app ${sidebarCollapsed ? "sidebar-small" : ""} ${mobileOpen ? "mobile-sidebar-open" : ""} ${intelligenceOpen && view === "research" ? "with-intelligence" : ""}`}
    >
      {mobileOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        className="sidebar"
        ref={sidebarRef}
        aria-label="Workspace navigation"
      >
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <BrandMark />
          </div>
          <div>
            <strong>Crebry</strong>
            <small>The Research Agent</small>
          </div>
        </div>
        <WorkspacePicker
          workspaces={workspaces}
          workspaceId={workspaceId}
          busy={busy}
          connecting={connecting}
          onSelect={(id) => {
            newChat();
            update({ workspaceId: id, conversations: [] });
            if (typeof window !== "undefined") {
              localStorage.setItem("crebry_workspace_" + userId, id);
            }
          }}
          onOpenManage={() => setWorkspaceOpen(true)}
        />
        <Button
          variant="outline"
          className="new-research"
          disabled={busy}
          onClick={() => {
            newChat();
            setMobileOpen(false);
          }}
          title="New research"
        >
          <Plus size={16} />
          <span>New research</span>
          <kbd>
            <Command size={10} /> K
          </kbd>
        </Button>
        <div className="sidebar-section-label">Workspace</div>
        <nav aria-label="Main navigation">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              title={item.title}
              disabled={uploading}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => {
                update({ view: item.id });
                setMobileOpen(false);
              }}
            >
              <item.icon size={17} />
              <span>{item.title}</span>
              {item.hint && <small>{item.hint}</small>}
            </button>
          ))}
          <button
            className="nav-item"
            title="Research history"
            onClick={() => {
              setHistoryOpen(true);
              setMobileOpen(false);
            }}
          >
            <History size={17} />
            <span>Research history</span>
          </button>
        </nav>
        <div className="recent-chats">
          <div className="sidebar-section-label">
            Recent research <span>{conversations.length || ""}</span>
          </div>
          {conversations.length > 5 && (
            <div className="chat-search">
              <Search size={12} />
              <input
                aria-label="Search conversations"
                placeholder="Find an exploration…"
                value={chatSearch}
                onChange={(event) => setChatSearch(event.target.value)}
              />
            </div>
          )}
          <div className="recent-list">
            {conversations
              .filter((chat) =>
                chat.title.toLowerCase().includes(chatSearch.toLowerCase()),
              )
              .map((conversation) => (
                <div
                  className={`recent-item ${conversationId === conversation.id ? "selected" : ""}`}
                  key={conversation.id}
                >
                  <button
                    onClick={() => {
                      void openChat(conversation);
                      setMobileOpen(false);
                    }}
                    disabled={busy}
                    title={conversation.title}
                  >
                    <MessageSquare size={13} />
                    <span>{conversation.title}</span>
                  </button>
                  <button
                    className="delete-chat"
                    disabled={busy}
                    onClick={() => void deleteChat(conversation)}
                    aria-label={`Delete chat ${conversation.title}`}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            {!conversations.length && (
              <div className="recent-empty">
                Your next discovery starts
                <br />
                with a question.
              </div>
            )}
          </div>
        </div>
        <div className="sidebar-bottom">
          <button
            className="nav-item settings-nav"
            title="Settings"
            onClick={() => {
              setSettingsOpen(true);
              setMobileOpen(false);
            }}
          >
            <Settings size={17} />
            <span>Settings</span>
          </button>
          <Link className="learn-link" href="/">
            <span>
              <strong>Follow the evidence</strong>
              <small>About Crebry</small>
            </span>
          </Link>
          <div className="profile">
            <div className="profile-user">
              <UserButton />
            </div>
            <div>
              <strong>{user?.firstName || "Your research"}</strong>
              <small>
                <span className={`status-dot ${health ? "live" : ""}`} />
                {health ? "Private workspace" : "Backend offline"}
              </small>
            </div>
            <button
              onClick={() => {
                update({ sidebarCollapsed: !sidebarCollapsed });
                setMobileOpen(false);
              }}
              aria-label={
                sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
              }
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen size={16} />
              ) : (
                <PanelLeftClose size={16} />
              )}
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell" inert={mobileOpen}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu"
              ref={menuRef}
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle sidebar"
              aria-expanded={mobileOpen}
            >
              <PanelLeftOpen size={18} />
            </button>
            <span>{currentWorkspace?.name ?? "Crebry"}</span>
            <ChevronRight size={13} />
            <strong>
              {view === "research"
                ? (currentChat?.title ?? "New exploration")
                : navigation.find((item) => item.id === view)?.title}
            </strong>
          </div>
          <div className="topbar-actions">
            <span className="connection-status">
              <span
                className={`status-dot ${health?.gemini_configured ? "live" : ""}`}
              />
              {streaming
                ? "Research running"
                : connecting
                  ? "Connecting"
                  : !health
                    ? "Offline"
                    : health.gemini_configured
                      ? "Ready to research"
                      : "Setup needed"}
            </span>
            {streaming && view !== "research" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => update({ view: "research" })}
              >
                Return to research
              </Button>
            )}
            {!health && (
              <Button
                variant="ghost"
                size="icon"
                disabled={connecting}
                onClick={() => void initialize()}
                aria-label="Reconnect to backend"
              >
                <RefreshCw size={15} className={connecting ? "spin" : ""} />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() =>
                setTheme(resolvedTheme === "dark" ? "light" : "dark")
              }
              aria-label="Toggle light and dark theme"
            >
              {mounted && resolvedTheme === "dark" ? (
                <Sun size={17} />
              ) : (
                <Moon size={17} />
              )}
            </Button>
            {view === "research" && (
              <Button
                variant={intelligenceOpen ? "secondary" : "ghost"}
                size="icon"
                onClick={() => update({ intelligenceOpen: !intelligenceOpen })}
                aria-label="Toggle intelligence panel"
                aria-pressed={intelligenceOpen}
              >
                <PanelRight size={17} />
              </Button>
            )}
          </div>
        </header>
        {error && view !== "research" && (
          <div className="global-error alert" role="alert">
            {error}
            <button
              onClick={() => update({ error: "" })}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        )}
        <main className="main-content">
          {view === "research" && <Chat />}
          {view === "documents" && <Documents />}
        </main>
      </div>
      {intelligenceOpen && view === "research" && <Intelligence />}
      <Workspaces open={workspaceOpen} onOpenChange={setWorkspaceOpen} />
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="settings-dialog">
          <div className="dialog-icon">
            <Settings size={21} />
          </div>
          <DialogTitle>Workspace settings</DialogTitle>
          <DialogDescription>
            A few preferences for a more focused research space.
          </DialogDescription>
          <div className="preference-row">
            <div>
              <strong>Appearance</strong>
              <p>Choose your interface theme.</p>
            </div>
            <div className="segmented">
              <button
                type="button"
                aria-pressed={theme === "system"}
                className={theme === "system" ? "selected" : ""}
                onClick={() => setTheme("system")}
              >
                System
              </button>
              <button
                type="button"
                aria-pressed={theme === "dark"}
                className={theme === "dark" ? "selected" : ""}
                onClick={() => setTheme("dark")}
              >
                Dark
              </button>
              <button
                type="button"
                aria-pressed={theme === "light"}
                className={theme === "light" ? "selected" : ""}
                onClick={() => setTheme("light")}
              >
                Light
              </button>
            </div>
          </div>
          <div className="preference-row">
            <div>
              <strong>Research model</strong>
              <p>Choose from available free models.</p>
            </div>
            <FreeModelPicker />
          </div>
          <div className="preference-row">
            <div>
              <strong>Document relevance</strong>
              <p>Minimum score per passage. Higher is stricter.</p>
            </div>
            <RelevancePicker />
          </div>
          <div className="preference-row">
            <div>
              <strong>Workspaces</strong>
              <p>Organize projects and their sources.</p>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                setSettingsOpen(false);
                setWorkspaceOpen(true);
              }}
            >
              Manage
            </Button>
          </div>
          <div className="settings-account-note">
            Account and profile preferences are available from your profile
            menu.
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="history-dialog">
          <div className="dialog-icon">
            <History size={21} />
          </div>
          <DialogTitle>Research history</DialogTitle>
          <DialogDescription>
            Return to a question in {currentWorkspace?.name ?? "your workspace"}
            .
          </DialogDescription>
          <div className="search-field">
            <Search size={15} />
            <input
              aria-label="Search research history"
              placeholder="Find a question…"
              value={chatSearch}
              onChange={(event) => setChatSearch(event.target.value)}
            />
          </div>
          <div className="history-list">
            {conversations
              .filter((chat) =>
                chat.title.toLowerCase().includes(chatSearch.toLowerCase()),
              )
              .map((chat) => (
                <button
                  key={chat.id}
                  disabled={busy}
                  onClick={() => {
                    void openChat(chat);
                    setHistoryOpen(false);
                  }}
                >
                  <MessageSquare size={16} />
                  <span>{chat.title}</span>
                  <ChevronRight size={14} />
                </button>
              ))}
            {!conversations.length && (
              <div className="empty-state">
                <BookOpen size={24} />
                <h3>Your research begins here</h3>
                <p>
                  Saved conversations will appear after your first question.
                </p>
              </div>
            )}
            {!!conversations.length &&
              !conversations.some((chat) =>
                chat.title.toLowerCase().includes(chatSearch.toLowerCase()),
              ) && (
                <div className="empty-state">
                  <p>No questions match your search.</p>
                </div>
              )}
          </div>
        </DialogContent>
      </Dialog>
      <SourceDialog />
      {!workspaceId && !connecting && health && (
        <div className="no-workspace">
          <FolderOpen size={25} />
          <h2>Create a workspace to begin</h2>
          <p>
            Give your research a home before uploading documents or asking
            questions.
          </p>
          <Button onClick={() => setWorkspaceOpen(true)}>
            <Plus size={15} /> Create workspace
          </Button>
        </div>
      )}
    </div>
  );
}
