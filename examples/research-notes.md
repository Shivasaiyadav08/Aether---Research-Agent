# Aether Research: a sample knowledge source

Retrieval-augmented generation (RAG) finds relevant source passages before
generating an answer. It helps a language model answer using supplied evidence.
It does not guarantee that every generated claim is correct.

Aether Research splits extracted text into chunks of up to 800 characters with
150 characters of overlap. Paragraph boundaries are preferred when possible.
Overlap helps retain context near a boundary. PDF chunks retain page numbers.

The local sentence-transformers all-MiniLM-L6-v2 model converts text into
384-dimensional vectors. These embeddings stay on the computer. Chroma stores
the vectors persistently in a separate collection for each workspace.

Corrective RAG adds a quality check. Gemini grades each retrieved chunk for
relevance. The default threshold is 50 percent. A separate sufficiency check
determines whether accepted chunks answer all important parts of the question.
If evidence is insufficient, the workflow rewrites the query and searches Tavily.

Document references use identifiers such as D1. Web references use W1. Citation
membership is checked in code, and an LLM check assesses grounding.
The LLM check can fail to detect mistakes. Readers should inspect important facts.

SQLite stores workspaces, document metadata, settings, conversations, messages,
and workflow traces. The reference application runs on localhost.
Clerk verifies signed-in accounts, and API ownership checks isolate each user's
workspaces. Do not expose the reference backend publicly without deployment controls.
