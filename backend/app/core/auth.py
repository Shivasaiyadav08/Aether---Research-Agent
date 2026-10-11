# SECURITY RULE:
# Clerk checks who the user is.
# Our database checks whether the user owns the workspace.
# Never trust a user ID sent by the frontend.

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from fastapi import Depends, HTTPException, Request

from app.core.config import config
from app.models.database import Workspace


def verify_session(request: Request) -> str | None:
    """
    Check whether the user is logged in.
    So, this function mainly checks the user's existing login session on backend requests. It does not itself handle the login form or verify the password.

    Returns the user's Clerk ID if login is valid.
    Returns None for the health-check endpoint.
    """

    # Allow the health endpoint without login.
    if request.url.path == "/api/health":
        return None

    # Check whether the request contains a login token.
    # The frontend sends it in the Authorization header.
    if not request.headers.get("authorization", "").startswith("Bearer "):
        raise HTTPException(
            401,
            "Sign in to access your research.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Check whether Clerk authentication is configured on the backend.
    # Without either key, the backend cannot verify the session.
    if not config.clerk_secret_key and not config.clerk_jwt_key:
        raise HTTPException(
            503,
            "Clerk authentication is not configured on the backend."
        )

    # Convert the allowed frontend URLs from a string into a list.
    # Example: "http://localhost:3000,https://example.com"
    # becomes two separate URLs.
    parties = [
        value.strip()
        for value in config.clerk_authorized_parties.split(",")
        if value.strip()
    ]

    # Stop if no allowed frontend URLs are configured.
    if not parties:
        raise HTTPException(
            503,
            "Configure CLERK_AUTHORIZED_PARTIES on the backend."
        )

    # Ask Clerk's SDK to verify the login token.
    try:
        state = authenticate_request(
            request,
            AuthenticateRequestOptions(
                secret_key=config.clerk_secret_key or None,
                jwt_key=config.clerk_jwt_key or None,
                authorized_parties=parties,
                accepts_token=["session_token"],
            ),
        )

    # If Clerk cannot verify the token, reject the request.
    except Exception as error:
        raise HTTPException(
            401,
            "Could not verify your session. Sign in again."
        ) from error

    # Get the user ID from the verified token.
    # "sub" identifies the user, and "exp" contains the expiry time.
    # "sid" identifies the session.
    user_id = (state.payload or {}).get("sub")
    payload = state.payload or {}

    # Check that the user is logged in and that the token
    # contains the expected user ID and session information.
    if (
        not state.is_signed_in
        or not isinstance(user_id, str)
        or not user_id.startswith("user_")
        or not isinstance(payload.get("exp"), (int, float))
        or not isinstance(payload.get("sid"), str)
    ):
        raise HTTPException(
            401,
            "Your session is invalid or expired. Sign in again."
        )

    # Return the verified user ID for other functions to use.
    return user_id


def require_workspace_owner(db, workspace_id: str, user_id: str):
    """
    Check whether the logged-in user owns the requested workspace.
    If workspace 123 belongs to Rahul, access is allowed.

   If it belongs to someone else, access is denied.

   If the workspace doesn't exist, access is also denied.
    """

    # Find the workspace in the database using its ID.
    workspace = db.get(Workspace, workspace_id)

    # If the workspace doesn't exist or belongs to someone else,
    # deny access. Both cases return the same error.
    if workspace is None or workspace.owner_id != user_id:
        raise HTTPException(404, "Workspace not found.")

    # Return the workspace if the user owns it.
    return workspace


def authorize_request(
    request: Request,
    user_id: str | None = Depends(verify_session)
):
    """
    Connect login verification with workspace access checking.

    Depends(verify_session) tells FastAPI to run verify_session()
    and pass its result into user_id.
    """

    # Save the verified user ID for use during this request.
    request.state.user_id = user_id

    # Get the workspace ID from the URL, if the route has one.
    workspace_id = request.path_params.get("workspace_id")

    # If a workspace ID exists, check its ownership in the database.
    if workspace_id:
        # Open a database session to look up the workspace.
        with request.app.state.db() as db:
            require_workspace_owner(db, workspace_id, user_id)

    # If a check fails, an HTTP error stops the request.
    # Otherwise, FastAPI can continue to the route handler.