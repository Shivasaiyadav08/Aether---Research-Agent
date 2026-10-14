""" This file is the database models and database setup file for  project. It decides what information your application stores and how that information is organized in the database.
It uses SQLite, which stores the database in a file called aether.db.
"""



# Used to create timestamps showing when records were created.
from datetime import datetime, timezone

# Used to generate unique IDs for database records.
from uuid import uuid4

# SQLAlchemy tools for database columns, relationships, constraints,
# creating database connections, and responding to database events.
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, create_engine, event

# Tools for defining database tables and their columns using Python classes.
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


# Generate a unique ID for a new database record.
# Example: "a1b2c3..." (a 32-character hexadecimal string).
def new_id() -> str:
    return uuid4().hex


# Get the current date and time in UTC.
# ISO format converts it into a readable string for storage.
def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Base class for all database table classes.
# SQLAlchemy uses this base class to track the tables we define.
# The parent class used by SQLAlchemy to define database tables.
class Base(DeclarativeBase):
    pass


class RoutingState(Base):
    __tablename__ = "routing_state"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class RequestBudget(Base):
    __tablename__ = "request_budgets"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    window: Mapped[int]
    count: Mapped[int]


class ConversationModelPreference(Base):
    __tablename__ = "conversation_model_preferences"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    task: Mapped[str] = mapped_column(String(100), primary_key=True)
    model: Mapped[str] = mapped_column(String(200))


# WORKSPACE TABLE
# A workspace is a container for a user's documents and conversations.
# Stores each user's workspace details and owner ID.
class Workspace(Base):
    __tablename__ = "workspaces"  # Actual table name in the database.

    # Unique ID for each workspace.
    # new_id() generates an ID when a new record is inserted.
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)

    # Workspace name, limited to 100 characters.
    name: Mapped[str] = mapped_column(String(100))

    # Clerk user ID of the workspace owner.
    # It can be None, meaning the database permits a workspace without an owner.
    # index=True helps the database find workspaces by owner more efficiently.
    owner_id: Mapped[str | None] = mapped_column(String(200), index=True)

    # Time when the workspace is created.
    created_at: Mapped[str] = mapped_column(default=now)


# DOCUMENT TABLE
# Stores information about documents uploaded to a workspace.
class Document(Base):
    __tablename__ = "documents"

    # Prevent the same document content from being registered twice
    # in the same workspace, based on its content hash.
    # The same content may still exist in another workspace.
    __table_args__ = (UniqueConstraint("workspace_id", "content_hash"),)

    # Unique document ID.
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)

    # Workspace to which this document belongs.
    # ForeignKey links it to workspaces.id.
    # ondelete="CASCADE" means deleting the workspace can delete its documents.
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )

    # Original document name.
    name: Mapped[str]

    # Hash of the document's content, used to identify duplicate content.
    content_hash: Mapped[str]

    # Document size, usually measured in bytes by the application.
    size: Mapped[int]

    # Processing status; new documents start as "indexing".
    status: Mapped[str] = mapped_column(default="indexing")

    # Number of text chunks created from the document.
    # Chunks can be embedded and retrieved by a RAG system.
    chunk_count: Mapped[int] = mapped_column(default=0)

    # Extracted text from the document.
    # Defaults to an empty string.
    text: Mapped[str] = mapped_column(default="")

    # Error information if document processing fails.
    error: Mapped[str | None]

    # Version of the document's search index, if available.
    index_version: Mapped[str | None]

    # Time when the document record was created.
    created_at: Mapped[str] = mapped_column(default=now)


# CONVERSATION TABLE
# Stores individual chat conversations inside a workspace. Stores conversations created inside a workspace.
class Conversation(Base):
    __tablename__ = "conversations"

    # Unique conversation ID.
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)

    # Workspace that owns this conversation.
    # Deleting the workspace also deletes its conversations.
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )

    # Conversation title shown in the user interface.
    title: Mapped[str]

    # Time when the conversation was created.
    created_at: Mapped[str] = mapped_column(default=now)


# MESSAGE TABLE
# Stores messages sent by the user and generated by the AI.
class Message(Base):
    __tablename__ = "messages"

    # Unique ID for each message.
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)

    # Conversation to which this message belongs.
    # Deleting the conversation also deletes its messages.
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )

    # Who sent the message, for example "user" or "assistant".
    role: Mapped[str]

    # Actual message text.
    content: Mapped[str]

    # Sources used to support an AI answer.
    # JSON allows a list of source information to be stored in one column.
    # default=list creates a separate empty list for each new record.
    sources: Mapped[list] = mapped_column(JSON, default=list)

    # Optional ID connecting this message to an AI workflow execution.
    run_id: Mapped[str | None]

    # Time when the message was created.
    created_at: Mapped[str] = mapped_column(default=now)


# WORKFLOW RUN TABLE
# Stores information about an individual AI workflow execution.
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    # Unique ID for this workflow execution.
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)

    # Conversation associated with this execution.
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )

    # Workflow starts with the status "running".
    # Application code should update it when processing finishes or fails.
    status: Mapped[str] = mapped_column(default="running")

    # List of events produced during the workflow.
    # For example, an event might record document retrieval or answer generation.
    events: Mapped[list] = mapped_column(JSON, default=list)

    # Total workflow execution time in milliseconds.
    duration_ms: Mapped[int] = mapped_column(default=0)

    # Error details if the workflow fails.
    error: Mapped[str | None]

    # Time when the workflow run was created.
    created_at: Mapped[str] = mapped_column(default=now)


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (UniqueConstraint("owner_id", "request_key"),)
    id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(200), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str]
    snapshot: Mapped[dict] = mapped_column(JSON)
    next_node: Mapped[str] = mapped_column(default="retrieve")
    replaced_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default="queued", index=True)
    lease_owner: Mapped[str | None]
    lease_until: Mapped[float] = mapped_column(default=0)
    deadline_at: Mapped[float]
    cancel_requested: Mapped[bool] = mapped_column(default=False)


class ResearchEvent(Base):
    __tablename__ = "research_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), primary_key=True)
    sequence: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


# APPLICATION SETTINGS TABLE
# Stores configurable AI application settings in the database.
class AppSettings(Base):
    __tablename__ = "settings"

    # Integer primary key.
    # The default is 1, which is useful when the application keeps one settings row.
    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Name of the AI model used by the application.
    model: Mapped[str]

    # Minimum relevance score used by the retrieval logic.
    # The application code determines how this threshold is applied.
    relevance_threshold: Mapped[float] = mapped_column(default=0.5)

    # Whether the application should validate generated answers.
    validate_answer: Mapped[bool] = mapped_column(default=True)

    # Maximum number of retries allowed by the workflow logic.
    max_retries: Mapped[int] = mapped_column(default=1)

    # Number of document chunks to retrieve for a query.
    retrieval_count: Mapped[int] = mapped_column(default=6)


# CREATE THE DATABASE CONNECTION
def create_database(data_dir, database_url=None):
    """
    Create the data directory, configure SQLite, create tables,
    and return the database engine and session factory.
    """

    # Create the data directory if it does not already exist.
    # parents=True also creates missing parent directories.
    data_dir.mkdir(parents=True, exist_ok=True)

    # Connect to a SQLite database file named aether.db.
    # SQLite stores the database in a file instead of requiring
    # a separate database server.
    #
    # check_same_thread=False allows the connection to be used across
    # different threads, subject to SQLAlchemy's connection management.
    url = database_url or f"sqlite:///{(data_dir / 'aether.db').as_posix()}"
    if url.startswith(("postgres://", "postgresql://")):
        url = "postgresql+psycopg://" + url.split("://", 1)[1]
    is_sqlite = url.startswith("sqlite:")
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {}, pool_pre_ping=True)

    # RUN THIS CODE WHEN A DATABASE CONNECTION IS OPENED.
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):

        if not is_sqlite:
            return

        # Enable foreign-key checks in SQLite.
        # This helps enforce relationships between database tables.
        connection.execute("PRAGMA foreign_keys=ON")

        # Enable write-ahead logging (WAL).
        # This can improve concurrency between database readers and writers.
        connection.execute("PRAGMA journal_mode=WAL")

        # Wait up to 10 seconds when the database is busy.
        # This can reduce immediate "database is locked" errors.
        connection.execute("PRAGMA busy_timeout=10000")

    # CHECK AND UPDATE AN OLDER DATABASE
    # engine.begin() opens a transaction and commits it on success.
    with engine.begin() as connection:

        # Read the existing columns in the workspaces table.
        columns = connection.exec_driver_sql(
            "PRAGMA table_info(workspaces)"
        ).fetchall() if is_sqlite else []

        # If the table already exists but does not have owner_id,
        # add the column so an older database can support ownership.
        #
        # Existing workspaces are left without an assigned owner.
        # This avoids incorrectly assigning old data to a user.
        if columns and "owner_id" not in {row[1] for row in columns}:
            connection.exec_driver_sql(
                "ALTER TABLE workspaces ADD COLUMN owner_id VARCHAR(200)"
            )

            # Create an index to make searches by owner ID faster.
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_workspaces_owner_id ON workspaces(owner_id)"
            )

    # Create any missing tables based on the classes defined above.
    # This does not automatically migrate every kind of schema change.
    Base.metadata.create_all(engine)

    # Create a factory for opening database sessions.
    # A session is used to query, insert, update, and delete records.
    #
    # expire_on_commit=False keeps loaded object values accessible
    # after a commit without automatically expiring them.
    #
    # Return both objects so the rest of the application can use them.
    return engine, sessionmaker(engine, expire_on_commit=False)


# CONVERT A DATABASE RECORD INTO A DICTIONARY
def as_dict(record) -> dict:

    # Go through every column in the record's table and return
    # its column name and current value as a dictionary.
    #
    # This is useful when the application needs to serialize a record
    # into a structure that can later be returned by an API.
    return {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
    }
