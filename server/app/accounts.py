"""Sign-in (Neon Auth, managed Better Auth) and each person's saved designs (Neon Postgres).

Both are optional: without NEON_AUTH_BASE_URL and DATABASE_URL the app still makes designs, and these
endpoints answer 503.
"""
import base64
import io
import os
from contextlib import contextmanager
from typing import Annotated
from urllib.parse import urlsplit

import httpx
import jwt
import pystitch
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from pystitch.EmbConstant import STITCH

from app.machines import MACHINES
from app.preprocess import get_thread_catalog, nearest_thread

# e.g. https://ep-xxx.neonauth.ap-southeast-2.aws.neon.tech/neondb/auth
NEON_AUTH_URL = os.environ.get("NEON_AUTH_BASE_URL", "").rstrip("/")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
MAX_DESIGN_BYTES = 2 * 1024 * 1024  # home designs are well under 1 MB
# ponytail: flat cap so one account can't fill the free 1 GB database; raise it with a paid plan
MAX_DESIGNS_PER_PERSON = 200

SCHEMA = """
create table if not exists designs (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references neon_auth."user"(id) on delete cascade,
  name          text not null check (char_length(name) between 1 and 80),
  machine_key   text not null,
  format        text not null,
  file          bytea not null,
  thumbnail     bytea not null,
  threads       jsonb not null,
  stitch_count  int  not null,
  width_mm      real not null,
  height_mm     real not null,
  created_at    timestamptz not null default now()
);
create index if not exists designs_owner_created on designs (owner_id, created_at desc);
"""

router = APIRouter(prefix="/api")
# Neon suspends an idle database; checking each connection on checkout replaces ones it dropped
pool = (ConnectionPool(DATABASE_URL, min_size=1, max_size=4, open=False, check=ConnectionPool.check_connection,
                       kwargs={"row_factory": dict_row})
        if DATABASE_URL else None)
# Caches Neon's signing keys; fetched on first use
jwks = jwt.PyJWKClient(f"{NEON_AUTH_URL}/.well-known/jwks.json") if NEON_AUTH_URL else None
auth_http = httpx.AsyncClient(timeout=20)


def open_database():
    """Called at startup: opens the pool and makes sure the table exists."""
    if pool:
        pool.open()
        with pool.connection() as conn:
            conn.execute(SCHEMA)


@contextmanager
def database():
    if not pool:
        raise HTTPException(status_code=503, detail="Saving designs isn’t set up on this server.")
    with pool.connection() as conn:
        yield conn


def current_user(authorization: Annotated[str, Header()] = "") -> str:
    """The signed-in person's id, from the Neon Auth JWT the client sends as a Bearer token."""
    if not jwks:
        raise HTTPException(status_code=503, detail="Signing in isn’t set up on this server.")
    token = authorization.removeprefix("Bearer ").strip()
    # Neon issues tokens with issuer and audience set to the auth URL's origin
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(NEON_AUTH_URL))
    try:
        key = jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key, algorithms=["EdDSA"], issuer=origin, audience=origin)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Please sign in again.") from exc
    return claims["sub"]


User = Annotated[str, Depends(current_user)]


@router.api_route("/auth/{path:path}", methods=["GET", "POST"])
async def auth_proxy(path: str, request: Request):
    """Passes sign-in calls through to Neon Auth, so its cookies belong to this site.

    Straight from the browser they'd be third-party cookies, which Safari blocks.
    """
    if not NEON_AUTH_URL:
        raise HTTPException(status_code=503, detail="Signing in isn’t set up on this server.")
    # Origin is forwarded as is: Neon Auth only accepts this site's origins (Neon console: Auth > Domains)
    headers = {k: v for k in ("content-type", "cookie", "origin", "user-agent", "accept") if (v := request.headers.get(k))}
    upstream = await auth_http.request(request.method, f"{NEON_AUTH_URL}/{path}", params=request.query_params,
                                       content=await request.body(), headers=headers)
    response = Response(upstream.content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"))
    if jwt_header := upstream.headers.get("set-auth-jwt"):
        response.headers["set-auth-jwt"] = jwt_header  # the client reads the session's JWT from here
    for cookie in upstream.headers.get_list("set-cookie"):
        # Drop any Domain so the cookie is this site's
        response.headers.append("set-cookie", "; ".join(p for p in cookie.split("; ") if not p.lower().startswith("domain=")))
    return response


class NewDesign(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    machine_key: str
    file_base64: str = Field(max_length=MAX_DESIGN_BYTES * 4 // 3 + 4)
    threads: list[str] = Field(max_length=13)


@router.post("/designs")
def save_design(design: NewDesign, user: User):
    machine = MACHINES.get(design.machine_key)
    if not machine:
        raise HTTPException(status_code=400, detail="Unknown machine.")
    by_id = {t["id"]: t for t in get_thread_catalog()[0]}
    if not all(t in by_id for t in design.threads):
        raise HTTPException(status_code=400, detail="Unknown thread.")
    # The file comes from the browser, so it's read back to check it really is a design for this machine
    try:
        data = base64.b64decode(design.file_base64, validate=True)
        pattern = getattr(pystitch, f"read_{machine['format']}")(io.BytesIO(data))
    except Exception as exc:  # the readers fail in many ways on bad input
        raise HTTPException(status_code=400, detail="That design file couldn’t be read.") from exc
    stitches = sum(1 for _, _, command in pattern.stitches if command == STITCH) if pattern else 0
    if not stitches:
        raise HTTPException(status_code=400, detail="That design file has no stitches.")
    min_x, min_y, max_x, max_y = pattern.bounds()
    # Drawn in the chosen threads, not the palette colours the file stores
    chosen = [by_id[t] for t in design.threads]
    for t in pattern.threadlist if chosen else []:
        t.set_hex_color(nearest_thread((t.get_red(), t.get_green(), t.get_blue()), chosen)["hex"])
    thumbnail = io.BytesIO()
    pystitch.write_png(pattern, thumbnail, {"linewidth": 3})

    with database() as conn:
        count = conn.execute("select count(*) as n from designs where owner_id = %s", (user,)).fetchone()["n"]
        if count >= MAX_DESIGNS_PER_PERSON:
            raise HTTPException(status_code=400, detail=f"You can keep up to {MAX_DESIGNS_PER_PERSON} designs. Delete some to save more.")
        row = conn.execute(
            """insert into designs (owner_id, name, machine_key, format, file, thumbnail, threads, stitch_count, width_mm, height_mm)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            (user, design.name.strip(), design.machine_key, machine["format"], data, thumbnail.getvalue(),
             Jsonb([by_id[t] for t in design.threads]), stitches, (max_x - min_x) / 10, (max_y - min_y) / 10),
        ).fetchone()
    return {"id": row["id"]}


@router.get("/designs")
def list_designs(user: User):
    # ponytail: everything in one response, thumbnails inline (~10 KB each); paginate if lists get long
    with database() as conn:
        rows = conn.execute(
            """select id, name, machine_key, format, thumbnail, threads, stitch_count, width_mm, height_mm, created_at
               from designs where owner_id = %s order by created_at desc""",
            (user,),
        ).fetchall()
    for row in rows:
        row["thumbnail"] = "data:image/png;base64," + base64.b64encode(row["thumbnail"]).decode()
    return rows


@router.get("/designs/{design_id}/file")
def design_file(design_id: str, user: User):
    with database() as conn:
        row = conn.execute("select name, format, file from designs where id::text = %s and owner_id = %s",
                           (design_id, user)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Design not found.")
    return {"file_base64": base64.b64encode(row["file"]).decode(), "file_name": f"{row['name']}.{row['format']}"}


@router.delete("/designs/{design_id}", status_code=204)
def delete_design(design_id: str, user: User):
    with database() as conn:
        deleted = conn.execute("delete from designs where id::text = %s and owner_id = %s", (design_id, user)).rowcount
    if not deleted:
        raise HTTPException(status_code=404, detail="Design not found.")
